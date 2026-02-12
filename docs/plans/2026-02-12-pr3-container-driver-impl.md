# PR3: ContainerDriver, Factory Wiring, Network Allowlist — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the DevContainer sandbox feature by implementing ContainerDriver, wiring it into the driver factory, adding network allowlist infrastructure, and integrating sandbox teardown into the server lifecycle.

**Architecture:** ContainerDriver implements DriverInterface by delegating execution to a container worker via SandboxProvider.exec_stream(). Config flows Profile.sandbox → AgentConfig (injected by get_agent_config) → get_driver() → ContainerDriver. Network allowlist is a pure function generating iptables rules, applied by a shell script inside the container.

**Tech Stack:** Python 3.12+, Pydantic, asyncio, pytest, Docker CLI (no SDK)

---

## Task 1: Add `sandbox` and `profile_name` Fields to AgentConfig

**Files:**
- Modify: `amelia/core/types.py:41-54` (AgentConfig class)
- Test: `tests/unit/core/test_types.py`

### Step 1: Write the failing tests

Add tests to `tests/unit/core/test_types.py`:

```python
def test_agent_config_sandbox_default():
    """AgentConfig should default sandbox to SandboxConfig() with mode='none'."""
    from amelia.core.types import AgentConfig, SandboxConfig

    config = AgentConfig(driver="cli", model="sonnet")
    assert config.sandbox == SandboxConfig()
    assert config.sandbox.mode == "none"


def test_agent_config_profile_name_default():
    """AgentConfig should default profile_name to 'default'."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="cli", model="sonnet")
    assert config.profile_name == "default"


def test_agent_config_with_sandbox_config():
    """AgentConfig should accept explicit SandboxConfig."""
    from amelia.core.types import AgentConfig, SandboxConfig

    sandbox = SandboxConfig(mode="container", image="custom:latest")
    config = AgentConfig(
        driver="api", model="test-model",
        sandbox=sandbox, profile_name="work",
    )
    assert config.sandbox.mode == "container"
    assert config.sandbox.image == "custom:latest"
    assert config.profile_name == "work"
```

### Step 2: Run tests to verify they fail

Run: `uv run pytest tests/unit/core/test_types.py::test_agent_config_sandbox_default tests/unit/core/test_types.py::test_agent_config_profile_name_default tests/unit/core/test_types.py::test_agent_config_with_sandbox_config -v`
Expected: FAIL — AgentConfig has no `sandbox` or `profile_name` fields

### Step 3: Add the fields to AgentConfig

In `amelia/core/types.py`, add two fields to `AgentConfig` (line 54, after `options`):

```python
class AgentConfig(BaseModel):
    """Per-agent driver and model configuration.

    Attributes:
        driver: LLM driver type ('api' or 'cli').
        model: LLM model identifier.
        options: Agent-specific options (e.g., max_iterations).
        sandbox: Sandbox execution config (injected by Profile.get_agent_config).
        profile_name: Profile name (injected by Profile.get_agent_config).
    """

    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str
    options: dict[str, Any] = Field(default_factory=dict)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    profile_name: str = "default"
```

### Step 4: Run tests to verify they pass

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: All PASS (including existing tests — defaults are backward-compatible)

### Step 5: Commit

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "feat(sandbox): add sandbox and profile_name fields to AgentConfig"
```

---

## Task 2: Inject Sandbox Config in `Profile.get_agent_config()`

**Files:**
- Modify: `amelia/core/types.py:123-137` (Profile.get_agent_config method)
- Test: `tests/unit/core/test_types.py`

### Step 1: Write the failing tests

Add to `tests/unit/core/test_types.py`:

```python
def test_get_agent_config_injects_sandbox():
    """get_agent_config should inject profile's sandbox config into AgentConfig."""
    from amelia.core.types import AgentConfig, Profile, SandboxConfig

    sandbox = SandboxConfig(mode="container", image="custom:latest")
    profile = Profile(
        name="work",
        tracker="noop",
        working_dir="/tmp/test",
        sandbox=sandbox,
        agents={"architect": AgentConfig(driver="api", model="opus")},
    )

    config = profile.get_agent_config("architect")
    assert config.sandbox.mode == "container"
    assert config.sandbox.image == "custom:latest"
    assert config.profile_name == "work"


def test_get_agent_config_injects_profile_name():
    """get_agent_config should set profile_name to profile.name."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="personal",
        tracker="noop",
        working_dir="/tmp/test",
        agents={"developer": AgentConfig(driver="cli", model="sonnet")},
    )

    config = profile.get_agent_config("developer")
    assert config.profile_name == "personal"


def test_get_agent_config_preserves_original():
    """get_agent_config should not mutate the stored AgentConfig."""
    from amelia.core.types import AgentConfig, Profile, SandboxConfig

    sandbox = SandboxConfig(mode="container")
    original = AgentConfig(driver="api", model="opus")
    profile = Profile(
        name="work",
        tracker="noop",
        working_dir="/tmp/test",
        sandbox=sandbox,
        agents={"architect": original},
    )

    injected = profile.get_agent_config("architect")
    assert injected is not original
    assert original.sandbox.mode == "none"  # Original unchanged
    assert original.profile_name == "default"  # Original unchanged
    assert injected.sandbox.mode == "container"  # Injected has profile's sandbox
```

### Step 2: Run tests to verify they fail

Run: `uv run pytest tests/unit/core/test_types.py::test_get_agent_config_injects_sandbox tests/unit/core/test_types.py::test_get_agent_config_injects_profile_name tests/unit/core/test_types.py::test_get_agent_config_preserves_original -v`
Expected: FAIL — `get_agent_config` returns stored config without injection

### Step 3: Update `get_agent_config()`

In `amelia/core/types.py`, replace the `get_agent_config` method body:

```python
    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get config for an agent with profile-level sandbox and name injected.

        Args:
            agent_name: Name of the agent (e.g., 'architect', 'developer').

        Returns:
            AgentConfig with sandbox and profile_name from this profile.

        Raises:
            ValueError: If agent not configured in this profile.
        """
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not configured in profile '{self.name}'")
        return self.agents[agent_name].model_copy(
            update={"sandbox": self.sandbox, "profile_name": self.name}
        )
