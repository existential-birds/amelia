# Daytona Sandbox Provider Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Daytona cloud sandbox provider so Amelia workflows can run in ephemeral Daytona instances.

**Architecture:** New `DaytonaSandboxProvider` implements the existing `SandboxProvider` protocol using Daytona's native APIs for lifecycle/git and `process.exec()` for worker execution. Wired through the existing `get_driver()` factory with a new `SandboxMode.DAYTONA`. See `docs/plans/2026-03-03-daytona-sandbox-design.md` for full design.

**Tech Stack:** Python 3.12+, `daytona-sdk` (PyPI), Pydantic, pytest-asyncio, React/TypeScript (dashboard)

---

### Task 1: Add `daytona-sdk` dependency

**Files:**
- Modify: `pyproject.toml` (dependencies list, around line 7)

**Step 1: Add the dependency**

Add `"daytona-sdk>=0.148.0"` to the `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    ...existing deps...
    "daytona-sdk>=0.148.0",
]
```

**Step 2: Install**

Run: `uv sync`
Expected: Resolves and installs daytona-sdk

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add daytona-sdk"
```

---

### Task 2: Extend data model with Daytona types

**Files:**
- Modify: `amelia/core/types.py:45-68`
- Test: `tests/unit/core/test_sandbox_config.py`

**Step 1: Write failing tests**

Add to `tests/unit/core/test_sandbox_config.py`:

```python
from amelia.core.types import DaytonaResources, Profile, SandboxConfig


class TestDaytonaSandboxConfig:
    def test_daytona_mode(self):
        config = SandboxConfig(mode="daytona")
        assert config.mode == "daytona"

    def test_daytona_resources_defaults(self):
        r = DaytonaResources()
        assert r.cpu == 2
        assert r.memory == 4
        assert r.disk == 10

    def test_daytona_resources_custom(self):
        r = DaytonaResources(cpu=4, memory=8, disk=20)
        assert r.cpu == 4

    def test_sandbox_config_daytona_fields(self):
        config = SandboxConfig(
            mode="daytona",
            repo_url="https://github.com/org/repo.git",
            daytona_api_url="https://custom.daytona.io/api",
            daytona_target="eu",
            daytona_resources=DaytonaResources(cpu=4),
        )
        assert config.repo_url == "https://github.com/org/repo.git"
        assert config.daytona_api_url == "https://custom.daytona.io/api"
        assert config.daytona_target == "eu"
        assert config.daytona_resources.cpu == 4

    def test_sandbox_config_daytona_fields_default_none(self):
        config = SandboxConfig()
        assert config.repo_url is None
        assert config.daytona_resources is None

    def test_existing_container_config_unchanged(self):
        """Daytona fields don't affect existing container configs."""
        config = SandboxConfig(mode="container", image="custom:latest")
        assert config.mode == "container"
        assert config.repo_url is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_sandbox_config.py::TestDaytonaSandboxConfig -v`
Expected: FAIL — `DaytonaResources` not importable, `"daytona"` not a valid mode

**Step 3: Implement the model changes**

In `amelia/core/types.py`, add `DAYTONA` to `SandboxMode`:

```python
class SandboxMode(StrEnum):
    """Sandbox execution mode."""

    NONE = "none"
    CONTAINER = "container"
    DAYTONA = "daytona"
```

Add `DaytonaResources` model before `SandboxConfig`:

```python
class DaytonaResources(BaseModel):
    """Resource configuration for Daytona sandbox instances.

    Attributes:
        cpu: Number of CPU cores.
        memory: Memory in GB.
        disk: Disk space in GB.
    """

    model_config = ConfigDict(frozen=True)

    cpu: int = 2
    memory: int = 4
    disk: int = 10
```

Add new fields to `SandboxConfig`:

```python
class SandboxConfig(BaseModel):
    # ...existing fields unchanged...

    # Remote sandbox fields (Daytona)
    repo_url: str | None = None
    daytona_api_url: str = "https://app.daytona.io/api"
    daytona_target: str = "us"
    daytona_resources: DaytonaResources | None = None
