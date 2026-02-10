# Sandbox Container + Worker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement PR 2 (#410) — Dockerfile, `DockerSandboxProvider`, worker entrypoint, and git worktree management for the DevContainer sandbox.

**Architecture:** The worker runs inside a Docker container and communicates with the host via JSON lines on stdout. `DockerSandboxProvider` implements the `SandboxProvider` protocol from PR 1, managing container lifecycle via `docker` CLI commands. Git worktrees provide per-workflow isolation inside the container. The `USAGE` message type is added to `AgenticMessage` so the worker can report accumulated token usage back to the host.

**Tech Stack:** Python 3.12+, Docker, asyncio, pydantic, deepagents, loguru, httpx

**Design Doc:** `docs/plans/2026-02-08-devcontainer-sandbox-design.md` (PR 2 section, lines 317-509)

---

### Task 1: Add USAGE message type to AgenticMessage

**Files:**
- Modify: `amelia/drivers/base.py:30-36` (AgenticMessageType enum)
- Modify: `amelia/drivers/base.py:39-75` (AgenticMessage model)
- Test: `tests/unit/sandbox/test_worker_protocol.py`

**Context:** The worker protocol requires a final `USAGE` message with accumulated `DriverUsage`. This message type must exist before the worker or `ContainerDriver` can use it. The `to_workflow_event()` mapping does NOT need a USAGE entry — it is consumed internally by the driver, never reaching the event bus.

**Step 1: Write the failing test**

```python
"""Tests for the USAGE message type added to the worker protocol."""

import pytest
from pydantic import ValidationError

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
)


class TestUsageMessageType:
    """Tests for USAGE enum value and AgenticMessage.usage field."""

    def test_usage_enum_value_exists(self):
        assert AgenticMessageType.USAGE == "usage"

    def test_usage_enum_is_valid_string(self):
        assert AgenticMessageType("usage") == AgenticMessageType.USAGE

    def test_agentic_message_usage_field_default_none(self):
        msg = AgenticMessage(type=AgenticMessageType.RESULT, content="done")
        assert msg.usage is None

    def test_agentic_message_with_usage(self):
        usage = DriverUsage(input_tokens=100, output_tokens=50, model="test-model")
        msg = AgenticMessage(
            type=AgenticMessageType.USAGE,
            usage=usage,
        )
        assert msg.type == AgenticMessageType.USAGE
        assert msg.usage is not None
        assert msg.usage.input_tokens == 100
        assert msg.usage.output_tokens == 50

    def test_usage_message_json_roundtrip(self):
        usage = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.003,
            model="anthropic/claude-sonnet-4-5",
        )
        msg = AgenticMessage(type=AgenticMessageType.USAGE, usage=usage)
        json_str = msg.model_dump_json()
        restored = AgenticMessage.model_validate_json(json_str)
        assert restored.type == AgenticMessageType.USAGE
        assert restored.usage == usage

    def test_usage_message_not_in_workflow_event_mapping(self):
        """USAGE messages should raise KeyError in to_workflow_event — they are
        consumed by the driver, never reaching the event bus."""
        msg = AgenticMessage(type=AgenticMessageType.USAGE)
        with pytest.raises(KeyError):
            msg.to_workflow_event(workflow_id="wf-1", agent="developer")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/sandbox/test_worker_protocol.py -v`
Expected: FAIL — `AgenticMessageType` has no `USAGE` member, `AgenticMessage` has no `usage` field.

**Step 3: Write minimal implementation**

In `amelia/drivers/base.py`, add `USAGE` to the enum and `usage` field to the model:

```python
class AgenticMessageType(StrEnum):
    """Types of messages yielded during agentic execution."""

    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RESULT = "result"
    USAGE = "usage"


class AgenticMessage(BaseModel):
    # ... existing fields ...
    usage: DriverUsage | None = None  # Populated only for type=USAGE
```

