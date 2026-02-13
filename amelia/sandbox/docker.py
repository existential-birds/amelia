"""Docker-based sandbox provider for isolated agent execution.

Manages a single long-lived Docker container per profile. All docker
interactions use asyncio.create_subprocess_exec — no Docker SDK dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from loguru import logger

from amelia.sandbox.network import generate_allowlist_rules
from amelia.sandbox.provider import SandboxProvider


class DockerSandboxProvider(SandboxProvider):
    """Manages a Docker container for sandboxed agent execution.

    One container per profile, started on first use, kept alive with
    ``sleep infinity``. Work happens via ``docker exec``.

    Args:
        profile_name: Profile this sandbox belongs to.
        image: Docker image to use.
        proxy_port: Host port for the LLM/git proxy.
    """

    def __init__(
        self,
        profile_name: str,
        image: str = "amelia-sandbox:latest",
        proxy_port: int = 8430,
        network_allowlist_enabled: bool = False,
        network_allowed_hosts: Sequence[str] | None = None,
    ) -> None:
        self.profile_name = profile_name
        self.image = image
        self.proxy_port = proxy_port
        self.network_allowlist_enabled = network_allowlist_enabled
        self.network_allowed_hosts: list[str] = list(network_allowed_hosts or [])

        self.container_name = f"amelia-sandbox-{profile_name}"

    async def ensure_running(self) -> None:
        """Ensure the sandbox container is ready. Start if not running."""
        if await self.health_check():
            return
        if not await self._image_exists():
            await self._build_image()
        await self._start_container()
        await self._wait_for_ready()
        await self._apply_network_allowlist()

    async def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        """Execute command in container, streaming stdout lines.

        Args:
            command: Command and arguments to execute.
            cwd: Working directory inside the container.
            env: Additional environment variables.
            stdin: Optional bytes to pipe to stdin.

        Yields:
            Lines of stdout output.

        Raises:
            RuntimeError: If the command exits with non-zero status.
        """
        cmd = ["docker", "exec", "--user", "vscode"]
        if cwd:
            cmd.extend(["--workdir", cwd])
        if env:
            for key, value in env.items():
                cmd.extend(["-e", f"{key}={value}"])
        cmd.append(self.container_name)
        cmd.extend(command)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
        )

        if stdin and proc.stdin:
            proc.stdin.write(stdin)
            await proc.stdin.drain()
            proc.stdin.close()

        if proc.stdout is None:
            raise RuntimeError("Failed to capture stdout from docker exec")

        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            if proc.stderr:
                async for chunk in proc.stderr:
                    stderr_chunks.append(chunk)

        drain_task = asyncio.create_task(_drain_stderr())

        try:
            async for raw_line in proc.stdout:
                yield raw_line.decode().rstrip("\n")
        finally:
            if proc.returncode is None:
                proc.terminate()
            if not drain_task.done():
                drain_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await drain_task
            await proc.wait()

        if proc.returncode != 0:
            stderr_text = b"".join(stderr_chunks).decode().strip()
            raise RuntimeError(
                f"Command exited with code {proc.returncode}: "
                f"{stderr_text}"
            )

    async def teardown(self) -> None:
        """Stop and remove the container."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", self.container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "Failed to remove container",
                container=self.container_name,
                error=stderr.decode().strip(),
            )
        else:
            logger.info("Container removed", container=self.container_name)

    async def health_check(self) -> bool:
        """Check if the container is running.

        Returns:
            True if container is running and healthy.
        """
        proc = await asyncio.create_subprocess_exec(
            "docker", "inspect",
            "--format", "{{.State.Running}}",
            self.container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return proc.returncode == 0 and stdout.decode().strip() == "true"

    async def _image_exists(self) -> bool:
        """Check if the Docker image exists locally."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "image", "inspect", self.image,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    async def _ensure_base_image(self) -> None:
        """Build the ToB devcontainer base image if not present."""
        base_image = "tob-claude-devcontainer:latest"
        proc = await asyncio.create_subprocess_exec(
            "docker", "image", "inspect", base_image,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            return

        logger.info(
            "Building base image (first run, may take 5-15 minutes)",
            image=base_image,
        )
        script = Path(__file__).parent.parent.parent / "scripts" / "build-sandbox-base.sh"
        proc = await asyncio.create_subprocess_exec(
            "bash", str(script), "--force",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        async for line in proc.stdout:
            text = line.decode().rstrip()
            if text:
                logger.debug(text, source="sandbox-base-build")
        returncode = await proc.wait()
        if returncode != 0:
            raise RuntimeError("Failed to build base image (see logs above)")

    async def _build_image(self) -> None:
        """Build the sandbox Docker image from the in-repo Dockerfile."""
        await self._ensure_base_image()
        dockerfile_path = Path(__file__).parent / "Dockerfile"
        # Context must be repo root since Dockerfile uses COPY . and COPY amelia/
        repo_root = Path(__file__).parent.parent.parent
        logger.info("Building sandbox overlay image", image=self.image)
        proc = await asyncio.create_subprocess_exec(
            "docker", "build", "-f", str(dockerfile_path), "-t", self.image, str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        async for line in proc.stdout:
            text = line.decode().rstrip()
            if text:
                logger.debug(text, source="sandbox-overlay-build")
        returncode = await proc.wait()
        if returncode != 0:
            raise RuntimeError("Failed to build sandbox image (see logs above)")

    async def _start_container(self) -> None:
        """Start the container with sleep infinity.

        Attempts to restart an existing stopped container first. If no
        container exists, creates a new one with ``docker run``.
        """
        # Try restarting an existing stopped container first.
        restart = await asyncio.create_subprocess_exec(
            "docker", "start", self.container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await restart.wait()
        if restart.returncode == 0:
            logger.info(
                "Restarted existing container",
                container=self.container_name,
            )
            return

        cmd = [
            "docker", "run", "-d",
            "--name", self.container_name,
            "--add-host=host.docker.internal:host-gateway",
            # NET_ADMIN + NET_RAW required for iptables-based network allowlist
            # that restricts outbound connections to approved hosts only.
            "--cap-add", "NET_ADMIN",
            "--cap-add", "NET_RAW",
            "-e", f"LLM_PROXY_URL=http://host.docker.internal:{self.proxy_port}/proxy/v1",
            "-e", f"AMELIA_PROFILE={self.profile_name}",
            self.image,
            "sleep", "infinity",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to start container: {stderr.decode().strip()}"
            )
        logger.info(
            "Container started",
            container=self.container_name,
            image=self.image,
        )

    async def _wait_for_ready(self, timeout: float = 30.0) -> None:
        """Wait for the container to become healthy.

        Args:
            timeout: Maximum seconds to wait.

        Raises:
            TimeoutError: If container doesn't become healthy in time.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.health_check():
                return
            await asyncio.sleep(0.5)
        raise TimeoutError(
            f"Container {self.container_name} not ready after {timeout}s"
        )

    async def _apply_network_allowlist(self) -> None:
        """Apply iptables network allowlist if enabled.

        Generates iptables rules and executes them inside the container
        as root via the setup-network.sh script.
        """
        if not self.network_allowlist_enabled:
            return

        rules = generate_allowlist_rules(
            allowed_hosts=self.network_allowed_hosts,
        )
        logger.info(
            "Applying network allowlist",
            container=self.container_name,
            hosts=len(self.network_allowed_hosts),
        )

        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", "--user", "root", self.container_name,
            "sh", "/opt/amelia/scripts/setup-network.sh",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(input=rules.encode())
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to apply network allowlist: {stderr.decode().strip()}"
            )
        logger.info("Network allowlist applied", container=self.container_name)
