"""Docker-based sandbox provider for isolated agent execution.

Manages a single long-lived Docker container per profile. All docker
interactions use asyncio.create_subprocess_exec — no Docker SDK dependency.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

from loguru import logger


class DockerSandboxProvider:
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
    ) -> None:
        self.profile_name = profile_name
        self.image = image
        self.proxy_port = proxy_port
        self.container_name = f"amelia-sandbox-{profile_name}"

    async def ensure_running(self) -> None:
        """Ensure the sandbox container is ready. Start if not running."""
        if await self.health_check():
            return
        if not await self._image_exists():
            await self._build_image()
        await self._start_container()
        await self._wait_for_ready()

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

        assert proc.stdout is not None  # noqa: S101
        async for raw_line in proc.stdout:
            yield raw_line.decode().rstrip("\n")

        await proc.wait()
        if proc.returncode != 0:
            stderr_bytes = await proc.stderr.read() if proc.stderr else b""
            raise RuntimeError(
                f"Command exited with code {proc.returncode}: "
                f"{stderr_bytes.decode().strip()}"
            )

    async def teardown(self) -> None:
        """Stop and remove the container."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", self.container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
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

    async def _build_image(self) -> None:
        """Build the sandbox Docker image from the in-repo Dockerfile."""
        dockerfile_dir = Path(__file__).parent
        logger.info("Building sandbox image", image=self.image)
        proc = await asyncio.create_subprocess_exec(
            "docker", "build", "-t", self.image, str(dockerfile_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to build sandbox image: {stderr.decode().strip()}"
            )

    async def _start_container(self) -> None:
        """Start the container with sleep infinity."""
        cmd = [
            "docker", "run", "-d",
            "--name", self.container_name,
            "--add-host=host.docker.internal:host-gateway",
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