```

Also add `"app.daytona.io"` to `DEFAULT_NETWORK_ALLOWED_HOSTS`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_sandbox_config.py -v`
Expected: All PASS (including existing tests)

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_sandbox_config.py
git commit -m "feat(core): add DaytonaResources model and SandboxMode.DAYTONA"
```

---

### Task 3: Implement `DaytonaSandboxProvider`

**Files:**
- Create: `amelia/sandbox/daytona.py`
- Test: `tests/unit/sandbox/test_daytona_provider.py`

**Step 1: Write failing tests**

Create `tests/unit/sandbox/test_daytona_provider.py`:

```python
"""Unit tests for DaytonaSandboxProvider."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import DaytonaResources


class TestDaytonaSandboxProviderInit:
    """Provider initialization."""

    def test_creates_client_with_config(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="eu",
                repo_url="https://github.com/org/repo.git",
            )
            mock_cls.assert_called_once()
            assert provider._repo_url == "https://github.com/org/repo.git"


class TestDaytonaSandboxProviderEnsureRunning:
    """Sandbox creation and repo cloning."""

    @pytest.mark.asyncio
    async def test_creates_sandbox_and_clones_repo(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            mock_client.create.assert_called_once()
            mock_sandbox.git.clone.assert_called_once_with(
                "https://github.com/org/repo.git",
                "/workspace/repo",
            )

    @pytest.mark.asyncio
    async def test_noop_if_already_healthy(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(exit_code=0)
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            # First call creates
            await provider.ensure_running()
            # Second call should no-op
            await provider.ensure_running()

            assert mock_client.create.call_count == 1

    @pytest.mark.asyncio
    async def test_passes_resources_when_configured(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            resources = DaytonaResources(cpu=4, memory=8, disk=20)
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
                resources=resources,
            )
            await provider.ensure_running()

            create_args = mock_client.create.call_args
            # Verify resources were passed through
            params = create_args[0][0] if create_args[0] else create_args[1].get("params")
            assert params is not None


class TestDaytonaSandboxProviderExecStream:
    """Command execution via process.exec."""

    @pytest.mark.asyncio
    async def test_exec_stream_yields_stdout_lines(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(
                result="line1\nline2\nline3\n",
                exit_code=0,
            )
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            lines = []
            async for line in provider.exec_stream(["echo", "hello"], cwd="/workspace"):
                lines.append(line)

            assert lines == ["line1", "line2", "line3"]

    @pytest.mark.asyncio
    async def test_exec_stream_raises_on_nonzero_exit(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(
                result="",
                exit_code=1,
            )
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            with pytest.raises(RuntimeError, match="exited with code 1"):
                async for _ in provider.exec_stream(["false"]):
                    pass


class TestDaytonaSandboxProviderTeardown:
    """Sandbox cleanup."""

    @pytest.mark.asyncio
    async def test_teardown_deletes_sandbox(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()
            await provider.teardown()

            mock_sandbox.delete.assert_called_once()
            assert provider._sandbox is None

    @pytest.mark.asyncio
    async def test_teardown_noop_when_no_sandbox(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_cls.return_value = AsyncMock()
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            # Should not raise
            await provider.teardown()


class TestDaytonaSandboxProviderHealthCheck:
    """Health check."""

    @pytest.mark.asyncio
    async def test_healthy_sandbox(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(exit_code=0)
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_no_sandbox_returns_false(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_cls.return_value = AsyncMock()
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            assert await provider.health_check() is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_daytona_provider.py -v`
Expected: FAIL — `amelia.sandbox.daytona` does not exist

**Step 3: Implement `DaytonaSandboxProvider`**

Create `amelia/sandbox/daytona.py`:

```python
"""Daytona cloud sandbox provider.

Implements the SandboxProvider protocol using Daytona's native APIs
for sandbox lifecycle and git operations, with process.exec() for
command execution.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from daytona_sdk import AsyncDaytona, CreateSandboxFromImageParams, DaytonaConfig, Image, Resources
from loguru import logger

from amelia.sandbox.worktree import REPO_PATH