No change to `to_workflow_event()` — the existing `type_mapping` dict will raise `KeyError` for `USAGE`, which is correct (the driver consumes USAGE messages before they reach the event bus).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/sandbox/test_worker_protocol.py -v`
Expected: PASS

**Step 5: Run existing tests to verify no regressions**

Run: `uv run pytest tests/unit/drivers/ -v`
Expected: All PASS — the new field defaults to `None` and the new enum value doesn't affect existing code.

**Step 6: Commit**

```bash
git add amelia/drivers/base.py tests/unit/sandbox/test_worker_protocol.py
git commit -m "feat(sandbox): add USAGE message type to AgenticMessage for worker protocol"
```

---

### Task 2: DockerSandboxProvider

**Files:**
- Create: `amelia/sandbox/docker.py`
- Test: `tests/unit/sandbox/test_docker_provider.py`

**Context:** `DockerSandboxProvider` implements the `SandboxProvider` protocol from PR 1. It manages a single long-lived container per profile using `docker` CLI commands. All docker interactions go through `asyncio.create_subprocess_exec` — no Docker SDK dependency. The container runs with `sleep infinity` and work happens via `docker exec`.

**Step 1: Write the failing tests**

```python
"""Tests for DockerSandboxProvider."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.sandbox.docker import DockerSandboxProvider
from amelia.sandbox.provider import SandboxProvider


class TestDockerProviderProtocol:
    """DockerSandboxProvider satisfies SandboxProvider protocol."""

    def test_satisfies_protocol(self):
        provider = DockerSandboxProvider(profile_name="test")
        assert isinstance(provider, SandboxProvider)

    def test_container_name(self):
        provider = DockerSandboxProvider(profile_name="work")
        assert provider.container_name == "amelia-sandbox-work"

    def test_default_image(self):
        provider = DockerSandboxProvider(profile_name="test")
        assert provider.image == "amelia-sandbox:latest"

    def test_custom_image(self):
        provider = DockerSandboxProvider(profile_name="test", image="custom:v1")
        assert provider.image == "custom:v1"


class TestHealthCheck:
    """Tests for health_check() — inspects container state."""

    @pytest.fixture
    def provider(self):
        return DockerSandboxProvider(profile_name="test")

    async def test_healthy_container(self, provider):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"true\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await provider.health_check()

        assert result is True
        args = mock_exec.call_args[0]
        assert "docker" in args
        assert "inspect" in args

    async def test_unhealthy_container(self, provider):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"false\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await provider.health_check()

        assert result is False

    async def test_missing_container(self, provider):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"No such object")
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await provider.health_check()

        assert result is False


class TestExecStream:
    """Tests for exec_stream() — runs commands via docker exec."""

    @pytest.fixture
    def provider(self):
        return DockerSandboxProvider(profile_name="test")

    async def test_streams_stdout_lines(self, provider):
        lines = [b"line1\n", b"line2\n", b"line3\n"]

        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: aiter(lines)
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = [line async for line in provider.exec_stream(["echo", "hello"])]

        assert result == ["line1", "line2", "line3"]

    async def test_passes_cwd(self, provider):
        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: aiter([])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            _ = [line async for line in provider.exec_stream(
                ["ls"], cwd="/workspace/worktrees/issue-1"
            )]

        args = mock_exec.call_args[0]
        assert "--workdir" in args
        assert "/workspace/worktrees/issue-1" in args

    async def test_nonzero_exit_raises(self, provider):
        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: aiter([b"output\n"])
        mock_proc.wait = AsyncMock(return_value=1)
        mock_proc.returncode = 1
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"error details")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="exited with code 1"):
                _ = [line async for line in provider.exec_stream(["false"])]


class TestTeardown:
    """Tests for teardown() — removes the container."""

    async def test_removes_container(self):
        provider = DockerSandboxProvider(profile_name="test")
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await provider.teardown()

        args = mock_exec.call_args[0]
        assert "docker" in args
        assert "rm" in args
        assert "-f" in args
        assert "amelia-sandbox-test" in args


class TestEnsureRunning:
    """Tests for ensure_running() — starts container if not healthy."""

    async def test_noop_when_healthy(self):
        provider = DockerSandboxProvider(profile_name="test")
        provider.health_check = AsyncMock(return_value=True)
        provider._build_image = AsyncMock()
        provider._start_container = AsyncMock()

        await provider.ensure_running()

        provider.health_check.assert_awaited_once()
        provider._build_image.assert_not_awaited()
        provider._start_container.assert_not_awaited()

    async def test_builds_and_starts_when_not_healthy(self):
        provider = DockerSandboxProvider(profile_name="test")
        provider.health_check = AsyncMock(return_value=False)
        provider._image_exists = AsyncMock(return_value=False)
        provider._build_image = AsyncMock()
        provider._start_container = AsyncMock()
        provider._wait_for_ready = AsyncMock()

        await provider.ensure_running()

        provider._build_image.assert_awaited_once()
        provider._start_container.assert_awaited_once()

    async def test_skips_build_when_image_exists(self):
        provider = DockerSandboxProvider(profile_name="test")
        provider.health_check = AsyncMock(return_value=False)
        provider._image_exists = AsyncMock(return_value=True)
        provider._build_image = AsyncMock()
        provider._start_container = AsyncMock()
        provider._wait_for_ready = AsyncMock()

        await provider.ensure_running()

        provider._build_image.assert_not_awaited()
        provider._start_container.assert_awaited_once()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_docker_provider.py -v`
Expected: FAIL — `amelia.sandbox.docker` does not exist.

**Step 3: Write minimal implementation**

```python
"""Docker-based sandbox provider for isolated agent execution.

