"""CLI commands for the Amelia server."""
from typing import Annotated

import typer
import uvicorn
from rich.console import Console

from amelia.server.banner import print_banner
from amelia.server.config import ServerConfig


console = Console()

server_app = typer.Typer(
    name="server",
    help="Amelia API server commands.",
)


@server_app.callback(invoke_without_command=True)
def server(
    ctx: typer.Context,
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="Port to listen on (default: from config/env)"),
    ] = None,
    bind_all: Annotated[
        bool,
        typer.Option(
            "--bind-all",
            help="Bind to all interfaces (0.0.0.0). WARNING: Exposes server to network.",
        ),
    ] = False,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Enable auto-reload for development"),
    ] = False,
) -> None:
    """Start the Amelia API server.

    By default, binds to localhost (127.0.0.1) only.
    Use --bind-all to expose to the network (not recommended without auth).

    Port and host can be configured via AMELIA_PORT and AMELIA_HOST env vars.
    """
    # Skip if subcommand is invoked
    if ctx.invoked_subcommand is not None:
        return

    # Load config (respects environment variables)
    config = ServerConfig()

    # CLI flags override config
    effective_port = port if port is not None else config.port
    effective_host = "0.0.0.0" if bind_all else config.host

    # Print ASCII banner
    print_banner(console)

    if bind_all:
        console.print(
            "[yellow]Warning:[/yellow] Server accessible to all network clients. "
            "No authentication enabled.",
            style="bold yellow",
        )

    console.print(f"Starting Amelia server on http://{effective_host}:{effective_port}")
    console.print(f"API docs: http://{effective_host}:{effective_port}/api/docs")

    try:
        uvicorn.run(
            "amelia.server.main:app",
            host=effective_host,
            port=effective_port,
            reload=reload,
            log_level="info",
        )
    except KeyboardInterrupt:
        console.print("\nServer stopped.")


# NOTE: Cleanup command will be implemented in Phase 2.1-02 (Database Foundation)
# when LogRetentionService is added. See docs/plans/phase-2.1-02-database-foundation.md
@server_app.command("cleanup", hidden=True)
def cleanup(
    retention_days: Annotated[
        int,
        typer.Option("--retention-days", help="Days to retain logs"),
    ] = 30,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be deleted without deleting"),
    ] = False,
) -> None:
    """Run log retention cleanup manually.

    Useful if server was killed without graceful shutdown.

    Note: This command requires the database foundation (Phase 2.1-02).
    """
    # Placeholder until LogRetentionService is implemented in Phase 2.1-02
    console.print(
        "[yellow]Cleanup not yet available.[/yellow] "
        "Requires database foundation (see docs/plans/phase-2.1-02-database-foundation.md)"
    )