if TYPE_CHECKING:
    from daytona_sdk import Sandbox

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
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://app.daytona.io/api",
        target: str = "us",
        repo_url: str = "",
        branch: str = "main",
        resources: DaytonaResources | None = None,
    ) -> None:
        self._client = AsyncDaytona(DaytonaConfig(
            api_key=api_key,
            api_url=api_url,
            target=target,
        ))
        self._repo_url = repo_url
        self._branch = branch
        self._resources = resources
        self._sandbox: Sandbox | None = None

    async def ensure_running(self) -> None:
        """Create Daytona sandbox and clone repo using native APIs.

        First call creates the sandbox and clones the repository.
        Subsequent calls are no-ops if the sandbox is healthy.
        """
        if self._sandbox is not None and await self.health_check():
            return

        logger.info("Creating Daytona sandbox", target=self._client._config.target)

        create_params = CreateSandboxFromImageParams(
            image=Image.debian_slim("3.12"),
        )
        if self._resources:
            create_params = CreateSandboxFromImageParams(
                image=Image.debian_slim("3.12"),
                resources=Resources(
                    cpu=self._resources.cpu,
                    memory=self._resources.memory,
                    disk=self._resources.disk,
                ),
            )

        self._sandbox = await self._client.create(create_params)
        logger.info("Daytona sandbox created", sandbox_id=self._sandbox.id)

        if self._repo_url:
            logger.info("Cloning repo via Daytona git API", url=self._repo_url)
            await self._sandbox.git.clone(self._repo_url, REPO_PATH)

    async def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        """Execute command in sandbox, yielding stdout lines.

        Wraps Daytona's process.exec() and splits the result into lines.
        Note: stdin is not supported by the Daytona SDK and is ignored
        with a warning if provided.

        Args:
            command: Command and arguments to execute.
            cwd: Working directory inside the sandbox.
            env: Additional environment variables.
            stdin: Ignored (Daytona process.exec does not support stdin).

        Yields:
            Lines of stdout output.

        Raises:
            RuntimeError: If the sandbox is not running or command fails.
        """
        if self._sandbox is None:
            raise RuntimeError("Sandbox not running — call ensure_running() first")

        if stdin:
            logger.warning("Daytona exec_stream does not support stdin, ignoring")

        cmd_str = " ".join(command)
        response = await self._sandbox.process.exec(
            cmd_str,
            cwd=cwd,
            env_vars=env,
        )

        if response.exit_code != 0:
            raise RuntimeError(
                f"Command exited with code {response.exit_code}: {cmd_str}"
            )

        for line in response.result.splitlines():
            yield line

    async def teardown(self) -> None:
        """Delete the ephemeral Daytona sandbox."""
        if self._sandbox is None:
            return
        logger.info("Tearing down Daytona sandbox", sandbox_id=self._sandbox.id)
        await self._sandbox.delete()
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
            return response.exit_code == 0
        except Exception:
            logger.debug("Daytona health check failed")
            return False
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/sandbox/test_daytona_provider.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add amelia/sandbox/daytona.py tests/unit/sandbox/test_daytona_provider.py
git commit -m "feat(sandbox): add DaytonaSandboxProvider"
```

---

### Task 4: Wire Daytona into the driver factory

**Files:**
- Modify: `amelia/drivers/factory.py:9-52`
- Test: `tests/unit/drivers/test_factory.py`

**Step 1: Write failing tests**

Add to `tests/unit/drivers/test_factory.py`:

```python
import os


