# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Dev command implementation for running API server and dashboard together.

This module provides the `amelia dev` command that starts both the Python API server
and the React dashboard with a unified, color-coded log output.
"""
from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import shutil
import signal
import socket
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.text import Text

from amelia.server.banner import (
    CREAM,
    GOLD,
    GRAY,
    MOSS,
    RUST,
    TWILIGHT,
    get_service_urls_display,
    print_banner,
)
from amelia.server.config import ServerConfig


# Process prefixes
SERVER_PREFIX = Text("[server]    ", style=TWILIGHT)
DASHBOARD_PREFIX = Text("[dashboard] ", style=GOLD)

dev_app = typer.Typer(help="Start development server with dashboard")
console = Console()


def is_amelia_dev_repo() -> bool:
    """Detect if running in the Amelia development repository.

    Returns:
        True if all three conditions are met:
        - amelia/ directory exists (Python package)
        - dashboard/package.json exists
        - .git/ directory exists
    """
    cwd = Path.cwd()
    return (
        (cwd / "amelia").is_dir()
        and (cwd / "dashboard" / "package.json").is_file()
        and (cwd / ".git").is_dir()
    )


def check_pnpm_installed() -> bool:
    """Check if pnpm is available in PATH.

    Returns:
        True if pnpm is available, False otherwise.
    """
    return shutil.which("pnpm") is not None


def check_node_installed() -> bool:
    """Check if Node.js is available in PATH.

    Returns:
        True if Node.js is available, False otherwise.
    """
    return shutil.which("node") is not None


def check_node_modules_exist() -> bool:
    """Check if dashboard/node_modules exists.

    Returns:
        True if node_modules directory exists, False otherwise.
    """
    return (Path.cwd() / "dashboard" / "node_modules").is_dir()


def check_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding.

    Args:
        host: Host address to check.
        port: Port number to check.

    Returns:
        True if port is available, False if already in use.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError as e:
            if e.errno in (errno.EADDRINUSE, errno.EADDRNOTAVAIL):
                return False
            raise


async def run_pnpm_install() -> bool:
    """Run pnpm install in the dashboard directory.

    Returns:
        True if installation succeeded, False otherwise.
    """
    console.print(DASHBOARD_PREFIX + Text("Installing dependencies...", style=CREAM))

    process = await asyncio.create_subprocess_exec(
        "pnpm",
        "install",
        cwd=Path.cwd() / "dashboard",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    assert process.stdout is not None
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        text = line.decode().rstrip()
        console.print(DASHBOARD_PREFIX + Text(text, style=GRAY))

    await process.wait()
    return process.returncode == 0


def _get_log_level_style(text: str) -> str:
    """Determine the style based on log level prefix in text.

    Parses uvicorn-style log output (e.g., "INFO:     message") and returns
    the appropriate color from the Amelia palette.

    Args:
        text: Log line text to parse.

    Returns:
        Color style string for the detected log level.
    """
    text_upper = text.upper()
    if text_upper.startswith("ERROR") or text_upper.startswith("CRITICAL"):
        return RUST
    if text_upper.startswith("WARNING") or text_upper.startswith("WARN"):
        return GOLD
    if text_upper.startswith("DEBUG"):
        return CREAM
    if text_upper.startswith("INFO"):
        return MOSS
    # Default for unparseable lines
    return CREAM


async def stream_output(
    stream: asyncio.StreamReader,
    prefix: Text,
    is_stderr: bool = False,
) -> None:
    """Stream output from a subprocess with colored prefix.

    Args:
        stream: The asyncio stream to read from.
        prefix: The colored prefix to prepend to each line.
        is_stderr: Whether this is stderr (ignored, we parse log levels instead).
    """
    # Note: is_stderr is kept for API compatibility but we parse log levels instead
    # because uvicorn writes all logs (including INFO) to stderr
    _ = is_stderr
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode().rstrip()
        if text:
            style = _get_log_level_style(text)
            console.print(prefix + Text(text, style=style))


class ProcessManager:
    """Manages the lifecycle of server and dashboard processes."""

    def __init__(self) -> None:
        self.server_process: asyncio.subprocess.Process | None = None
        self.dashboard_process: asyncio.subprocess.Process | None = None
        self._shutdown_event = asyncio.Event()
        self._exit_code = 0

    async def start_server(
        self,
        host: str,
        port: int,
    ) -> asyncio.subprocess.Process:
        """Start the uvicorn server process.

        Args:
            host: Host to bind to.
            port: Port to bind to.

        Returns:
            The subprocess handle.
        """
        console.print(
            SERVER_PREFIX + Text(f"Starting uvicorn on http://{host}:{port}", style=CREAM)
        )

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "uvicorn",
            "amelia.server.main:app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "info",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self.server_process = process
        return process

    async def start_dashboard(self) -> asyncio.subprocess.Process:
        """Start the Vite dev server process.

        Returns:
            The subprocess handle.
        """
        console.print(
            DASHBOARD_PREFIX
            + Text("Starting vite on http://localhost:5173", style=CREAM)
        )

        process = await asyncio.create_subprocess_exec(
            "pnpm",
            "run",
            "dev",
            cwd=Path.cwd() / "dashboard",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "FORCE_COLOR": "1"},
        )

        self.dashboard_process = process
        return process

    async def wait_for_process(
        self,
        process: asyncio.subprocess.Process,
        name: str,
        prefix: Text,
    ) -> int:
        """Wait for a process and stream its output.

        Args:
            process: The subprocess to wait for.
            name: Name of the process for logging.
            prefix: Colored prefix for log lines.

        Returns:
            The process exit code.
        """
        assert process.stdout is not None
        assert process.stderr is not None

        # Stream both stdout and stderr
        stdout_task = asyncio.create_task(stream_output(process.stdout, prefix))
        stderr_task = asyncio.create_task(stream_output(process.stderr, prefix, is_stderr=True))

        # Wait for process to complete
        exit_code = await process.wait()

        # Wait for output streaming to complete
        await stdout_task
        await stderr_task

        if exit_code != 0:
            console.print(
                prefix + Text(f"Process exited with code {exit_code}", style=RUST)
            )
            self._exit_code = exit_code
            self._shutdown_event.set()

        return exit_code

    async def shutdown(self) -> None:
        """Gracefully shutdown all processes."""
        tasks: list[asyncio.Task[None]] = []

        if self.dashboard_process and self.dashboard_process.returncode is None:
            console.print(
                DASHBOARD_PREFIX + Text("Stopping...", style=MOSS)
            )
            self.dashboard_process.terminate()
            tasks.append(asyncio.create_task(self._wait_for_termination(self.dashboard_process)))

        if self.server_process and self.server_process.returncode is None:
            console.print(
                SERVER_PREFIX + Text("Stopping...", style=MOSS)
            )
            self.server_process.terminate()
            tasks.append(asyncio.create_task(self._wait_for_termination(self.server_process)))

        if tasks:
            await asyncio.gather(*tasks)

    async def _wait_for_termination(
        self,
        process: asyncio.subprocess.Process,
        timeout: float = 5.0,
    ) -> None:
        """Wait for a process to terminate, killing if necessary.

        Args:
            process: The process to wait for.
            timeout: Seconds to wait before sending SIGKILL.
        """
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()

    @property
    def exit_code(self) -> int:
        """Get the exit code for the dev command."""
        return self._exit_code

    def request_shutdown(self) -> None:
        """Request graceful shutdown of all processes."""
        self._shutdown_event.set()

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown to be requested."""
        await self._shutdown_event.wait()