Manages a single long-lived Docker container per profile. All docker
interactions use asyncio.create_subprocess_exec — no Docker SDK dependency.
"""

from __future__ import annotations

import asyncio
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
        stdout, stderr = await proc.communicate()
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
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if await self.health_check():
                return
            await asyncio.sleep(0.5)
        raise TimeoutError(
            f"Container {self.container_name} not ready after {timeout}s"
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/sandbox/test_docker_provider.py -v`
Expected: PASS

**Step 5: Run full sandbox test suite**

Run: `uv run pytest tests/unit/sandbox/ -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add amelia/sandbox/docker.py tests/unit/sandbox/test_docker_provider.py
git commit -m "feat(sandbox): add DockerSandboxProvider for container lifecycle management"
```

---

### Task 3: Git worktree management

**Files:**
- Create: `amelia/sandbox/worktree.py`
- Test: `tests/unit/sandbox/test_worktree.py`

**Context:** Each workflow gets an isolated git worktree inside the container. A bare clone at `/workspace/repo` is shared across workflows. Worktrees are created under `/workspace/worktrees/{workflow_id}`. All git commands run inside the container via the `SandboxProvider.exec_stream()` interface — the worktree manager does not call docker directly.

**Step 1: Write the failing tests**

```python
"""Tests for git worktree management inside sandbox containers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from amelia.sandbox.worktree import WorktreeManager