class TestGetDriverDaytonaBranch:
    """Daytona sandbox driver creation."""

    def test_daytona_mode_returns_container_driver(self):
        sandbox = SandboxConfig(
            mode="daytona",
            repo_url="https://github.com/org/repo.git",
            daytona_api_url="https://test.daytona.io/api",
            daytona_target="eu",
        )
        with patch("amelia.sandbox.daytona.DaytonaSandboxProvider") as mock_provider_cls, \
             patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls, \
             patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"}):
            mock_driver_cls.return_value = MagicMock()
            _driver = get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
            )
            mock_provider_cls.assert_called_once_with(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="eu",
                repo_url="https://github.com/org/repo.git",
                resources=None,
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider_cls.return_value,
            )

    def test_daytona_mode_missing_api_key_raises(self):
        sandbox = SandboxConfig(mode="daytona", repo_url="https://github.com/org/repo.git")
        with patch.dict(os.environ, {}, clear=True), \
             pytest.raises(ValueError, match="DAYTONA_API_KEY"):
            get_driver("api", sandbox_config=sandbox, profile_name="test")

    @pytest.mark.parametrize("driver_key", ["claude", "codex"])
    def test_daytona_mode_rejects_cli_wrappers(self, driver_key: str):
        sandbox = SandboxConfig(mode="daytona", repo_url="https://github.com/org/repo.git")
        with patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"}), \
             pytest.raises(ValueError, match="Daytona sandbox requires API driver"):
            get_driver(driver_key, sandbox_config=sandbox, profile_name="test")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/drivers/test_factory.py::TestGetDriverDaytonaBranch -v`
Expected: FAIL — factory doesn't handle `"daytona"` mode

**Step 3: Implement factory changes**

In `amelia/drivers/factory.py`, add a new branch after the `"container"` branch (line 35), before the `if driver_key == "claude"` line:

```python
    if sandbox_config and sandbox_config.mode == "daytona":
        if driver_key in {"claude", "codex"}:
            raise ValueError(
                "Daytona sandbox requires API driver. "
                "CLI driver containerization is not yet supported."
            )
        if driver_key != "api":
            raise ValueError(f"Unknown driver key: {driver_key!r}")

        import os  # noqa: PLC0415

        from amelia.sandbox.daytona import DaytonaSandboxProvider  # noqa: PLC0415
        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        api_key = os.environ.get("DAYTONA_API_KEY")
        if not api_key:
            raise ValueError(
                "DAYTONA_API_KEY environment variable is required for Daytona sandbox"
            )

        provider = DaytonaSandboxProvider(
            api_key=api_key,
            api_url=sandbox_config.daytona_api_url,
            target=sandbox_config.daytona_target,
            repo_url=sandbox_config.repo_url or "",
            resources=sandbox_config.daytona_resources,
        )
        return ContainerDriver(model=model, provider=provider)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/drivers/test_factory.py -v`
Expected: All PASS (existing + new)

**Step 5: Commit**

```bash
git add amelia/drivers/factory.py tests/unit/drivers/test_factory.py
git commit -m "feat(drivers): wire DaytonaSandboxProvider into factory"
```

---

### Task 5: Integration test — provider + ContainerDriver + WorktreeManager

**Files:**
- Create: `tests/integration/test_daytona_sandbox.py`

**Step 1: Write the integration test**

This test validates the full stack with a mocked Daytona SDK:

```python
"""Integration test for Daytona sandbox stack.

Tests DaytonaSandboxProvider + ContainerDriver + WorktreeManager
working together, mocking at the Daytona SDK boundary.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import DaytonaResources, SandboxConfig
from amelia.drivers.base import AgenticMessage, AgenticMessageType


class TestDaytonaFullStack:
    """DaytonaSandboxProvider + ContainerDriver end-to-end."""

    @pytest.fixture
    def mock_daytona(self):
        """Mock Daytona SDK returning realistic process.exec responses."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.id = "test-sandbox-123"
            mock_sandbox.process.exec.return_value = MagicMock(
                result="", exit_code=0,
            )
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client
            yield mock_sandbox

    @pytest.mark.asyncio
    async def test_container_driver_with_daytona_provider(self, mock_daytona):
        """ContainerDriver should work with DaytonaSandboxProvider."""
        from amelia.sandbox.daytona import DaytonaSandboxProvider
        from amelia.sandbox.driver import ContainerDriver

        provider = DaytonaSandboxProvider(
            api_key="test-key",
            api_url="https://test.daytona.io/api",
            target="us",
            repo_url="https://github.com/org/repo.git",
        )
        driver = ContainerDriver(model="test-model", provider=provider)

        # Simulate worker output for generate mode
        result_msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Generated output",
        )
        mock_daytona.process.exec.return_value = MagicMock(
            result=result_msg.model_dump_json(),
            exit_code=0,
        )

        output, session_id = await driver.generate(prompt="Test prompt")
        assert output == "Generated output"
        assert session_id is None

    @pytest.mark.asyncio
    async def test_worktree_manager_with_daytona_provider(self, mock_daytona):
        """WorktreeManager should work via DaytonaSandboxProvider.exec_stream."""
        from amelia.sandbox.daytona import DaytonaSandboxProvider
        from amelia.sandbox.worktree import WorktreeManager

        provider = DaytonaSandboxProvider(
            api_key="test-key",
            api_url="https://test.daytona.io/api",
            target="us",
            repo_url="https://github.com/org/repo.git",
        )
        await provider.ensure_running()

        # WorktreeManager uses exec_stream for git worktree commands
        wt = WorktreeManager(provider=provider, repo_url="https://github.com/org/repo.git")

        mock_daytona.process.exec.return_value = MagicMock(
            result="", exit_code=0,
        )

        # create_worktree shells out via exec_stream
        worktree_path = await wt.create_worktree("wf-123", base_branch="main")
        assert worktree_path == "/workspace/worktrees/wf-123"

    @pytest.mark.asyncio
    async def test_factory_creates_daytona_stack(self, mock_daytona):
        """get_driver with daytona mode should produce working ContainerDriver."""
        import os

        from amelia.drivers.factory import get_driver

        sandbox = SandboxConfig(
            mode="daytona",
            repo_url="https://github.com/org/repo.git",
        )
        with patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"}):
            driver = get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
            )

        assert driver is not None
        assert hasattr(driver, "execute_agentic")