```

### Step 4: Run tests to verify they pass

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: All PASS

### Step 5: Commit

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "feat(sandbox): inject sandbox config and profile_name in get_agent_config()"
```

---

## Task 3: Refactor Driver Factory to Typed Signature

**Files:**
- Modify: `amelia/drivers/factory.py`
- Create: `tests/unit/drivers/test_factory.py`

### Step 1: Write the failing tests

Create `tests/unit/drivers/test_factory.py`:

```python
"""Unit tests for the driver factory."""
from unittest.mock import MagicMock, patch

import pytest

from amelia.core.types import SandboxConfig
from amelia.drivers.factory import get_driver


class TestGetDriverExistingBehavior:
    """Existing behavior must be preserved with the new signature."""

    def test_cli_driver(self) -> None:
        with patch("amelia.drivers.factory.ClaudeCliDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            driver = get_driver("cli", model="sonnet")
            mock_cls.assert_called_once_with(model="sonnet")

    def test_api_driver(self) -> None:
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            driver = get_driver("api", model="test-model")
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")

    def test_unknown_driver_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown driver key: unknown"):
            get_driver("unknown")


class TestGetDriverContainerBranch:
    """Container sandbox driver creation."""

    def test_container_mode_returns_container_driver(self) -> None:
        sandbox = SandboxConfig(mode="container", image="test:latest")
        with patch("amelia.drivers.factory.DockerSandboxProvider") as mock_provider_cls, \
             patch("amelia.drivers.factory.ContainerDriver") as mock_driver_cls:
            mock_driver_cls.return_value = MagicMock()
            driver = get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
            )
            mock_provider_cls.assert_called_once_with(
                profile_name="work", image="test:latest",
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider_cls.return_value,
            )

    def test_container_mode_cli_raises(self) -> None:
        sandbox = SandboxConfig(mode="container")
        with pytest.raises(ValueError, match="Container sandbox requires API driver"):
            get_driver("cli", sandbox_config=sandbox, profile_name="test")

    def test_container_mode_cli_colon_raises(self) -> None:
        sandbox = SandboxConfig(mode="container")
        with pytest.raises(ValueError, match="Container sandbox requires API driver"):
            get_driver("cli:claude", sandbox_config=sandbox, profile_name="test")

    def test_none_mode_returns_normal_driver(self) -> None:
        sandbox = SandboxConfig(mode="none")
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            driver = get_driver("api", model="test-model", sandbox_config=sandbox)
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")

    def test_no_sandbox_config_returns_normal_driver(self) -> None:
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            driver = get_driver("api", model="test-model")
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")
```

### Step 2: Run tests to verify they fail

Run: `uv run pytest tests/unit/drivers/test_factory.py -v`
Expected: FAIL — `get_driver` uses `**kwargs`, doesn't accept `sandbox_config`/`profile_name`

### Step 3: Implement the refactored factory

Replace `get_driver` in `amelia/drivers/factory.py`:

```python
from typing import Any

from amelia.core.types import SandboxConfig
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.claude import ClaudeCliDriver


def get_driver(
    driver_key: str,
    *,
    model: str = "",
    cwd: str | None = None,
    sandbox_config: SandboxConfig | None = None,
    profile_name: str = "default",
    options: dict[str, Any] | None = None,
) -> DriverInterface:
    """Get a concrete driver implementation.

    Args:
        driver_key: Driver identifier ("cli" or "api").
        model: LLM model identifier.
        cwd: Working directory (used by CLI driver).
        sandbox_config: Sandbox configuration for containerized execution.
        profile_name: Profile name for container naming.
        options: Driver-specific configuration options.

    Returns:
        Configured driver instance.

    Raises:
        ValueError: If driver_key is not recognized or incompatible with sandbox.
    """
    if sandbox_config and sandbox_config.mode == "container":
        if driver_key.startswith("cli"):
            raise ValueError(
                "Container sandbox requires API driver. "
                "CLI driver containerization is not yet supported."
            )
        from amelia.sandbox.docker import DockerSandboxProvider  # noqa: PLC0415
        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        provider = DockerSandboxProvider(
            profile_name=profile_name,
            image=sandbox_config.image,
        )
        return ContainerDriver(model=model, provider=provider)

    # Accept legacy values for backward compatibility
    if driver_key in ("cli:claude", "cli"):
        return ClaudeCliDriver(model=model)
    elif driver_key in ("api:openrouter", "api"):
        return ApiDriver(provider="openrouter", model=model)
    else:
        raise ValueError(f"Unknown driver key: {driver_key}")
```

**Note:** The `cwd` and `options` parameters are declared for forward compatibility but not used in this PR's factory logic. Agents pass `cwd` directly to `execute_agentic()`, not to the factory.

### Step 4: Run tests to verify they pass

Run: `uv run pytest tests/unit/drivers/test_factory.py -v`
Expected: FAIL — `ContainerDriver` doesn't exist yet. The container-branch tests will fail until Task 5.