async def run_dev_mode(
    host: str,
    port: int,
    no_dashboard: bool,
    is_dev_repo: bool,
) -> int:
    """Run the development server with optional dashboard.

    Args:
        host: Host to bind to.
        port: Port to bind to.
        no_dashboard: If True, skip starting the dashboard.
        is_dev_repo: Whether we're in the Amelia dev repo.

    Returns:
        Exit code (0 for success).
    """
    manager = ProcessManager()
    loop = asyncio.get_running_loop()

    # Handle signals
    def signal_handler() -> None:
        """Handle termination signals by requesting graceful shutdown."""
        manager.request_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        # Start server
        server = await manager.start_server(host, port)
        tasks: list[asyncio.Task[int]] = [
            asyncio.create_task(
                manager.wait_for_process(server, "server", SERVER_PREFIX)
            )
        ]

        # Start dashboard if in dev mode and not disabled
        if is_dev_repo and not no_dashboard:
            # Check dependencies
            if not check_node_modules_exist():
                success = await run_pnpm_install()
                if not success:
                    console.print(
                        DASHBOARD_PREFIX
                        + Text("Failed to install dependencies", style=RUST)
                    )
                    await manager.shutdown()
                    return 1

            dashboard = await manager.start_dashboard()
            tasks.append(
                asyncio.create_task(
                    manager.wait_for_process(dashboard, "dashboard", DASHBOARD_PREFIX)
                )
            )

        # Wait for shutdown signal or process failure
        done, pending = await asyncio.wait(
            [*tasks, asyncio.create_task(manager.wait_for_shutdown())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    finally:
        await manager.shutdown()
        # Remove signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)

    return manager.exit_code


@dev_app.callback(invoke_without_command=True)
def dev(
    ctx: typer.Context,
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="Server port (default: 8420)"),
    ] = None,
    no_dashboard: Annotated[
        bool,
        typer.Option("--no-dashboard", help="Server only, skip dashboard"),
    ] = False,
    bind_all: Annotated[
        bool,
        typer.Option(
            "--bind-all",
            help="Bind to 0.0.0.0 (network access)",
        ),
    ] = False,
) -> None:
    """Start the Amelia development environment.

    Runs the API server and dashboard together with unified, color-coded output.

    In the Amelia repository (dev mode):
      - Runs uvicorn for the API server
      - Runs Vite dev server for the dashboard with hot reload
      - Auto-installs npm dependencies if needed

    In other repositories (user mode):
      - Runs uvicorn only
      - Serves bundled dashboard static files
    """
    if ctx.invoked_subcommand is not None:
        return

    is_dev_repo = is_amelia_dev_repo()

    # Check prerequisites for dev mode
    if is_dev_repo and not no_dashboard:
        if not check_node_installed():
            console.print(
                Text(
                    "Error: Node.js is required for dev mode. Install from https://nodejs.org",
                    style=RUST,
                )
            )
            raise typer.Exit(code=1)

        if not check_pnpm_installed():
            console.print(
                Text(
                    "Error: pnpm is required for dev mode. Install: npm i -g pnpm",
                    style=RUST,
                )
            )
            raise typer.Exit(code=1)

    # Print banner
    print_banner(console)

    # Load config
    config = ServerConfig()
    effective_port = port if port is not None else config.port
    effective_host = "0.0.0.0" if bind_all else config.host

    # Check port availability
    if not check_port_available(effective_host, effective_port):
        console.print(
            Text(
                f"Error: Port {effective_port} is already in use. "
                f"Try a different port with --port <PORT>",
                style=RUST,
            )
        )
        raise typer.Exit(code=1)

    # Show mode and service URLs
    mode = "dev" if is_dev_repo else "user"
    is_dev_mode = is_dev_repo and not no_dashboard
    console.print(Text(f"Mode: {mode}", style=MOSS))
    console.print()
    console.print(get_service_urls_display(effective_host, effective_port, is_dev_mode))
    console.print()

    if bind_all:
        console.print(
            Text(
                "Warning: Server accessible to all network clients. No authentication enabled.",
                style=RUST,
            )
        )

    # Run the async event loop
    try:
        exit_code = asyncio.run(
            run_dev_mode(effective_host, effective_port, no_dashboard, is_dev_repo)
        )
        raise typer.Exit(code=exit_code)
    except KeyboardInterrupt:
        console.print(Text("\nShutdown complete.", style=MOSS))