```

**Step 2: Run the test**

Run: `uv run pytest tests/integration/test_daytona_sandbox.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/integration/test_daytona_sandbox.py
git commit -m "test(integration): add Daytona sandbox full-stack tests"
```

---

### Task 6: Dashboard TypeScript types

**Files:**
- Modify: `dashboard/src/api/settings.ts:57-62`
- Modify: `dashboard/src/__tests__/fixtures.ts:185-193`

**Step 1: Update `SandboxConfig` interface**

In `dashboard/src/api/settings.ts`, update the `SandboxConfig` interface:

```typescript
export interface DaytonaResources {
  cpu: number;
  memory: number;
  disk: number;
}

export interface SandboxConfig {
  mode: 'none' | 'container' | 'daytona';
  image: string;
  network_allowlist_enabled: boolean;
  network_allowed_hosts: string[];
  // Remote sandbox fields (Daytona)
  repo_url?: string;
  daytona_api_url?: string;
  daytona_target?: string;
  daytona_resources?: DaytonaResources;
}
```

**Step 2: Update test fixtures**

In `dashboard/src/__tests__/fixtures.ts`, update `createMockSandboxConfig`:

No change needed — the new fields are all optional, so existing fixture works.

**Step 3: Run dashboard type check**

Run: `cd dashboard && pnpm type-check`
Expected: PASS

**Step 4: Commit**

```bash
git add dashboard/src/api/settings.ts
git commit -m "feat(dashboard): add Daytona types to SandboxConfig"
```

---

### Task 7: Dashboard profile modal — Daytona settings UI

**Files:**
- Modify: `dashboard/src/components/settings/ProfileEditModal.tsx`

**Step 1: Extend form data type**

Add Daytona fields to `ProfileFormData` (around line 157):

```typescript
  sandbox_mode: 'none' | 'container' | 'daytona';
  // ...existing fields...
  // Daytona-specific
  sandbox_repo_url: string;
  sandbox_daytona_api_url: string;
  sandbox_daytona_target: string;
  sandbox_daytona_cpu: number;
  sandbox_daytona_memory: number;
  sandbox_daytona_disk: number;
```

**Step 2: Extend defaults** (around line 223):

```typescript
  sandbox_repo_url: '',
  sandbox_daytona_api_url: 'https://app.daytona.io/api',
  sandbox_daytona_target: 'us',
  sandbox_daytona_cpu: 2,
  sandbox_daytona_memory: 4,
  sandbox_daytona_disk: 10,
```

**Step 3: Extend `profileToFormData`** (around line 265):

```typescript
  sandbox_repo_url: profile.sandbox?.repo_url ?? '',
  sandbox_daytona_api_url: profile.sandbox?.daytona_api_url ?? 'https://app.daytona.io/api',
  sandbox_daytona_target: profile.sandbox?.daytona_target ?? 'us',
  sandbox_daytona_cpu: profile.sandbox?.daytona_resources?.cpu ?? 2,
  sandbox_daytona_memory: profile.sandbox?.daytona_resources?.memory ?? 4,
  sandbox_daytona_disk: profile.sandbox?.daytona_resources?.disk ?? 10,
```

**Step 4: Extend `formSandboxToApi`** (around line 725):

```typescript
  const formSandboxToApi = (): SandboxConfig => ({
    mode: formData.sandbox_mode,
    image: formData.sandbox_image,
    network_allowlist_enabled: formData.sandbox_network_allowlist_enabled,
    network_allowed_hosts: formData.sandbox_network_allowed_hosts,
    ...(formData.sandbox_mode === 'daytona' && {
      repo_url: formData.sandbox_repo_url,
      daytona_api_url: formData.sandbox_daytona_api_url,
      daytona_target: formData.sandbox_daytona_target,
      daytona_resources: {
        cpu: formData.sandbox_daytona_cpu,
        memory: formData.sandbox_daytona_memory,
        disk: formData.sandbox_daytona_disk,
      },
    }),
  });