For now, run only the non-container tests:
Run: `uv run pytest tests/unit/drivers/test_factory.py::TestGetDriverExistingBehavior tests/unit/drivers/test_factory.py::TestGetDriverContainerBranch::test_container_mode_cli_raises tests/unit/drivers/test_factory.py::TestGetDriverContainerBranch::test_container_mode_cli_colon_raises tests/unit/drivers/test_factory.py::TestGetDriverContainerBranch::test_none_mode_returns_normal_driver tests/unit/drivers/test_factory.py::TestGetDriverContainerBranch::test_no_sandbox_config_returns_normal_driver -v`
Expected: All PASS

### Step 5: Verify existing tests still pass

Run: `uv run pytest tests/unit/agents/test_developer.py tests/unit/agents/test_architect_agentic.py -v`
Expected: All PASS (get_driver callers still use keyword args)

### Step 6: Commit

```bash
git add amelia/drivers/factory.py tests/unit/drivers/test_factory.py
git commit -m "feat(sandbox): refactor driver factory to typed signature with container branch"
```

---

## Task 4: Update Agent Constructors to Pass Sandbox Config

**Files:**
- Modify: `amelia/agents/architect.py:75` (one-line change)
- Modify: `amelia/agents/developer.py:39` (one-line change)
- Modify: `amelia/agents/reviewer.py:129` (one-line change)
- Test: `tests/unit/agents/test_developer.py` (update assertions)

### Step 1: Write the failing test

Add to `tests/unit/agents/test_developer.py`:

```python
def test_developer_init_passes_sandbox_config() -> None:
    """Developer should pass sandbox_config and profile_name to get_driver."""
    from amelia.core.types import SandboxConfig

    sandbox = SandboxConfig(mode="container", image="custom:latest")
    config = AgentConfig(
        driver="api", model="test-model",
        sandbox=sandbox, profile_name="work",
        options={"max_iterations": 5},
    )

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_get_driver.return_value = MagicMock()
        developer = Developer(config)

        mock_get_driver.assert_called_once_with(
            "api",
            model="test-model",
            sandbox_config=sandbox,
            profile_name="work",
            options={"max_iterations": 5},
        )
```

### Step 2: Run test to verify it fails

Run: `uv run pytest tests/unit/agents/test_developer.py::test_developer_init_passes_sandbox_config -v`
Expected: FAIL — `get_driver` called with `model=` only

### Step 3: Update all three agent constructors

**`amelia/agents/developer.py`** — replace the `self.driver = get_driver(...)` line:
```python
        self.driver = get_driver(
            config.driver,
            model=config.model,
            sandbox_config=config.sandbox,
            profile_name=config.profile_name,
            options=config.options,
        )
```

**`amelia/agents/architect.py`** — same change to the `self.driver = get_driver(...)` line:
```python
        self.driver = get_driver(
            config.driver,
            model=config.model,
            sandbox_config=config.sandbox,
            profile_name=config.profile_name,
            options=config.options,
        )
```

**`amelia/agents/reviewer.py`** — same change to the `self.driver = get_driver(...)` line:
```python
        self.driver = get_driver(
            config.driver,
            model=config.model,
            sandbox_config=config.sandbox,
            profile_name=config.profile_name,
            options=config.options,
        )
```

### Step 4: Update existing test assertions

In `tests/unit/agents/test_developer.py`, update `test_developer_init_with_agent_config`:
```python
def test_developer_init_with_agent_config() -> None:
    """Developer should accept AgentConfig and create its own driver."""
    config = AgentConfig(driver="api", model="anthropic/claude-sonnet-4")

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        developer = Developer(config)

        from amelia.core.types import SandboxConfig
        mock_get_driver.assert_called_once_with(
            "api",
            model="anthropic/claude-sonnet-4",
            sandbox_config=SandboxConfig(),
            profile_name="default",
            options={},
        )
        assert developer.driver is mock_driver
        assert developer.options == {}
```

Similarly update `test_developer_init_with_options` to match the new call signature.

Also check and update corresponding tests in `tests/unit/agents/test_architect_agentic.py` and `tests/unit/agents/test_reviewer.py` that assert on `get_driver` call args.

### Step 5: Run all agent tests

Run: `uv run pytest tests/unit/agents/ -v`
Expected: All PASS

### Step 6: Commit

```bash
git add amelia/agents/architect.py amelia/agents/developer.py amelia/agents/reviewer.py tests/unit/agents/
git commit -m "feat(sandbox): pass sandbox_config and profile_name through agent constructors"
```

---

## Task 5: Implement ContainerDriver

**Files:**
- Create: `amelia/sandbox/driver.py`
- Create: `tests/unit/sandbox/test_container_driver.py`

This is the largest task. The driver implements `DriverInterface` by delegating to `SandboxProvider.exec_stream()`.

### Step 1: Write the failing tests

Create `tests/unit/sandbox/test_container_driver.py`:

```python
"""Unit tests for ContainerDriver."""
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
)


class SampleSchema(BaseModel):
    """Test schema for generate() tests."""
    goal: str
    summary: str


def _make_provider_mock(lines: list[str]) -> AsyncMock:
    """Create a mock SandboxProvider whose exec_stream returns the given lines.

    Args:
        lines: Lines to yield from exec_stream.

    Returns:
        AsyncMock implementing SandboxProvider protocol.
    """
    provider = AsyncMock()
    provider.ensure_running = AsyncMock()

    call_count = 0

    async def mock_exec_stream(
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        nonlocal call_count
        call_count += 1
        # First call: write prompt file (tee). Yield nothing.
        # Second call: run worker. Yield lines.
        # Third call: cleanup (rm). Yield nothing.
        if call_count == 2:
            for line in lines:
                yield line
        # Other calls yield nothing (prompt write and cleanup)

    provider.exec_stream = mock_exec_stream
    return provider


class TestExecuteAgentic:
    """Tests for ContainerDriver.execute_agentic()."""

    async def test_happy_path_yields_messages(self) -> None:
        """Should parse JSON lines into AgenticMessage, skip USAGE."""
        from amelia.sandbox.driver import ContainerDriver

        thinking = AgenticMessage(
            type=AgenticMessageType.THINKING, content="Planning...", model="test",
        )
        result = AgenticMessage(
            type=AgenticMessageType.RESULT, content="Done", model="test",
        )
        usage_msg = AgenticMessage(
            type=AgenticMessageType.USAGE,
            usage=DriverUsage(input_tokens=100, output_tokens=50, model="test"),
        )
        lines = [
            thinking.model_dump_json(),
            result.model_dump_json(),
            usage_msg.model_dump_json(),
        ]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        messages: list[AgenticMessage] = []
        async for msg in driver.execute_agentic(prompt="do something", cwd="/work"):
            messages.append(msg)

        assert len(messages) == 2
        assert messages[0].type == AgenticMessageType.THINKING
        assert messages[0].content == "Planning..."
        assert messages[1].type == AgenticMessageType.RESULT
        assert messages[1].content == "Done"

    async def test_usage_captured(self) -> None:
        """USAGE message should be captured for get_usage()."""
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(type=AgenticMessageType.RESULT, content="Done")
        usage = DriverUsage(input_tokens=100, output_tokens=50, model="test")
        usage_msg = AgenticMessage(type=AgenticMessageType.USAGE, usage=usage)
        lines = [result.model_dump_json(), usage_msg.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
            pass

        result_usage = driver.get_usage()
        assert result_usage is not None
        assert result_usage.input_tokens == 100
        assert result_usage.output_tokens == 50

    async def test_empty_prompt_raises(self) -> None:
        """Empty prompt should raise ValueError."""
        from amelia.sandbox.driver import ContainerDriver

        provider = _make_provider_mock([])
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            async for _ in driver.execute_agentic(prompt="", cwd="/work"):
                pass

    async def test_malformed_json_raises(self) -> None:
        """Malformed JSON should raise RuntimeError immediately."""
        from amelia.sandbox.driver import ContainerDriver

        lines = ["not valid json"]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(RuntimeError, match="Failed to parse worker output"):
            async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
                pass

    async def test_prompt_file_cleanup_on_success(self) -> None:
        """Prompt file should be cleaned up after successful execution."""
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(type=AgenticMessageType.RESULT, content="Done")
        lines = [result.model_dump_json()]

        calls: list[list[str]] = []
        provider = AsyncMock()
        provider.ensure_running = AsyncMock()

        call_count = 0

        async def tracking_exec_stream(
            command: list[str], **kwargs: Any,
        ) -> AsyncIterator[str]:
            nonlocal call_count
            calls.append(command)
            call_count += 1
            if call_count == 2:
                for line in lines:
                    yield line

        provider.exec_stream = tracking_exec_stream
        driver = ContainerDriver(model="test", provider=provider)

        async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
            pass

        # Third call should be cleanup (rm -f)
        assert len(calls) == 3
        assert calls[2][0] == "rm"
        assert calls[2][1] == "-f"

    async def test_prompt_file_cleanup_on_exception(self) -> None:
        """Prompt file should be cleaned up even if worker fails."""
        from amelia.sandbox.driver import ContainerDriver

        calls: list[list[str]] = []
        provider = AsyncMock()
        provider.ensure_running = AsyncMock()

        call_count = 0

        async def failing_exec_stream(
            command: list[str], **kwargs: Any,
        ) -> AsyncIterator[str]:
            nonlocal call_count
            calls.append(command)
            call_count += 1
            if call_count == 2:
                yield "invalid json"

        provider.exec_stream = failing_exec_stream
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(RuntimeError):
            async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
                pass

        # Cleanup should still have been called
        assert any(cmd[0] == "rm" for cmd in calls)


class TestGenerate:
    """Tests for ContainerDriver.generate()."""

    async def test_happy_path_returns_content(self) -> None:
        """Should return (content, None) tuple."""
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(
            type=AgenticMessageType.RESULT, content="Generated text",
        )
        usage_msg = AgenticMessage(
            type=AgenticMessageType.USAGE,
            usage=DriverUsage(input_tokens=50, output_tokens=25),
        )
        lines = [result.model_dump_json(), usage_msg.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        output, session_id = await driver.generate(prompt="generate something")

        assert output == "Generated text"
        assert session_id is None

    async def test_schema_round_trip(self) -> None:
        """generate() with schema should return Pydantic model instance."""
        from amelia.sandbox.driver import ContainerDriver

        schema_instance = SampleSchema(goal="build feature", summary="details")
        result = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=schema_instance.model_dump_json(),
        )
        lines = [result.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        output, _ = await driver.generate(
            prompt="generate", schema=SampleSchema,
        )

        assert isinstance(output, SampleSchema)
        assert output.goal == "build feature"
        assert output.summary == "details"

    async def test_schema_validation_failure_raises(self) -> None:
        """Invalid JSON for schema should raise RuntimeError."""
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(
            type=AgenticMessageType.RESULT, content="not valid json for schema",
        )
        lines = [result.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(RuntimeError, match="Failed to validate worker output"):
            await driver.generate(prompt="generate", schema=SampleSchema)

    async def test_missing_result_raises(self) -> None:
        """Worker that emits no RESULT should raise RuntimeError."""
        from amelia.sandbox.driver import ContainerDriver

        thinking = AgenticMessage(
            type=AgenticMessageType.THINKING, content="Thinking...",
        )
        lines = [thinking.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(RuntimeError, match="Worker did not emit a RESULT message"):
            await driver.generate(prompt="generate")

    async def test_empty_prompt_raises(self) -> None:
        """Empty prompt should raise ValueError."""
        from amelia.sandbox.driver import ContainerDriver

        provider = _make_provider_mock([])
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            await driver.generate(prompt="")

    async def test_usage_captured(self) -> None:
        """USAGE message should be captured for get_usage()."""
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(type=AgenticMessageType.RESULT, content="Done")
        usage = DriverUsage(input_tokens=200, output_tokens=100, model="test")
        usage_msg = AgenticMessage(type=AgenticMessageType.USAGE, usage=usage)
        lines = [result.model_dump_json(), usage_msg.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        await driver.generate(prompt="test")

        result_usage = driver.get_usage()
        assert result_usage is not None
        assert result_usage.input_tokens == 200


class TestCleanupSession:
    """Tests for ContainerDriver.cleanup_session()."""

    async def test_returns_false(self) -> None:
        """cleanup_session should return False (stateless)."""
        from amelia.sandbox.driver import ContainerDriver

        provider = _make_provider_mock([])
        driver = ContainerDriver(model="test", provider=provider)

        result = await driver.cleanup_session("any-session-id")
        assert result is False


class TestGetUsage:
    """Tests for ContainerDriver.get_usage()."""

    def test_returns_none_before_execution(self) -> None:
        """get_usage should return None before any execution."""
        from amelia.sandbox.driver import ContainerDriver

        provider = _make_provider_mock([])
        driver = ContainerDriver(model="test", provider=provider)

        assert driver.get_usage() is None
```

