"""Daytona cloud sandbox provider.

Implements the SandboxProvider protocol using Daytona's native APIs
for sandbox lifecycle and git operations, with session-based streaming
for real-time command output.
"""

from __future__ import annotations

import asyncio
import contextlib
import shlex
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

from daytona_sdk import (
    AsyncDaytona,
    AsyncSandbox,
    CreateSandboxFromImageParams,
    CreateSandboxFromSnapshotParams,
    DaytonaConfig,
    Image,
    Resources,
    SessionExecuteRequest,
)
from loguru import logger

from amelia.core.retry import with_retry
from amelia.core.types import RetryConfig
from amelia.sandbox.worktree import REPO_PATH


# Path where the standalone worker script is uploaded inside the sandbox.
WORKER_PATH = "/opt/amelia/worker.py"

# Lightweight deps needed by amelia.sandbox.worker inside the sandbox.
# These are installed into the Daytona image at build time so the worker
# can run without a pre-built GHCR image.
_WORKER_DEPS = ["deepagents", "pydantic", "loguru", "httpx", "langchain-openai"]


if TYPE_CHECKING:
    from amelia.core.types import DaytonaResources


class DaytonaSandboxProvider:
    """Sandbox provider using Daytona cloud instances.

    Uses Daytona's native APIs for lifecycle management (create/delete)
    and git operations (clone), while exposing exec_stream for worker
    process execution.

    Args:
        api_key: Daytona API key.
        api_url: Daytona API endpoint URL.
        target: Daytona target region.
        repo_url: Git remote URL to clone into the sandbox.
        branch: Git branch to clone.
        resources: Optional CPU/memory/disk resource configuration.
        image: Docker image for the sandbox (default: python:3.12-slim).
        snapshot: Optional Daytona snapshot name.  When set, the sandbox is
            created from a pre-built snapshot (fastest startup) and the
            ``image`` parameter is ignored.
        timeout: Timeout in seconds for sandbox creation and git clone.
        git_token: Optional Git access token for private repo operations.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://app.daytona.io/api",
        target: str = "us",
        repo_url: str = "",
        branch: str = "main",
        resources: DaytonaResources | None = None,
        image: str = "python:3.12-slim",
        snapshot: str | None = None,
        timeout: float = 120.0,
        retry_config: RetryConfig | None = None,
        git_token: str | None = None,
        workflow_branch: str | None = None,
        worker_env: dict[str, str] | None = None,
    ) -> None:
        self._client = AsyncDaytona(DaytonaConfig(
            api_key=api_key,
            api_url=api_url,
            target=target,
        ))
        self._target = target
        self._repo_url = repo_url
        self._branch = branch
        self._resources = resources
        self._image = image
        self._snapshot = snapshot
        self._timeout = timeout
        self._retry_config = retry_config
        self._git_token = git_token
        self._workflow_branch = workflow_branch
        self._worker_env: dict[str, str] = dict(worker_env) if worker_env else {}
        self._sandbox: AsyncSandbox | None = None

    @property
    def _git_auth(self) -> dict[str, str]:
        """Git credentials for Daytona SDK git operations."""
        if self._git_token:
            return {"username": "x-access-token", "password": self._git_token}
        return {}

    @property
    def worker_cmd(self) -> list[str]:
        """Invoke the standalone worker script uploaded to the sandbox."""
        return ["python", WORKER_PATH]

    @property
    def worker_env(self) -> dict[str, str]:
        """Environment variables needed by the worker inside the sandbox."""
        return dict(self._worker_env)

    async def _upload_worker(self, sandbox: AsyncSandbox) -> None:
        """Upload the standalone worker.py script into the sandbox."""
        from pathlib import Path  # noqa: PLC0415

        worker_src = Path(__file__).parent / "worker.py"
        content = worker_src.read_bytes()
        # Ensure parent directory exists.
        await sandbox.process.exec(f"mkdir -p {shlex.quote(str(Path(WORKER_PATH).parent))}")
        await sandbox.fs.upload_file(content, WORKER_PATH)
        logger.info("Uploaded standalone worker", path=WORKER_PATH, size=len(content))

    async def ensure_running(self) -> None:
        """Create Daytona sandbox and clone repo using native APIs.

        First call creates the sandbox and clones the repository.
        Subsequent calls are no-ops if the sandbox is healthy.
        Health checks are retried to avoid destroying a sandbox on
        transient API failures.
        """
        if self._sandbox is not None:
            # Retry health check to avoid destroying sandbox on transient failures
            for attempt in range(3):
                if await self.health_check():
                    logger.debug(
                        "Sandbox healthy, reusing",
                        sandbox_id=self._sandbox.id,
                        attempt=attempt,
                    )
                    return
                if attempt < 2:
                    logger.warning(
                        "Sandbox health check failed, retrying",
                        sandbox_id=self._sandbox.id,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(2 * (attempt + 1))

            # All retries exhausted — tear it down before replacing.
            logger.warning(
                "Sandbox unhealthy after retries, recreating",
                sandbox_id=self._sandbox.id,
            )
            with contextlib.suppress(Exception):
                await self._sandbox.delete()
            self._sandbox = None

        logger.info("Creating Daytona sandbox", target=self._target)

        resources = None
        if self._resources:
            resources = Resources(
                cpu=self._resources.cpu,
                memory=self._resources.memory,
                disk=self._resources.disk,
            )

        create_params: CreateSandboxFromSnapshotParams | CreateSandboxFromImageParams
        if self._snapshot:
            # Snapshot path: pre-built image with all deps, fastest startup.
            logger.info("Using Daytona snapshot", snapshot=self._snapshot)
            create_params = CreateSandboxFromSnapshotParams(
                snapshot=self._snapshot,
            )
        else:
            # Image path: build from base image with worker deps.
            if self._image.startswith("debian-slim"):
                if ":" in self._image:
                    version = self._image.split(":", 1)[1]
                    image = Image.debian_slim(version)  # type: ignore[arg-type]
                else:
                    image = Image.debian_slim()
            else:
                image = Image.base(self._image)

            # Ensure git and worker dependencies are available regardless of
            # the base image.  Daytona caches image layers so this only runs
            # on the first build for a given configuration.
            image = (
                image
                .run_commands(
                    "apt-get update && apt-get install -y --no-install-recommends git "
                    "&& rm -rf /var/lib/apt/lists/*"
                )
                .pip_install(*_WORKER_DEPS)
            )
            create_params = CreateSandboxFromImageParams(
                image=image,
                resources=resources,
            )

        _retryable = (ConnectionError, TimeoutError, OSError)

        created_sandbox: AsyncSandbox | None = None
        try:
            async with asyncio.timeout(self._timeout):
                if self._retry_config:
                    created_sandbox = await with_retry(
                        lambda: self._client.create(create_params),
                        self._retry_config,
                        retryable_exceptions=_retryable,
                    )
                else:
                    created_sandbox = await self._client.create(create_params)
                logger.info("Daytona sandbox created", sandbox_id=created_sandbox.id)

                if self._repo_url:
                    parsed = urlparse(self._repo_url)
                    safe_url = urlunparse(parsed._replace(netloc=parsed.hostname or parsed.netloc))
                    logger.info("Cloning repo via Daytona git API", url=safe_url)
                    if self._retry_config:
                        await with_retry(
                            lambda: created_sandbox.git.clone(
                                self._repo_url, REPO_PATH, branch=self._branch, **self._git_auth
                            ),
                            self._retry_config,
                            retryable_exceptions=_retryable,
                        )
                    else:
                        await created_sandbox.git.clone(self._repo_url, REPO_PATH, branch=self._branch, **self._git_auth)

                    # If the cloned repo is a Python package (has pyproject.toml
                    # or setup.py), install it so its modules are importable.
                    # For non-Python repos (e.g. Swift), no extra install
                    # needed — the worker has no amelia dependencies.
                    check_resp = await created_sandbox.process.exec(
                        f"test -f {REPO_PATH}/pyproject.toml || test -f {REPO_PATH}/setup.py"
                    )
                    if check_resp.exit_code == 0:
                        logger.info("Installing Python package from cloned repo")
                        install_resp = await created_sandbox.process.exec(
                            f"pip install --no-cache-dir --no-deps {REPO_PATH}"
                        )
                        if install_resp.exit_code != 0:
                            raise RuntimeError(
                                "Failed to install package from cloned repo: "
                                f"exit_code={install_resp.exit_code}, result={install_resp.result}"
                            )
                    else:
                        logger.info("Cloned repo is not a Python package, skipping pip install")

                    # Create workflow-specific branch after clone.
                    if self._workflow_branch:
                        branch_resp = await created_sandbox.process.exec(
                            f"git -C {REPO_PATH} checkout -b {shlex.quote(self._workflow_branch)}"
                        )
                        if branch_resp.exit_code != 0:
                            raise RuntimeError(
                                f"Failed to create workflow branch {self._workflow_branch!r}: "
                                f"exit_code={branch_resp.exit_code}, result={branch_resp.result}"
                            )
                        logger.info("Created workflow branch", branch=self._workflow_branch)

                # Upload the standalone worker script so the container
                # driver can invoke it without installing the amelia package.
                await self._upload_worker(created_sandbox)

                # Only persist after all setup steps succeed.
                self._sandbox = created_sandbox
        except TimeoutError:
            if created_sandbox is not None:
                with contextlib.suppress(Exception):
                    await created_sandbox.delete()
            raise TimeoutError(
                f"Daytona sandbox creation timed out after {self._timeout}s"
            ) from None
        except Exception:
            if created_sandbox is not None:
                with contextlib.suppress(Exception):
                    await created_sandbox.delete()
            raise

    def resolve_cwd(self, cwd: str) -> str:
        """Map host paths to the sandbox repo path.

        Inside the Daytona sandbox the repo is cloned to REPO_PATH
        (/workspace/repo). Any host-side path that doesn't start with
        /workspace/ is replaced with REPO_PATH so commands execute in the
        correct location.
        """
        if cwd.startswith("/workspace/"):
            return cwd
        logger.debug("Mapping host cwd to sandbox path", host_cwd=cwd, sandbox_cwd=REPO_PATH)
        return REPO_PATH

    async def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        """Execute command in sandbox, yielding stdout lines in real-time.

        Uses Daytona's session-based API with WebSocket log streaming to
        deliver output incrementally as it's produced.

        Args:
            command: Command and arguments to execute.
            cwd: Working directory inside the sandbox.
            env: Additional environment variables.
            stdin: Ignored (Daytona sessions do not support stdin).

        Yields:
            Lines of stdout output as they arrive.

        Raises:
            RuntimeError: If the sandbox is not running or command fails.
        """
        sandbox = self._sandbox
        if sandbox is None:
            raise RuntimeError("Sandbox not running — call ensure_running() first")

        if stdin:
            logger.warning("Daytona exec_stream does not support stdin — use write_file() instead")

        # Build command string with cwd/env baked in (session API has no
        # cwd/env params).
        cmd_str = shlex.join(command)
        if env:
            exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
            cmd_str = f"export {exports} && {cmd_str}"
        if cwd:
            cmd_str = f"cd {shlex.quote(cwd)} && {cmd_str}"

        session_id = f"amelia-{uuid.uuid4().hex[:12]}"
        await sandbox.process.create_session(session_id)

        try:
            resp = await sandbox.process.execute_session_command(
                session_id,
                SessionExecuteRequest(command=cmd_str, run_async=True),
            )
        except Exception:
            with contextlib.suppress(Exception):
                await sandbox.process.delete_session(session_id)
            raise
        cmd_id = resp.cmd_id

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        stderr_chunks: list[str] = []

        async def on_stdout(chunk: str) -> None:
            await queue.put(chunk)

        async def on_stderr(chunk: str) -> None:
            stderr_chunks.append(chunk)
            logger.debug("Daytona stderr chunk", size=len(chunk))

        async def stream_logs() -> None:
            try:
                await sandbox.process.get_session_command_logs_async(
                    session_id, cmd_id, on_stdout, on_stderr,
                )
            finally:
                await queue.put(None)

        log_task = asyncio.create_task(stream_logs())

        # Buffer partial lines; yield only complete newline-delimited lines.
        buf = ""
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    yield line
            # Yield any remaining partial line.
            if buf:
                yield buf
        finally:
            if not log_task.done():
                log_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await log_task

            # Propagate any exception from the log streaming task.
            if log_task.done() and not log_task.cancelled():
                task_exc = log_task.exception()
                if task_exc is not None:
                    raise task_exc

            # Check exit code before deleting the session.
            try:
                cmd_info = await sandbox.process.get_session_command(
                    session_id, cmd_id,
                )
                if cmd_info.exit_code is not None and cmd_info.exit_code != 0:
                    stderr_text = "".join(stderr_chunks).strip()
                    detail = f"Command exited with code {cmd_info.exit_code}: {cmd_str}"
                    if stderr_text:
                        # Limit stderr to last 2000 chars to avoid huge error messages.
                        tail = stderr_text[-2000:]
                        detail += f"\n\nStderr:\n{tail}"
                    raise RuntimeError(detail)
            finally:
                try:
                    await sandbox.process.delete_session(session_id)
                except Exception as exc:
                    logger.debug("Failed to delete Daytona session", session_id=session_id, error=exc)

    async def write_file(self, path: str, content: bytes) -> None:
        """Write content to a file inside the sandbox via Daytona FS API."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not running — call ensure_running() first")
        await self._sandbox.fs.upload_file(content, path)

    async def git_push(self, path: str) -> None:
        """Push via Daytona SDK with credentials."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not running — call ensure_running() first")
        await self._sandbox.git.push(path, **self._git_auth)

    async def git_fetch(self, path: str) -> None:
        """Fetch via Daytona SDK with credentials."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not running — call ensure_running() first")
        await self._sandbox.git.pull(path, **self._git_auth)

    async def teardown(self) -> None:
        """Delete the ephemeral Daytona sandbox."""
        if self._sandbox is None:
            return
        logger.info("Tearing down Daytona sandbox", sandbox_id=self._sandbox.id)
        try:
            await self._sandbox.delete()
        except Exception as exc:
            logger.warning("Failed to delete Daytona sandbox", sandbox_id=self._sandbox.id, error=exc)
        finally:
            self._sandbox = None

    async def health_check(self) -> bool:
        """Check if the sandbox is responsive.

        Returns:
            True if sandbox exists and responds to a trivial command.
        """
        if self._sandbox is None:
            return False
        try:
            response = await self._sandbox.process.exec("true")
            return bool(response.exit_code == 0)
        except Exception as e:
            logger.debug("Daytona health check failed", error=e)
            return False