class TestWorktreeManager:
    """Tests for WorktreeManager lifecycle operations."""

    @pytest.fixture
    def mock_provider(self):
        """Mock SandboxProvider that records exec_stream calls."""
        provider = AsyncMock()
        provider.exec_stream = AsyncMock()

        async def fake_exec_stream(command, **kwargs):
            for item in []:
                yield item

        provider.exec_stream.side_effect = fake_exec_stream
        return provider

    @pytest.fixture
    def manager(self, mock_provider):
        return WorktreeManager(
            provider=mock_provider,
            repo_url="https://github.com/org/repo.git",
        )

    async def test_setup_repo_clones_bare_on_first_use(self, manager, mock_provider):
        await manager.setup_repo()

        calls = mock_provider.exec_stream.call_args_list
        # First call should be git clone --bare
        first_cmd = calls[0][0][0]
        assert "clone" in first_cmd
        assert "--bare" in first_cmd
        assert "https://github.com/org/repo.git" in first_cmd

    async def test_setup_repo_fetches_on_subsequent_use(self, manager, mock_provider):
        manager._repo_initialized = True
        await manager.setup_repo()

        calls = mock_provider.exec_stream.call_args_list
        first_cmd = calls[0][0][0]
        assert "fetch" in first_cmd

    async def test_create_worktree_returns_path(self, manager, mock_provider):
        manager._repo_initialized = True
        path = await manager.create_worktree("issue-123", "main")

        assert path == "/workspace/worktrees/issue-123"
        calls = mock_provider.exec_stream.call_args_list
        cmd = calls[-1][0][0]
        assert "worktree" in cmd
        assert "add" in cmd

    async def test_remove_worktree(self, manager, mock_provider):
        await manager.remove_worktree("issue-123")

        calls = mock_provider.exec_stream.call_args_list
        cmd = calls[0][0][0]
        assert "worktree" in cmd
        assert "remove" in cmd

    async def test_push_worktree(self, manager, mock_provider):
        await manager.push("issue-123")

        calls = mock_provider.exec_stream.call_args_list
        cmd = calls[0][0][0]
        assert "push" in cmd
        assert "origin" in cmd
        assert "issue-123" in cmd
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_worktree.py -v`
Expected: FAIL — `amelia.sandbox.worktree` does not exist.

**Step 3: Write minimal implementation**

```python
"""Git worktree lifecycle management inside sandbox containers.

All git commands run inside the container via the SandboxProvider interface.
The worktree manager does not call docker directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from amelia.sandbox.provider import SandboxProvider

# Container filesystem layout
REPO_PATH = "/workspace/repo"
WORKTREES_PATH = "/workspace/worktrees"


class WorktreeManager:
    """Manages git worktrees inside a sandbox container.

    Uses a bare clone at /workspace/repo as the shared base. Each workflow
    gets a worktree under /workspace/worktrees/{workflow_id}.

    Args:
        provider: Sandbox provider for executing commands.
        repo_url: Git repository URL to clone.
    """

    def __init__(self, provider: SandboxProvider, repo_url: str) -> None:
        self._provider = provider
        self._repo_url = repo_url
        self._repo_initialized = False

    async def _run(self, command: list[str], **kwargs: object) -> list[str]:
        """Execute command and collect all output lines.

        Args:
            command: Command and arguments.
            **kwargs: Passed to provider.exec_stream().

        Returns:
            List of stdout lines.
        """
        lines: list[str] = []
        async for line in self._provider.exec_stream(command, **kwargs):
            lines.append(line)
        return lines

    async def setup_repo(self) -> None:
        """Ensure the bare clone exists and is up to date.

        First call clones the repo. Subsequent calls fetch latest.
        """
        if not self._repo_initialized:
            logger.info("Cloning bare repo", url=self._repo_url)
            await self._run(
                ["git", "clone", "--bare", self._repo_url, REPO_PATH],
            )
            self._repo_initialized = True
        else:
            logger.debug("Fetching latest from origin")
            await self._run(
                ["git", "-C", REPO_PATH, "fetch", "origin"],
            )

    async def create_worktree(
        self, workflow_id: str, base_branch: str = "main"
    ) -> str:
        """Create a git worktree for a workflow.

        Args:
            workflow_id: Identifier for the workflow (used as branch and dir name).
            base_branch: Remote branch to base the worktree on.

        Returns:
            Absolute path to the worktree inside the container.
        """
        worktree_path = f"{WORKTREES_PATH}/{workflow_id}"
        await self._run([
            "git", "-C", REPO_PATH, "worktree", "add",
            worktree_path, "-b", workflow_id, f"origin/{base_branch}",
        ])
        logger.info("Created worktree", path=worktree_path, branch=workflow_id)
        return worktree_path

    async def remove_worktree(self, workflow_id: str) -> None:
        """Remove a worktree after workflow completion.

        Args:
            workflow_id: Identifier for the workflow.
        """
        worktree_path = f"{WORKTREES_PATH}/{workflow_id}"
        await self._run([
            "git", "-C", REPO_PATH, "worktree", "remove", worktree_path,
        ])
        logger.info("Removed worktree", path=worktree_path)

    async def push(self, workflow_id: str) -> None:
        """Push worktree branch to remote.

        Args:
            workflow_id: Branch name to push.
        """
        worktree_path = f"{WORKTREES_PATH}/{workflow_id}"
        await self._run(
            ["git", "push", "origin", workflow_id],
            cwd=worktree_path,
        )
        logger.info("Pushed branch", branch=workflow_id)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/sandbox/test_worktree.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/sandbox/worktree.py tests/unit/sandbox/test_worktree.py
git commit -m "feat(sandbox): add git worktree lifecycle management"
```

---

### Task 4: Worker entrypoint

**Files:**
- Create: `amelia/sandbox/worker.py`
- Test: `tests/unit/sandbox/test_worker.py`

**Context:** The worker is the Python entrypoint that runs inside the container. It receives a prompt via `--prompt-file`, runs a DeepAgents agent (agentic mode) or a single-turn LLM call (generate mode), and streams `AgenticMessage` objects as JSON lines to stdout. Loguru output goes to stderr. The worker uses `LLM_PROXY_URL` env var to route LLM calls through the host proxy.

The worker has two modes:
- `agentic`: Full tool-using agent execution (DeepAgents + LocalSandbox)
- `generate`: Single-turn structured output (ToolStrategy with optional schema)

The worker emits a final `USAGE` message with accumulated token usage before exiting.

**Step 1: Write the failing tests**

```python
"""Tests for the sandbox worker entrypoint."""

from __future__ import annotations

import json
import sys
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage


class TestWorkerEmitLine:
    """Tests for the JSON-line emission helper."""

    def test_emit_line_writes_json_to_stdout(self):
        from amelia.sandbox.worker import _emit_line

        buf = StringIO()
        msg = AgenticMessage(type=AgenticMessageType.RESULT, content="done")
        _emit_line(msg, file=buf)

        line = buf.getvalue().strip()
        parsed = json.loads(line)
        assert parsed["type"] == "result"
        assert parsed["content"] == "done"

    def test_emit_line_one_line_per_message(self):
        from amelia.sandbox.worker import _emit_line

        buf = StringIO()
        _emit_line(AgenticMessage(type=AgenticMessageType.THINKING, content="hmm"), file=buf)
        _emit_line(AgenticMessage(type=AgenticMessageType.RESULT, content="ok"), file=buf)

        lines = buf.getvalue().strip().split("\n")
        assert len(lines) == 2


class TestWorkerParseArgs:
    """Tests for CLI argument parsing."""

    def test_agentic_mode(self):
        from amelia.sandbox.worker import _parse_args

        args = _parse_args([
            "agentic",
            "--prompt-file", "/tmp/prompt.txt",
            "--cwd", "/workspace/worktrees/issue-1",
            "--model", "anthropic/claude-sonnet-4-5",
        ])
        assert args.mode == "agentic"
        assert args.prompt_file == "/tmp/prompt.txt"
        assert args.cwd == "/workspace/worktrees/issue-1"
        assert args.model == "anthropic/claude-sonnet-4-5"

    def test_generate_mode_with_schema(self):
        from amelia.sandbox.worker import _parse_args

        args = _parse_args([
            "generate",
            "--prompt-file", "/tmp/prompt.txt",
            "--model", "anthropic/claude-sonnet-4-5",
            "--schema", "amelia.agents.schemas.evaluator:EvaluationOutput",
        ])
        assert args.mode == "generate"
        assert args.schema == "amelia.agents.schemas.evaluator:EvaluationOutput"

    def test_agentic_mode_with_instructions(self):
        from amelia.sandbox.worker import _parse_args

        args = _parse_args([
            "agentic",
            "--prompt-file", "/tmp/prompt.txt",
            "--cwd", "/workspace",
            "--model", "test-model",
            "--instructions", "Be concise.",
        ])
        assert args.instructions == "Be concise."


class TestWorkerSchemaImport:
    """Tests for dynamic schema class import."""

    def test_import_known_schema(self):
        from amelia.sandbox.worker import _import_schema

        cls = _import_schema("amelia.agents.schemas.evaluator:EvaluationOutput")
        from amelia.agents.schemas.evaluator import EvaluationOutput

        assert cls is EvaluationOutput

    def test_import_invalid_format_raises(self):
        from amelia.sandbox.worker import _import_schema

        with pytest.raises(ValueError, match="must be 'module:ClassName'"):
            _import_schema("no_colon_here")

    def test_import_nonexistent_module_raises(self):
        from amelia.sandbox.worker import _import_schema

        with pytest.raises(ImportError):
            _import_schema("nonexistent.module:Foo")


class TestWorkerUsageEmission:
    """Tests for final USAGE message emission."""

    def test_emit_usage(self):
        from amelia.sandbox.worker import _emit_usage

        buf = StringIO()
        usage = DriverUsage(input_tokens=100, output_tokens=50)
        _emit_usage(usage, file=buf)

        line = buf.getvalue().strip()
        parsed = AgenticMessage.model_validate_json(line)
        assert parsed.type == AgenticMessageType.USAGE
        assert parsed.usage is not None
        assert parsed.usage.input_tokens == 100
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_worker.py -v`
Expected: FAIL — `amelia.sandbox.worker` does not exist.

**Step 3: Write minimal implementation**

```python
"""Sandbox worker entrypoint — runs inside the container.