### Step 2: Run tests to verify they fail

Run: `uv run pytest tests/unit/sandbox/test_container_driver.py -v`
Expected: FAIL — `amelia.sandbox.driver` module doesn't exist

### Step 3: Implement ContainerDriver

Create `amelia/sandbox/driver.py`:

```python
"""ContainerDriver — DriverInterface implementation for sandboxed execution.

Delegates LLM execution to a container worker via SandboxProvider.exec_stream().
The worker runs inside a Docker container and streams AgenticMessage JSON lines.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
    GenerateResult,
)
from amelia.sandbox.provider import SandboxProvider


class ContainerDriver:
    """Driver that executes LLM operations inside a sandbox container.

    Implements DriverInterface by delegating to a SandboxProvider.
    The provider manages the container lifecycle; this driver handles
    prompt delivery, output parsing, and usage tracking.

    Args:
        model: LLM model identifier passed to the worker.
        provider: SandboxProvider managing the container.
    """

    def __init__(self, model: str, provider: SandboxProvider) -> None:
        self.model = model
        self._provider = provider
        self._last_usage: DriverUsage | None = None

    async def _write_prompt(self, prompt: str) -> str:
        """Write prompt to a temp file in the container.

        Args:
            prompt: The prompt text to write.

        Returns:
            Path to the prompt file inside the container.
        """
        prompt_path = f"/tmp/prompt-{uuid4().hex[:12]}.txt"
        async for _ in self._provider.exec_stream(
            ["tee", prompt_path],
            stdin=prompt.encode(),
        ):
            pass  # tee output not needed
        return prompt_path

    async def _cleanup_prompt(self, prompt_path: str) -> None:
        """Remove the prompt file from the container.

        Args:
            prompt_path: Path to remove.
        """
        async for _ in self._provider.exec_stream(["rm", "-f", prompt_path]):
            pass

    def _parse_line(self, line: str) -> AgenticMessage:
        """Parse a JSON line into AgenticMessage.

        Args:
            line: Raw JSON string from worker stdout.

        Returns:
            Parsed AgenticMessage.

        Raises:
            RuntimeError: If line is not valid JSON or not a valid AgenticMessage.
        """
        try:
            return AgenticMessage.model_validate_json(line)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"Failed to parse worker output: {line[:200]}"
            ) from exc

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
        allowed_tools: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgenticMessage]:
        """Execute prompt with autonomous tool use inside the container.

        Args:
            prompt: The prompt to send.
            cwd: Working directory for tool execution.
            session_id: Unused (stateless driver).
            instructions: Optional system instructions.
            schema: Unused for agentic execution.
            allowed_tools: Unused (worker manages tools).
            **kwargs: Ignored.

        Yields:
            AgenticMessage for each event (USAGE messages captured, not yielded).

        Raises:
            ValueError: If prompt is empty.
            RuntimeError: On malformed output or worker failure.
        """
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        await self._provider.ensure_running()
        prompt_path = await self._write_prompt(prompt)

        try:
            cmd = [
                "python", "-m", "amelia.sandbox.worker", "agentic",
                "--prompt-file", prompt_path,
                "--cwd", cwd,
                "--model", self.model,
            ]
            if instructions:
                cmd.extend(["--instructions", instructions])

            async for line in self._provider.exec_stream(cmd, cwd=cwd):
                msg = self._parse_line(line)
                if msg.type == AgenticMessageType.USAGE:
                    self._last_usage = msg.usage
                else:
                    yield msg
        finally:
            await self._cleanup_prompt(prompt_path)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Generate a response from the model inside the container.

        Args:
            prompt: The user prompt.
            system_prompt: Unused.
            schema: Optional Pydantic model to validate output.
            **kwargs: Ignored.

        Returns:
            GenerateResult tuple of (output, session_id=None).

        Raises:
            ValueError: If prompt is empty.
            RuntimeError: On malformed output, missing RESULT, or schema validation failure.
        """
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        await self._provider.ensure_running()
        prompt_path = await self._write_prompt(prompt)

        try:
            cmd = [
                "python", "-m", "amelia.sandbox.worker", "generate",
                "--prompt-file", prompt_path,
                "--model", self.model,
            ]
            if schema:
                cmd.extend(["--schema", f"{schema.__module__}:{schema.__name__}"])

            result_content: str | None = None
            async for line in self._provider.exec_stream(cmd):
                msg = self._parse_line(line)
                if msg.type == AgenticMessageType.USAGE:
                    self._last_usage = msg.usage
                elif msg.type == AgenticMessageType.RESULT:
                    result_content = msg.content
        finally:
            await self._cleanup_prompt(prompt_path)

        if result_content is None:
            raise RuntimeError("Worker did not emit a RESULT message")

        if schema:
            try:
                output = schema.model_validate_json(result_content)
            except (ValidationError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Failed to validate worker output against {schema.__name__}: "
                    f"{result_content[:200]}"
                ) from exc
            return output, None

        return result_content, None

    def get_usage(self) -> DriverUsage | None:
        """Return accumulated usage from last execution."""
        return self._last_usage

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up session state. Always returns False (stateless)."""
        return False
```