```

**Step 5: Extend `hasChanges`** (around line 603):

Add comparisons for the new fields inside the sandbox change check.

**Step 6: Add Daytona option to sandbox mode select and conditional UI** (around line 980):

Add `<SelectItem value="daytona">Daytona</SelectItem>` to the mode selector.

Update the description text:

```typescript
  {formData.sandbox_mode === 'none'
    ? 'Code runs directly on the host machine.'
    : formData.sandbox_mode === 'container'
      ? 'Code runs in an isolated Docker container.'
      : 'Code runs in an ephemeral Daytona cloud sandbox.'}
```

Add a new conditional block for Daytona settings (after the container block):

```tsx
{formData.sandbox_mode === 'daytona' && (
  <>
    {/* Repo URL */}
    <div className="space-y-2">
      <Label className="text-xs uppercase tracking-wider text-muted-foreground">
        Repository URL
      </Label>
      <Input
        value={formData.sandbox_repo_url}
        onChange={(e) => handleChange('sandbox_repo_url', e.target.value)}
        placeholder="https://github.com/org/repo.git"
        className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
      />
    </div>

    {/* API URL */}
    <div className="space-y-2">
      <Label className="text-xs uppercase tracking-wider text-muted-foreground">
        Daytona API URL
      </Label>
      <Input
        value={formData.sandbox_daytona_api_url}
        onChange={(e) => handleChange('sandbox_daytona_api_url', e.target.value)}
        placeholder="https://app.daytona.io/api"
        className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
      />
    </div>

    {/* Target Region */}
    <div className="space-y-2">
      <Label className="text-xs uppercase tracking-wider text-muted-foreground">
        Target Region
      </Label>
      <Select
        value={formData.sandbox_daytona_target}
        onValueChange={(v) => handleChange('sandbox_daytona_target', v)}
      >
        <SelectTrigger className="bg-background/50">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="us">US</SelectItem>
          <SelectItem value="eu">EU</SelectItem>
        </SelectContent>
      </Select>
    </div>

    {/* Resources */}
    <div className="space-y-2">
      <Label className="text-xs uppercase tracking-wider text-muted-foreground">
        Resources
      </Label>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">CPU Cores</Label>
          <Input
            type="number" min={1} max={16}
            value={formData.sandbox_daytona_cpu}
            onChange={(e) => handleChange('sandbox_daytona_cpu', parseInt(e.target.value) || 2)}
            className="bg-background/50"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Memory (GB)</Label>
          <Input
            type="number" min={1} max={64}
            value={formData.sandbox_daytona_memory}
            onChange={(e) => handleChange('sandbox_daytona_memory', parseInt(e.target.value) || 4)}
            className="bg-background/50"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Disk (GB)</Label>
          <Input
            type="number" min={1} max={100}
            value={formData.sandbox_daytona_disk}
            onChange={(e) => handleChange('sandbox_daytona_disk', parseInt(e.target.value) || 10)}
            className="bg-background/50"
          />
        </div>
      </div>
    </div>

    {/* API Key note */}
    <p className="text-xs text-muted-foreground">
      Set the <code className="rounded bg-muted px-1">DAYTONA_API_KEY</code> environment variable before starting Amelia.
    </p>
  </>
)}
```

**Step 7: Run dashboard checks**

Run: `cd dashboard && pnpm type-check && pnpm lint:fix`
Expected: PASS

**Step 8: Commit**

```bash
git add dashboard/src/components/settings/ProfileEditModal.tsx
git commit -m "feat(dashboard): add Daytona sandbox settings to profile modal"
```

---

### Task 8: Run full test suite and lint

**Step 1: Backend checks**

Run: `uv run ruff check amelia tests && uv run mypy amelia && uv run pytest`
Expected: All PASS

**Step 2: Frontend checks**

Run: `cd dashboard && pnpm type-check && pnpm test:run && pnpm build`
Expected: All PASS

**Step 3: Fix any issues found and commit**

If lint/type issues arise, fix them and commit:

```bash
git add -A
git commit -m "fix: address lint and type issues from Daytona integration"
```