Receives a prompt, runs a DeepAgents agent or single-turn LLM call,
and streams AgenticMessage objects as JSON lines to stdout.

Usage:
    python -m amelia.sandbox.worker agentic --prompt-file /tmp/p.txt --cwd /workspace --model m
    python -m amelia.sandbox.worker generate --prompt-file /tmp/p.txt --model m [--schema mod:Cls]
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
import time
from typing import IO, Any, TextIO

from loguru import logger
from pydantic import BaseModel

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
)

# Route loguru to stderr so stdout is reserved for JSON lines
logger.remove()
logger.add(sys.stderr, level="DEBUG")


def _emit_line(msg: AgenticMessage, file: TextIO = sys.stdout) -> None:
    """Write a single AgenticMessage as a JSON line to the given stream.

    Args:
        msg: Message to serialize.
        file: Output stream (default: stdout).
    """
    file.write(msg.model_dump_json() + "\n")
    file.flush()


def _emit_usage(usage: DriverUsage, file: TextIO = sys.stdout) -> None:
    """Emit the final USAGE message.

    Args:
        usage: Accumulated usage data.
        file: Output stream.
    """
    msg = AgenticMessage(type=AgenticMessageType.USAGE, usage=usage)
    _emit_line(msg, file=file)


def _import_schema(schema_path: str) -> type[BaseModel]:
    """Dynamically import a schema class from a 'module:ClassName' path.

    Args:
        schema_path: Fully qualified path like 'amelia.agents.schemas.evaluator:EvaluationOutput'.

    Returns:
        The imported Pydantic model class.

    Raises:
        ValueError: If format is not 'module:ClassName'.
        ImportError: If module cannot be imported.
        AttributeError: If class doesn't exist in the module.
    """
    if ":" not in schema_path:
        raise ValueError(
            f"Schema path must be 'module:ClassName', got: '{schema_path}'"
        )
    module_path, class_name = schema_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse worker CLI arguments.

    Args:
        argv: Argument list (default: sys.argv[1:]).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Amelia sandbox worker",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    # Shared arguments
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--prompt-file", required=True, help="Path to prompt file")
    shared.add_argument("--model", required=True, help="LLM model identifier")

    # agentic subcommand
    agentic = sub.add_parser("agentic", parents=[shared])
    agentic.add_argument("--cwd", required=True, help="Working directory")
    agentic.add_argument("--instructions", help="System instructions")

    # generate subcommand
    generate = sub.add_parser("generate", parents=[shared])
    generate.add_argument("--schema", help="Schema as module:ClassName")

    return parser.parse_args(argv)