### Step 4: Run tests to verify they pass

Run: `uv run pytest tests/unit/sandbox/test_container_driver.py -v`
Expected: All PASS

### Step 5: Run the factory container-branch tests that were deferred

Run: `uv run pytest tests/unit/drivers/test_factory.py -v`
Expected: All PASS (ContainerDriver now exists)

### Step 6: Commit

```bash
git add amelia/sandbox/driver.py tests/unit/sandbox/test_container_driver.py
git commit -m "feat(sandbox): implement ContainerDriver with DriverInterface protocol"
```

---

## Task 6: Network Allowlist — Pure Function

**Files:**
- Create: `amelia/sandbox/network.py`
- Create: `tests/unit/sandbox/test_network.py`

### Step 1: Write the failing tests

Create `tests/unit/sandbox/test_network.py`:

```python
"""Unit tests for network allowlist rule generation."""
import pytest


class TestGenerateAllowlistRules:
    """Tests for generate_allowlist_rules()."""

    def test_default_rules_structure(self) -> None:
        """Should generate rules with established, loopback, DNS, proxy, and DROP."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        assert "ESTABLISHED,RELATED" in rules
        assert "-i lo -j ACCEPT" in rules
        assert "--dport 53" in rules
        assert "host.docker.internal" in rules
        assert "-j DROP" in rules

    def test_custom_hosts_included(self) -> None:
        """Custom hosts should appear in the generated rules."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(
            allowed_hosts=["api.example.com", "cdn.example.com"],
        )

        assert "api.example.com" in rules
        assert "cdn.example.com" in rules

    def test_proxy_always_allowed(self) -> None:
        """Proxy host should always be in rules regardless of allowed_hosts."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        assert "host.docker.internal" in rules

    def test_custom_proxy_host(self) -> None:
        """Should use custom proxy host when specified."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(
            allowed_hosts=[], proxy_host="custom-proxy.local",
        )

        assert "custom-proxy.local" in rules
        assert "host.docker.internal" not in rules

    def test_empty_host_list_still_allows_infra(self) -> None:
        """With no custom hosts, should still allow DNS + loopback + proxy."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        lines = rules.strip().split("\n")
        # Must have at least: flush + established + loopback + DNS(2) + proxy + DROP
        assert len(lines) >= 6

    def test_drop_is_last_rule(self) -> None:
        """DROP should be the final iptables rule."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=["example.com"])

        iptables_lines = [
            line for line in rules.strip().split("\n")
            if line.startswith("iptables")
        ]
        assert iptables_lines[-1].endswith("-j DROP")

    def test_output_is_valid_shell(self) -> None:
        """Output should start with shebang and set -e."""
        from amelia.sandbox.network import generate_allowlist_rules

        rules = generate_allowlist_rules(allowed_hosts=[])

        assert rules.startswith("#!/bin/sh\nset -e\n")
```

### Step 2: Run tests to verify they fail

Run: `uv run pytest tests/unit/sandbox/test_network.py -v`
Expected: FAIL — module doesn't exist

### Step 3: Implement `generate_allowlist_rules`

Create `amelia/sandbox/network.py`:

```python
"""Network allowlist rule generation for sandbox containers.

Generates iptables rules that restrict outbound connections to approved
hosts only. The generated script is applied inside the container by
setup-network.sh.
"""


def generate_allowlist_rules(
    allowed_hosts: list[str],
    proxy_host: str = "host.docker.internal",
) -> str:
    """Generate iptables rules for the network allowlist.

    Returns a shell script that:
    1. Flushes existing OUTPUT rules
    2. Allows established/related connections
    3. Allows loopback
    4. Allows DNS (UDP + TCP port 53)
    5. Allows the proxy host (LLM + git credentials)
    6. Resolves and allows each configured host
    7. DROPs everything else

    Args:
        allowed_hosts: Hostnames to allow outbound connections to.
        proxy_host: Host running the LLM/git proxy.

    Returns:
        Shell script string with iptables rules.
    """
    lines = [
        "#!/bin/sh",
        "set -e",
        "",
        "# Flush existing OUTPUT rules",
        "iptables -F OUTPUT",
        "",
        "# Allow established/related connections",
        "iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
        "",
        "# Allow loopback",
        "iptables -A OUTPUT -o lo -j ACCEPT",
        "iptables -A INPUT -i lo -j ACCEPT",
        "",
        "# Allow DNS (UDP + TCP)",
        "iptables -A OUTPUT -p udp --dport 53 -j ACCEPT",
        "iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT",
        "",
        f"# Allow proxy host ({proxy_host})",
        f'PROXY_IP=$(getent hosts {proxy_host} | awk \'{{print $1}}\')',
        'if [ -n "$PROXY_IP" ]; then',
        '    iptables -A OUTPUT -d "$PROXY_IP" -j ACCEPT',
        "fi",
    ]

    if allowed_hosts:
        lines.append("")
        lines.append("# Allow configured hosts")
        for host in allowed_hosts:
            lines.append(f'HOST_IP=$(getent hosts {host} | awk \'{{print $1}}\')')
            lines.append('if [ -n "$HOST_IP" ]; then')
            lines.append(f'    iptables -A OUTPUT -d "$HOST_IP" -j ACCEPT')
            lines.append("fi")

    lines.extend([
        "",
        "# Drop everything else",
        "iptables -A OUTPUT -j DROP",
    ])

    return "\n".join(lines) + "\n"
```

### Step 4: Run tests to verify they pass

Run: `uv run pytest tests/unit/sandbox/test_network.py -v`
Expected: All PASS

### Step 5: Commit

```bash
git add amelia/sandbox/network.py tests/unit/sandbox/test_network.py
git commit -m "feat(sandbox): add network allowlist rule generation"
```

---

## Task 7: Create `setup-network.sh` Script

**Files:**
- Create: `amelia/sandbox/scripts/setup-network.sh`

### Step 1: Create the script

Create `amelia/sandbox/scripts/setup-network.sh`:

```bash
#!/bin/sh
# setup-network.sh — Applies iptables network allowlist rules inside the container.
#
# This script receives generated iptables rules via stdin and executes them.
# It is called by DockerSandboxProvider.ensure_running() when
# network_allowlist_enabled is true.
#
# Usage:
#   echo "$RULES" | sh /opt/amelia/scripts/setup-network.sh
set -e

# Read rules from stdin and execute them
sh -s
```

### Step 2: Commit

```bash
chmod +x amelia/sandbox/scripts/setup-network.sh
git add amelia/sandbox/scripts/setup-network.sh
git commit -m "feat(sandbox): add setup-network.sh for iptables allowlist"
```

---

## Task 8: Server Teardown — `teardown_all_sandbox_containers`

**Files:**
- Create: `amelia/sandbox/teardown.py`
- Create: `tests/unit/sandbox/test_teardown.py`
- Modify: `amelia/server/main.py:225-238` (shutdown block)

### Step 1: Write the failing tests

Create `tests/unit/sandbox/test_teardown.py`:

```python
"""Unit tests for sandbox container teardown."""
from unittest.mock import AsyncMock, patch

import pytest


class TestTeardownAllSandboxContainers:
    """Tests for teardown_all_sandbox_containers()."""

    async def test_stops_running_containers(self) -> None:
        """Should find and remove all amelia-sandbox-* containers."""
        from amelia.sandbox.teardown import teardown_all_sandbox_containers

        # Mock docker ps returning two container IDs
        mock_ps = AsyncMock()
        mock_ps.communicate = AsyncMock(return_value=(b"abc123\ndef456\n", b""))
        mock_ps.returncode = 0

        mock_rm = AsyncMock()
        mock_rm.communicate = AsyncMock(return_value=(b"", b""))
        mock_rm.returncode = 0

        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_ps
            return mock_rm

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
            await teardown_all_sandbox_containers()

        # Should have called docker ps once, then docker rm once
        assert call_count == 2

    async def test_no_containers_is_noop(self) -> None:
        """Should do nothing when no containers are running."""
        from amelia.sandbox.teardown import teardown_all_sandbox_containers

        mock_ps = AsyncMock()
        mock_ps.communicate = AsyncMock(return_value=(b"", b""))
        mock_ps.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_ps):
            await teardown_all_sandbox_containers()

        # Only docker ps was called, no docker rm
        mock_ps.communicate.assert_called_once()

    async def test_handles_docker_not_available(self) -> None:
        """Should handle gracefully when docker is not available."""
        from amelia.sandbox.teardown import teardown_all_sandbox_containers

        mock_ps = AsyncMock()
        mock_ps.communicate = AsyncMock(return_value=(b"", b"Cannot connect"))
        mock_ps.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_ps):
            # Should not raise
            await teardown_all_sandbox_containers()
```

### Step 2: Run tests to verify they fail

Run: `uv run pytest tests/unit/sandbox/test_teardown.py -v`
Expected: FAIL — module doesn't exist

### Step 3: Implement `teardown_all_sandbox_containers`

Create `amelia/sandbox/teardown.py`:

```python
"""Sandbox container teardown utilities.

Provides functions to clean up sandbox containers during server shutdown.
"""
import asyncio

from loguru import logger


async def teardown_all_sandbox_containers() -> None:
    """Stop and remove all amelia-sandbox-* containers.

    Queries Docker directly for containers matching the naming convention,
    then removes them. Handles cases where Docker is unavailable or no
    containers exist.
    """
    try:
        ps_proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-q", "--filter", "name=amelia-sandbox-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await ps_proc.communicate()

        if ps_proc.returncode != 0:
            logger.warning(
                "Failed to list sandbox containers",
                error=stderr.decode().strip(),
            )
            return

        container_ids = [
            cid for cid in stdout.decode().strip().split("\n") if cid
        ]
        if not container_ids:
            logger.debug("No sandbox containers to clean up")
            return

        logger.info(
            "Tearing down sandbox containers",
            count=len(container_ids),
        )
        rm_proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", *container_ids,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, rm_stderr = await rm_proc.communicate()

        if rm_proc.returncode != 0:
            logger.warning(
                "Failed to remove some containers",
                error=rm_stderr.decode().strip(),
            )
        else:
            logger.info("Sandbox containers removed", count=len(container_ids))

    except FileNotFoundError:
        logger.debug("Docker not found, skipping sandbox teardown")
```

### Step 4: Run tests to verify they pass

Run: `uv run pytest tests/unit/sandbox/test_teardown.py -v`
Expected: All PASS

### Step 5: Wire teardown into server lifespan

In `amelia/server/main.py`, add the import near the sandbox proxy import (around line 59):

```python
from amelia.sandbox.teardown import teardown_all_sandbox_containers
```

Then in the shutdown block (after `await lifecycle.shutdown()`, around line 232), add:

```python
    await teardown_all_sandbox_containers()
```

The shutdown section should look like:

```python
    # Shutdown - stop components in reverse order
    await event_bus.cleanup()
    await connection_manager.close_all(code=1001, reason="Server shutting down")

    await health_checker.stop()
    await lifecycle.shutdown()
    await teardown_all_sandbox_containers()
    clear_orchestrator()
    await exit_stack.aclose()

    await database.close()
    clear_database()
    clear_config()
```

### Step 6: Commit

```bash
git add amelia/sandbox/teardown.py tests/unit/sandbox/test_teardown.py amelia/server/main.py
git commit -m "feat(sandbox): add container teardown on server shutdown"
```

---

## Task 9: Export ContainerDriver from `amelia/sandbox/__init__.py`

**Files:**
- Modify: `amelia/sandbox/__init__.py`

### Step 1: Add ContainerDriver to exports

In `amelia/sandbox/__init__.py`:

1. Add to `TYPE_CHECKING` block:
```python
    from amelia.sandbox.driver import ContainerDriver
```

2. Add `"ContainerDriver"` to `__all__` list.

3. Add lazy import branch in `__getattr__`:
```python
    if name == "ContainerDriver":
        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        return ContainerDriver
```

### Step 2: Verify import works

Run: `uv run python -c "from amelia.sandbox import ContainerDriver; print(ContainerDriver)"`
Expected: `<class 'amelia.sandbox.driver.ContainerDriver'>`

### Step 3: Commit

```bash
git add amelia/sandbox/__init__.py
git commit -m "feat(sandbox): export ContainerDriver from sandbox package"
```

---

## Task 10: Full Test Suite Verification

### Step 1: Run all sandbox tests

Run: `uv run pytest tests/unit/sandbox/ -v`
Expected: All PASS

### Step 2: Run all driver tests

Run: `uv run pytest tests/unit/drivers/ -v`
Expected: All PASS

### Step 3: Run all agent tests

Run: `uv run pytest tests/unit/agents/ -v`
Expected: All PASS

### Step 4: Run core type tests

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: All PASS

### Step 5: Run full unit test suite

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

### Step 6: Run linting and type checking

Run: `uv run ruff check amelia tests`
Run: `uv run mypy amelia`
Expected: No errors

### Step 7: Final commit (if any linting fixes needed)

```bash
git add -A
git commit -m "chore: fix lint/type errors from PR3 changes"
```

---

## Dependency Graph

```
Task 1 (AgentConfig fields)
  └─→ Task 2 (get_agent_config injection)
       └─→ Task 4 (Agent constructors)
Task 3 (Factory signature) ─→ Task 5 (ContainerDriver)
Task 6 (Network allowlist) — independent
Task 7 (setup-network.sh) — independent
Task 8 (Server teardown) — independent
Task 9 (Exports) — after Task 5
Task 10 (Full verification) — after all
```

**Parallelizable groups:**
- Tasks 1–2 (config threading) can run in parallel with Tasks 6–8 (network + teardown)
- Task 3 (factory) can start after Task 1 but before Task 2
- Tasks 6, 7, 8 are all independent of each other

---

## Files Changed Summary

| File | Action | Task |
|------|--------|------|
| `amelia/core/types.py` | Modify | 1, 2 |
| `amelia/drivers/factory.py` | Modify | 3 |
| `amelia/agents/architect.py` | Modify (1 line) | 4 |
| `amelia/agents/developer.py` | Modify (1 line) | 4 |
| `amelia/agents/reviewer.py` | Modify (1 line) | 4 |
| `amelia/sandbox/driver.py` | Create | 5 |
| `amelia/sandbox/network.py` | Create | 6 |
| `amelia/sandbox/scripts/setup-network.sh` | Create | 7 |
| `amelia/sandbox/teardown.py` | Create | 8 |
| `amelia/server/main.py` | Modify (2 lines) | 8 |
| `amelia/sandbox/__init__.py` | Modify | 9 |
| `tests/unit/core/test_types.py` | Modify | 1, 2 |
| `tests/unit/drivers/test_factory.py` | Create | 3 |
| `tests/unit/agents/test_developer.py` | Modify | 4 |
| `tests/unit/sandbox/test_container_driver.py` | Create | 5 |
| `tests/unit/sandbox/test_network.py` | Create | 6 |
| `tests/unit/sandbox/test_teardown.py` | Create | 8 |