async def _run_agentic(args: argparse.Namespace) -> None:
    """Run agentic mode — full tool-using agent execution.

    Args:
        args: Parsed CLI arguments.
    """
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from deepagents.backends.protocol import ExecuteResponse, SandboxBackendProtocol
    from langchain.chat_models import init_chat_model
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from amelia.core.constants import normalize_tool_name

    prompt = _read_prompt(args.prompt_file)
    proxy_url = os.environ.get("LLM_PROXY_URL")
    base_url = proxy_url if proxy_url else None

    chat_model = _create_worker_chat_model(args.model, base_url=base_url)
    backend = FilesystemBackend(cwd=args.cwd)

    agent = create_deep_agent(
        chat_model=chat_model,
        backend=backend,
        instructions=args.instructions,
    )

    start_time = time.monotonic()
    total_input = 0
    total_output = 0
    num_turns = 0

    async for chunk in agent.astream(
        {"messages": [HumanMessage(content=prompt)]},
        stream_mode="values",
    ):
        messages = chunk.get("messages", [])
        if not messages:
            continue
        message = messages[-1]
        num_turns += 1

        # Track usage
        if hasattr(message, "usage_metadata") and message.usage_metadata:
            total_input += message.usage_metadata.get("input_tokens", 0)
            total_output += message.usage_metadata.get("output_tokens", 0)

        if isinstance(message, AIMessage):
            # Emit thinking for text content
            content = message.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        _emit_line(AgenticMessage(
                            type=AgenticMessageType.THINKING,
                            content=block["text"],
                            model=args.model,
                        ))
            elif isinstance(content, str) and content:
                _emit_line(AgenticMessage(
                    type=AgenticMessageType.THINKING,
                    content=content,
                    model=args.model,
                ))

            # Emit tool calls
            for tc in message.tool_calls:
                _emit_line(AgenticMessage(
                    type=AgenticMessageType.TOOL_CALL,
                    tool_name=normalize_tool_name(tc["name"]),
                    tool_input=tc.get("args", {}),
                    tool_call_id=tc.get("id"),
                    model=args.model,
                ))

        elif isinstance(message, ToolMessage):
            _emit_line(AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=normalize_tool_name(message.name or "unknown"),
                tool_output=str(message.content)[:10000],
                tool_call_id=message.tool_call_id,
                is_error=message.status == "error" if hasattr(message, "status") else False,
                model=args.model,
            ))

    # Final result — last AI message content
    final_content = ""
    for msg in reversed(chunk.get("messages", [])):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str):
                final_content = content
            elif isinstance(content, list):
                final_content = " ".join(
                    b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"
                )
            break

    _emit_line(AgenticMessage(
        type=AgenticMessageType.RESULT,
        content=final_content,
        model=args.model,
    ))

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit_usage(DriverUsage(
        input_tokens=total_input or None,
        output_tokens=total_output or None,
        duration_ms=duration_ms,
        num_turns=num_turns,
        model=args.model,
    ))


async def _run_generate(args: argparse.Namespace) -> None:
    """Run generate mode — single-turn structured output.

    Args:
        args: Parsed CLI arguments.
    """
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langchain.agents.structured_output import ToolStrategy
    from langchain_core.messages import HumanMessage

    prompt = _read_prompt(args.prompt_file)
    proxy_url = os.environ.get("LLM_PROXY_URL")
    base_url = proxy_url if proxy_url else None

    chat_model = _create_worker_chat_model(args.model, base_url=base_url)

    schema = _import_schema(args.schema) if args.schema else None

    start_time = time.monotonic()

    if schema:
        agent = create_deep_agent(
            chat_model=chat_model,
            backend=FilesystemBackend(cwd="/tmp"),
            tool_strategy=ToolStrategy(schema=schema),
        )
        result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        messages = result.get("messages", [])

        # Extract structured output from the last AI message
        output = None
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                try:
                    output = schema.model_validate_json(
                        msg.content if isinstance(msg.content, str) else str(msg.content)
                    )
                except Exception:
                    output = msg.content
                break

        content = output.model_dump_json() if isinstance(output, BaseModel) else str(output)
    else:
        result = chat_model.invoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)

    # Track usage
    total_input = 0
    total_output = 0
    for msg in result.get("messages", []) if isinstance(result, dict) else [result]:
        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            total_input += msg.usage_metadata.get("input_tokens", 0)
            total_output += msg.usage_metadata.get("output_tokens", 0)

    _emit_line(AgenticMessage(
        type=AgenticMessageType.RESULT,
        content=content,
        model=args.model,
    ))

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit_usage(DriverUsage(
        input_tokens=total_input or None,
        output_tokens=total_output or None,
        duration_ms=duration_ms,
        model=args.model,
    ))


def _read_prompt(path: str) -> str:
    """Read prompt from file.

    Args:
        path: Path to the prompt file.

    Returns:
        Prompt text content.
    """
    with open(path) as f:
        return f.read()


def _create_worker_chat_model(model: str, base_url: str | None = None) -> Any:
    """Create a chat model for the worker, using proxy URL if available.

    Args:
        model: Model identifier.
        base_url: Optional proxy base URL.

    Returns:
        Configured LangChain chat model.
    """
    from langchain.chat_models import init_chat_model

    if base_url:
        # Route through proxy — use openai-compatible interface
        return init_chat_model(
            model=model,
            model_provider="openai",
            base_url=base_url,
            api_key="proxy-managed",
        )
    return init_chat_model(model)


async def _main() -> None:
    """Worker entrypoint."""
    args = _parse_args()
    if args.mode == "agentic":
        await _run_agentic(args)
    elif args.mode == "generate":
        await _run_generate(args)


if __name__ == "__main__":
    asyncio.run(_main())
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/sandbox/test_worker.py -v`
Expected: PASS

**Step 5: Run full sandbox test suite**

Run: `uv run pytest tests/unit/sandbox/ -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add amelia/sandbox/worker.py tests/unit/sandbox/test_worker.py
git commit -m "feat(sandbox): add worker entrypoint for container-side execution"
```

---

### Task 5: Dockerfile, devcontainer.json, and credential helper

**Files:**
- Create: `amelia/sandbox/Dockerfile`
- Create: `amelia/sandbox/devcontainer.json`
- Create: `amelia/sandbox/scripts/credential-helper.sh`

**Context:** The Dockerfile extends the Trail of Bits devcontainer base image. It installs the amelia package with `--no-deps` (for schema/message imports) plus only the lightweight deps the worker needs. The credential helper is a bash script that git calls to get credentials from the host proxy. No automated tests for these — they're validated in integration testing.

**Step 1: Create the credential helper script**

```bash
#!/bin/bash
# Git credential helper that routes through the Amelia host proxy.
# Installed as: git config --system credential.helper '/opt/amelia/scripts/credential-helper.sh'
#
# Git sends credential request data on stdin. This script forwards it
# to the host proxy and returns the credentials.

set -euo pipefail

PROXY_URL="${LLM_PROXY_URL:-http://host.docker.internal:8430/proxy/v1}"
PROFILE="${AMELIA_PROFILE:-default}"

curl -sf \
    -H "X-Amelia-Profile: ${PROFILE}" \
    "${PROXY_URL}/git/credentials" \
    --data-binary @/dev/stdin
```

**Step 2: Create the Dockerfile**

```dockerfile
# Amelia sandbox container for isolated agent execution.
# Based on Trail of Bits claude-code-devcontainer with Amelia worker overlay.
FROM ghcr.io/trailofbits/claude-code-devcontainer:latest

# Install amelia package (code only, no transitive deps) and worker dependencies.
# This gives the worker access to:
#   amelia.drivers.base (AgenticMessage, DriverUsage)
#   amelia.agents.schemas (EvaluationOutput, MarkdownPlanOutput, etc.)
#   amelia.sandbox.worker (entrypoint)
# Heavy deps (langgraph, fastapi, asyncpg, langchain) are NOT installed.
COPY . /tmp/amelia/
RUN cd /tmp/amelia \
    && uv pip install --system --no-deps . \
    && uv pip install --system deepagents pydantic loguru httpx \
    && rm -rf /tmp/amelia

# Install credential helper
COPY amelia/sandbox/scripts/ /opt/amelia/scripts/
RUN chmod +x /opt/amelia/scripts/*.sh

# Configure git to use credential helper
RUN git config --system credential.helper \
    '/opt/amelia/scripts/credential-helper.sh'

USER vscode
WORKDIR /workspace
```

**Step 3: Create devcontainer.json**

```json
{
  "name": "Amelia Sandbox",
  "build": {
    "dockerfile": "Dockerfile",
    "context": "../.."
  },
  "remoteUser": "vscode",
  "workspaceFolder": "/workspace",
  "features": {},
  "customizations": {
    "vscode": {
      "settings": {
        "terminal.integrated.defaultProfile.linux": "bash"
      }
    }
  }
}
```

**Step 4: Commit**

```bash
mkdir -p amelia/sandbox/scripts
git add amelia/sandbox/Dockerfile amelia/sandbox/devcontainer.json amelia/sandbox/scripts/credential-helper.sh
git commit -m "feat(sandbox): add Dockerfile, devcontainer.json, and credential helper"
```

---

### Task 6: Update sandbox module exports and verify

**Files:**
- Modify: `amelia/sandbox/__init__.py`

**Context:** Update the sandbox package `__init__.py` to export the new components from PR 2. This makes imports clean for downstream consumers (PR 3's `ContainerDriver` and `factory.py`).

**Step 1: Update exports**

Update `amelia/sandbox/__init__.py`:

```python
"""Sandbox execution infrastructure for isolated agent environments."""

from amelia.sandbox.docker import DockerSandboxProvider
from amelia.sandbox.provider import SandboxProvider
from amelia.sandbox.proxy import ProviderConfig
from amelia.sandbox.worktree import WorktreeManager


__all__ = [
    "DockerSandboxProvider",
    "ProviderConfig",
    "SandboxProvider",
    "WorktreeManager",
]
```

**Step 2: Run type checks and full test suite**

Run: `uv run mypy amelia/sandbox/`
Expected: PASS (or only pre-existing issues)

Run: `uv run pytest tests/unit/sandbox/ -v`
Expected: All PASS

Run: `uv run ruff check amelia/sandbox/`
Expected: PASS

**Step 3: Commit**

```bash
git add amelia/sandbox/__init__.py
git commit -m "feat(sandbox): export DockerSandboxProvider and WorktreeManager from package"
```

---

### Task 7: Final verification

**Files:** None (verification only)

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS — no regressions in existing tests.

**Step 2: Run linting**

Run: `uv run ruff check amelia/ tests/`
Expected: PASS

**Step 3: Run type checking**

Run: `uv run mypy amelia/`
Expected: PASS (or only pre-existing issues)

**Step 4: Verify import chain is lightweight**

Run: `uv run python -c "from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage; print('base OK')"`
Run: `uv run python -c "from amelia.agents.schemas import EvaluationOutput, MarkdownPlanOutput; print('schemas OK')"`
Run: `uv run python -c "from amelia.sandbox.docker import DockerSandboxProvider; print('docker OK')"`
Run: `uv run python -c "from amelia.sandbox.worktree import WorktreeManager; print('worktree OK')"`
Expected: All print OK

---

## Summary

| Task | Component | Test File | Commit Message |
|------|-----------|-----------|---------------|
| 1 | USAGE message type | `test_worker_protocol.py` | `feat(sandbox): add USAGE message type to AgenticMessage` |
| 2 | DockerSandboxProvider | `test_docker_provider.py` | `feat(sandbox): add DockerSandboxProvider for container lifecycle` |
| 3 | WorktreeManager | `test_worktree.py` | `feat(sandbox): add git worktree lifecycle management` |
| 4 | Worker entrypoint | `test_worker.py` | `feat(sandbox): add worker entrypoint for container-side execution` |
| 5 | Dockerfile + scripts | (none — integration) | `feat(sandbox): add Dockerfile, devcontainer.json, and credential helper` |
| 6 | Package exports | (existing tests) | `feat(sandbox): export DockerSandboxProvider and WorktreeManager` |
| 7 | Final verification | (all tests) | — |

**Dependencies:** Task 1 must complete before Task 4 (worker uses USAGE type). Tasks 2, 3 are independent of each other. Task 5 is independent. Task 6 depends on 2-4. Task 7 depends on all.
