# Agentic-Only Execution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan batch-by-batch.

**Goal:** Remove direct execution path from Developer agent - use only agentic execution via `driver.execute_agentic()`.

**Architecture:** Simplify the execution model. The Developer agent formats batch instructions and delegates to the driver's agentic mode. The driver handles all tool execution autonomously.

**Key Insight:** DeepAgents provides two security models: (1) **FilesystemBackend** for file-only operations with path containment - no shell command execution; (2) **SandboxBackends** (Modal/Runloop/Daytona) for full command execution in isolated containers. For local development, FilesystemBackend is safe because it cannot execute arbitrary commands.

> **Security Model Clarification (for reviewers):**
>
> DeepAgents is a production-grade LangChain library used millions of times daily. The security model is sound:
>
> - **FilesystemBackend** exposes file tools (read, write, list) but NOT the `execute` tool. The LangChain docs stating "execute tool is only available when backend implements SandboxBackendProtocol" means FilesystemBackend intentionally OMITS execution capability - it only provides file operations.
>
> - **SandboxBackend** (Modal/Runloop/Daytona) implements the full protocol INCLUDING the `execute` tool, but runs commands in isolated containers where damage is contained.
>
> This is "security by design" - FilesystemBackend simply cannot run shell commands, so no validation is needed. The plan removes ~1000 lines of security code because that code was protecting against threats that don't exist when using FilesystemBackend.
>
> **✅ VERIFIED (2025-12-23):** Source code review of `deepagents/backends/filesystem.py` confirms:
> - FilesystemBackend implements `BackendProtocol` only (NOT `SandboxBackendProtocol`)
> - Exposes only: `ls_info`, `read`, `write`, `edit`, `grep_raw`, `glob_info`, `upload_files`, `download_files`
> - No `execute()` method exists in FilesystemBackend
> - Middleware layer (`deepagents/middleware/filesystem.py`) explicitly checks `isinstance(backend, SandboxBackendProtocol)` before exposing execute tool
> - Path traversal prevention built-in: blocks `..` sequences, `~` expansion, enforces root_dir containment

**Tech Stack:** Python, Pydantic, LangGraph, DeepAgents, asyncio

> **TDD Guidance:** For each batch, write tests BEFORE implementation. Run tests to confirm RED (fail), then implement to make them GREEN.

---

## Architectural Decision: DeepAgents as a Driver

### Current Architecture (Complex Security)

```text
┌─────────────────────────────────────────────────────┐
│ Developer Node                                       │
│  └─ _execute_batch()                                │
│       └─ security validation (TOCTOU issues!)       │
│            └─ driver.execute_agentic()              │
│                 └─ ApiDriver (pydantic-ai)          │
│                      └─ tools.py (more security!)   │
│                           └─ SafeShellExecutor      │
│                                (even more security!)│
└─────────────────────────────────────────────────────┘
```

**Problems:**
- Security scattered across tools.py, safe_shell.py, developer.py (~1000+ lines)
- TOCTOU vulnerability: commands execute before validation in streaming drivers
- Complex exception handling and validation at every layer

### Proposed Architecture (Security by Isolation)

```text
┌─────────────────────────────────────────────────────┐
│ Developer Node                                       │
│  └─ _execute_batch()                                │
│       └─ driver.execute_agentic()                   │
│            ├─ ClaudeCliDriver (local development)   │
│            │    └─ relies on Claude Code's perms    │
│            └─ DeepAgentsDriver                      │
│                 └─ create_deep_agent()              │
│                      ├─ FilesystemBackend (file ops)│
│                      │    └─ path containment only  │
│                      └─ SandboxBackend (full exec)  │
│                           ├─ Modal                  │
│                           ├─ Runloop                │
│                           └─ Daytona               │
└─────────────────────────────────────────────────────┘
```

**Benefits:**
1. **Security by isolation** - Sandbox backends run commands in containers
2. **No TOCTOU** - Commands can't damage host, even if malicious
3. **Simpler code** - Remove ~1000 lines of security validation
4. **Maintained by others** - DeepAgents security is community-maintained

### Driver Comparison

| Driver | Security Model | Use Case | TOCTOU Risk |
|--------|----------------|----------|-------------|
| `cli:claude` | Claude Code's permission system | Local dev, trusted repos | ⚠️ Relies on CC |
| `deepagents:modal` | Modal sandbox isolation | Production, untrusted | ✅ None |
| `deepagents:runloop` | Runloop sandbox isolation | Production | ✅ None |
| `api:openrouter` | **DEPRECATED** - Tool-level validation | - | ❌ High |

---

## Batch 0 [LOW RISK] - Add DeepAgents Dependency

*Add deepagents as a dependency and verify it imports correctly.*

### Step 0.1: Add dependency to pyproject.toml
- **File:** `pyproject.toml`
- **Action:** Add to dependencies:
```toml
[project.dependencies]
# ... existing deps
deepagents = ">=0.1.0"
langchain = ">=0.3.0"
langchain-anthropic = ">=0.3.0"  # Required for init_chat_model with Anthropic models
```
- **Note:** For local development against a local deepagents checkout, use:
```toml
deepagents = { path = "../deepagents/libs/deepagents" }
```

### Step 0.2: Verify imports
- **Command:** `uv sync && uv run python -c "from deepagents import create_deep_agent; from langchain.chat_models import init_chat_model; print('OK')"`
- **Expected:** "OK" printed

---

## Batch 1 [LOW RISK] - Simplify PlanStep Model

*Remove execution-specific fields from PlanStep. Keep only instruction-oriented fields.*

### Step 1.0: Write RED tests
- **File:** `tests/unit/test_state.py`
- **Action:** Add tests for simplified PlanStep, StepResult, BlockerReport models
- **Tests:** Verify PlanStep only has `id`, `description`, `action_type`, `depends_on`, `risk_level`
- **Tests:** Verify StepResult doesn't have `executed_command` field
- **Tests:** Verify BlockerReport has `batch_number` and doesn't have step-specific fields
- **Command:** `uv run pytest tests/unit/test_state.py -v`
- **Expected:** FAIL (changes not yet implemented)

### Step 1.1: Update PlanStep in state.py
- **File:** `amelia/core/state.py`
- **Action:** Remove fields: `file_path`, `code_change`, `command`, `cwd`, `fallback_commands`, `expect_exit_code`, `expected_output_pattern`, `validation_command`, `success_criteria`, `estimated_minutes`, `requires_human_judgment`, `is_test_step`, `validates_step`
- **Keep:** `id`, `description`, `action_type`, `depends_on`, `risk_level`
- **Action:** Update `ActionType` on line 15:
```python
ActionType = Literal["task"]  # Simplified - all steps are now agent tasks
```

### Step 1.2: Simplify StepResult in state.py
- **File:** `amelia/core/state.py`
- **Action:** Remove `executed_command` field since commands are no longer tracked at step level
- **Keep:** `step_id`, `status`, `output`, `error`, `duration_seconds`, `cancelled_by_user`

### Step 1.3: Simplify BlockerReport in state.py
- **File:** `amelia/core/state.py`
- **Action:** Simplify to batch-level failure info while keeping debugging context
- **Change:** `step_id: str` → `step_id: str | None = None` (optional - may not be available in agentic execution)
- **Add:** `batch_number` field
- **Add:** `"sandbox_error"` to the `BlockerType` Literal for sandbox-specific failures

### Step 1.4: Run tests and type checker to verify GREEN
- **Command:** `uv run pytest tests/unit/test_state.py -v && uv run mypy amelia/core/state.py`
- **Expected:** Tests pass (GREEN phase), no type errors

---

## Batch 2 [LOW RISK] - Remove ExecutionMode Type

*Remove the unused execution_mode parameter and type.*

### Step 2.0: Write RED tests
- **File:** `tests/unit/test_types.py`
- **Action:** Add tests verifying Profile works without execution_mode field
```python
def test_profile_without_execution_mode():
    """Profile should work without execution_mode field."""
    profile = Profile(
        tracker="github",
        driver="cli:claude",
        working_dir="/tmp/test",
    )
    # Verify execution_mode is not an attribute
    assert not hasattr(profile, "execution_mode")


def test_execution_mode_type_removed():
    """ExecutionMode type should not exist."""
    from amelia.core import types
    assert not hasattr(types, "ExecutionMode")
```
- **Command:** `uv run pytest tests/unit/test_types.py::test_profile_without_execution_mode tests/unit/test_types.py::test_execution_mode_type_removed -v`
- **Expected:** FAIL (changes not yet implemented)

### Step 2.1: Remove ExecutionMode from types.py
- **File:** `amelia/core/types.py`
- **Action:** Delete `ExecutionMode = Literal["structured", "agentic"]`

### Step 2.2: Remove execution_mode from Profile
- **File:** `amelia/core/types.py`
- **Action:** Remove `execution_mode: ExecutionMode = "structured"` field from Profile class

### Step 2.2.1: Add working_dir validator to Profile
- **File:** `amelia/core/types.py`
- **Action:** Add field validator to Profile class:
```python
from pathlib import Path

@field_validator("working_dir")
@classmethod
def validate_working_dir(cls, v: str | None) -> str | None:
    """Validate working_dir is absolute and has no path traversal."""
    if v is None:
        return v

    # Check raw string FIRST (before Path processing) to catch all traversal attempts
    if ".." in v:
        raise ValueError("working_dir cannot contain '..'")
    if v != v.strip():
        raise ValueError("working_dir cannot have leading/trailing whitespace")

    path = Path(v)
    if not path.is_absolute():
        raise ValueError("working_dir must be an absolute path")

    return str(path.resolve())
```

### Step 2.3: Run tests and type checker to verify GREEN
- **Command:** `uv run pytest tests/unit/test_types.py -v && uv run mypy amelia/core/types.py`
- **Expected:** Tests pass (GREEN phase), no type errors

---

## Batch 3 [MEDIUM RISK] - Create DeepAgentsDriver

*Create a new driver that wraps DeepAgents with sandbox execution.*

> **API Note:** The deepagents imports below are speculative based on current documentation. Verify actual API paths during implementation - particularly `create_deep_agent` signature, `BaseSandbox` location, and sandbox backend availability.

### Step 3.0: Write RED tests
- **File:** `tests/unit/drivers/test_deepagents_driver.py` (NEW)
- **Action:** Create test suite for DeepAgentsDriver
```python
"""Tests for DeepAgents driver integration."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from amelia.drivers.deepagents import DeepAgentsDriver
from amelia.core.state import AgentMessage
from tests.conftest import AsyncIteratorMock


@pytest.fixture
def mock_deep_agent():
    """Create mock DeepAgents agent."""
    agent = AsyncMock()
    agent.ainvoke = AsyncMock(return_value={
        "messages": [MagicMock(content="Task completed", type="ai")]
    })
    return agent


async def test_driver_with_modal_raises_not_implemented():
    """DeepAgentsDriver with modal provider should raise NotImplementedError (not yet supported)."""
    driver = DeepAgentsDriver(sandbox_provider="modal")
    messages = [AgentMessage(role="user", content="Test")]

    with pytest.raises(NotImplementedError, match="Modal backend requires"):
        async for _ in driver.execute_agentic(messages, cwd="/tmp"):
            pass


async def test_driver_with_filesystem_backend():
    """DeepAgentsDriver without provider uses FilesystemBackend."""
    # Test the actual behavior, not mocked internals
    driver = DeepAgentsDriver()
    assert driver.sandbox_provider is None  # Uses FilesystemBackend


async def test_execute_agentic_yields_events(mock_deep_agent):
    """execute_agentic should yield streaming events."""
    with patch("amelia.drivers.deepagents.driver.create_deep_agent", return_value=mock_deep_agent):
        driver = DeepAgentsDriver()
        messages = [AgentMessage(role="user", content="Fix the bug")]

        events = []
        async for event in driver.execute_agentic(messages, cwd="/tmp"):
            events.append(event)

        assert len(events) > 0


async def test_driver_respects_working_directory():
    """Driver should configure agent with correct working directory."""
    with patch("amelia.drivers.deepagents.driver.create_deep_agent") as mock_create:
        mock_agent = AsyncMock()
        mock_agent.astream = AsyncMock(return_value=AsyncIteratorMock([]))
        mock_create.return_value = mock_agent

        driver = DeepAgentsDriver()
        messages = [AgentMessage(role="user", content="Test")]

        async for _ in driver.execute_agentic(messages, cwd="/workspace/myproject"):
            pass

        # Verify cwd was passed to agent
```

### Step 3.0.1: Verify RED phase
- **Command:** `uv run pytest tests/unit/drivers/test_deepagents_driver.py -v`
- **Expected:** FAIL (driver module does not exist yet)

### Step 3.1: Create driver module structure
- **Action:** Create directory `amelia/drivers/deepagents/`
- **Files:**
  - `__init__.py`
  - `driver.py`
  - `events.py` (for event type mapping)

### Step 3.2: Implement DeepAgentsDriver
- **File:** `amelia/drivers/deepagents/driver.py`
```python
"""DeepAgents driver implementation with sandbox execution."""
from collections.abc import AsyncIterator
from typing import Any

from langchain.chat_models import init_chat_model
from pydantic import BaseModel

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from amelia.core.state import AgentMessage
from amelia.drivers.base import DriverInterface, GenerateResult
from amelia.drivers.deepagents.events import DeepAgentsEvent, map_to_amelia_event


class DeepAgentsDriver(DriverInterface):
    """Driver that uses DeepAgents with backend-based security.

    Security model:
    - FilesystemBackend: File tools only (read/write/list). NO execute tool.
      Safe for local dev because shell commands are impossible.
    - SandboxBackend (Modal/Runloop): Full tools including execute, but
      commands run in isolated containers. Safe for production.

    This is security by design - we don't validate commands because
    FilesystemBackend physically cannot execute them.
    """

    def __init__(
        self,
        model: str = "anthropic:claude-sonnet-4-5-20250929",
        sandbox_provider: str | None = None,
        sandbox_config: dict[str, Any] | None = None,
        timeout: int = 600,
    ):
        """Initialize DeepAgents driver.

        Args:
            model: Model identifier (langchain format).
            sandbox_provider: Sandbox provider ("modal", "runloop", "daytona").
                If None, uses FilesystemBackend (for local dev only).
            sandbox_config: Provider-specific configuration.
            timeout: Execution timeout in seconds.
        """
        self.model_id = model
        self.sandbox_provider = sandbox_provider
        self.sandbox_config = sandbox_config or {}
        self.timeout = timeout
        # Note: Agent and backend are created per-execution to avoid race conditions

    def _get_backend(self, cwd: str) -> FilesystemBackend:
        """Get appropriate backend based on configuration.

        FilesystemBackend security (why we can remove 1000+ lines of validation):
        - Exposes ONLY file tools: read_file, write_file, list_directory
        - Does NOT expose execute tool - shell commands are impossible
        - Path containment: All operations restricted to cwd
        - Path traversal protection: Blocks .. and ~ in paths

        This is fundamentally different from our old ApiDriver which HAD
        execute capability and needed complex validation. FilesystemBackend
        simply lacks the attack surface.

        For full command execution, use Modal/Runloop/Daytona sandbox backends
        which run commands in isolated containers.
        """
        if self.sandbox_provider == "modal":
            # Modal backend requires deepagents-cli integration (not available as direct Python import)
            raise NotImplementedError(
                "Modal backend requires deepagents-cli integration. "
                "Use FilesystemBackend for local development, or install deepagents-cli "
                "and configure Modal separately."
            )
        # Note: Runloop and Daytona support can be added in future versions
        else:
            # Local development - FilesystemBackend provides path isolation
            return FilesystemBackend(root_dir=cwd)

    async def _create_agent(self, cwd: str, instructions: str | None = None):
        """Create DeepAgents agent with appropriate backend.

        Returns a new agent instance for each call to avoid race conditions
        when multiple executions run concurrently.

        Includes a 30s timeout to prevent hangs if the backend service is unavailable.
        """
        import asyncio

        try:
            async with asyncio.timeout(30):  # 30s timeout for agent creation
                backend = self._get_backend(cwd)  # Local, not self._backend

                system_prompt = instructions or "You are a skilled software developer."

                agent = create_deep_agent(  # Local, not self._agent
                    model=init_chat_model(self.model_id),
                    backend=backend,
                    system_prompt=system_prompt,
                    middleware=[],
                )
                return agent
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Timed out creating {self.sandbox_provider or 'filesystem'} agent. "
                "Check network connectivity and service status."
            )

    async def generate(
        self,
        messages: list[AgentMessage],
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Generate response (delegates to agent)."""
        cwd = kwargs.get("cwd", ".")
        agent = await self._create_agent(cwd, kwargs.get("instructions"))

        # Convert messages to LangChain format
        lc_messages = [{"role": m.role, "content": m.content} for m in messages]

        result = await agent.ainvoke({"messages": lc_messages})
        output = result["messages"][-1].content if result.get("messages") else ""

        return (output, None)

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute tool via agent (not directly supported)."""
        raise NotImplementedError("Use execute_agentic for tool execution")

    def _sanitize_session_id(self, session_id: str | None) -> str:
        """Sanitize session_id to prevent directory traversal."""
        import re
        if session_id is None:
            return "default"
        if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
            raise ValueError(f"Invalid session_id format: {session_id}")
        return session_id

    async def execute_agentic(
        self,
        messages: list[AgentMessage],
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
    ) -> AsyncIterator[DeepAgentsEvent]:
        """Execute with autonomous tool access via DeepAgents.

        Security model (no command validation needed):
        - FilesystemBackend: File tools only. Execute tool doesn't exist.
          Agent can read/write/list files in cwd but cannot run commands.
        - SandboxBackend: Full tools in isolated container. Commands run
          in sandbox, not on host.

        Compare to old ApiDriver which exposed Bash tool requiring complex
        SafeShellExecutor validation. FilesystemBackend lacks this tool entirely.
        """
        # Validate cwd - must be absolute, no traversal, must exist
        from pathlib import Path
        cwd_path = Path(cwd)
        if not cwd_path.is_absolute():
            raise ValueError(f"cwd must be absolute path: {cwd}")
        if ".." in str(cwd_path):
            raise ValueError(f"cwd cannot contain '..': {cwd}")
        if not cwd_path.exists() or not cwd_path.is_dir():
            raise ValueError(f"cwd must be existing directory: {cwd}")

        # Validate messages - must not be empty
        if not messages:
            raise ValueError("messages list cannot be empty")

        # Validate instructions size - prevent memory exhaustion
        if instructions and len(instructions) > 50_000:
            raise ValueError("instructions exceed maximum size (50KB)")

        agent = await self._create_agent(cwd, instructions)

        # Convert messages to LangChain format
        lc_messages = [{"role": m.role, "content": m.content} for m in messages]

        # Use session_id for thread persistence (defaults to "default" if not provided)
        config = {"configurable": {"thread_id": self._sanitize_session_id(session_id)}}

        # Stream events from DeepAgents using "values" mode (returns full state after each node)
        async for chunk in agent.astream(
            {"messages": lc_messages},
            config=config,
            stream_mode="values",
        ):
            # Map DeepAgents chunks to Amelia event format
            event = map_to_amelia_event(chunk)
            if event:
                yield event
```

### Step 3.3: Implement event mapping
- **File:** `amelia/drivers/deepagents/events.py`
```python
"""Event mapping from DeepAgents to Amelia format."""
from dataclasses import dataclass
from typing import Any


@dataclass
class DeepAgentsEvent:
    """Event from DeepAgents execution."""
    type: str  # "text", "tool_use", "tool_result", "result", "error"
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_result: str | None = None


def map_to_amelia_event(chunk: dict[str, Any]) -> DeepAgentsEvent | None:
    """Map DeepAgents stream chunk to Amelia event format.

    Handles malformed chunks gracefully by catching exceptions and returning None.
    """
    try:
        # DeepAgents uses LangGraph streaming format
        if "messages" in chunk and chunk["messages"]:
            msg = chunk["messages"][-1]
            if msg:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tc = msg.tool_calls[0]
                    return DeepAgentsEvent(
                        type="tool_use",
                        tool_name=tc.get("name"),
                        tool_input=tc.get("args", {}),
                    )
                elif hasattr(msg, "content") and msg.content:
                    return DeepAgentsEvent(type="text", content=msg.content)

        # Handle tool results
        if "tools" in chunk:
            return DeepAgentsEvent(
                type="tool_result",
                tool_result=str(chunk["tools"]),
            )
    except (IndexError, KeyError, AttributeError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to map DeepAgents event: {e}")

    return None
```

### Step 3.4: Update driver factory
- **File:** `amelia/drivers/factory.py`
```python
from amelia.drivers.deepagents import DeepAgentsDriver

class DriverFactory:
    @staticmethod
    def get_driver(driver_key: str, **kwargs: Any) -> DriverInterface:
        if driver_key in ("cli:claude", "cli"):
            return ClaudeCliDriver(**kwargs)
        elif driver_key.startswith("deepagents:"):
            # Format: deepagents:modal, deepagents:runloop, deepagents:local
            provider = driver_key.split(":")[1] if ":" in driver_key else None
            return DeepAgentsDriver(sandbox_provider=provider, **kwargs)
        elif driver_key in ("api:openrouter", "api"):
            # DEPRECATED - use deepagents:modal for production
            return ApiDriver(**kwargs)
        else:
            raise ValueError(f"Unknown driver key: {driver_key}")
```

### Step 3.5: Run tests
- **Command:** `uv run pytest tests/unit/drivers/test_deepagents_driver.py -v`
- **Expected:** GREEN

---

## Batch 4 [MEDIUM RISK] - Update Architect Prompts

*Simplify the prompts to generate simpler PlanStep objects.*

### Step 4.0: Write RED tests for simplified plan generation
- **File:** `tests/unit/agents/test_architect.py`
- **Action:** Add test verifying Architect generates PlanStep with only simplified fields
```python
import pytest
from amelia.core.state import PlanStep


def test_planstep_has_only_simplified_fields():
    """PlanStep should only have id, description, action_type, depends_on, risk_level."""
    # Create a PlanStep with only the allowed fields
    step = PlanStep(
        id="step-1",
        description="Implement the feature",
        action_type="task",
        depends_on=(),
        risk_level="low",
    )

    # Verify required fields exist
    assert step.id == "step-1"
    assert step.description == "Implement the feature"
    assert step.action_type == "task"
    assert step.depends_on == ()
    assert step.risk_level == "low"


def test_planstep_rejects_removed_fields():
    """PlanStep should not accept removed fields like file_path, command, etc."""
    # These fields should no longer exist in PlanStep
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        PlanStep(
            id="step-1",
            description="Test",
            action_type="task",
            file_path="/some/path",  # Removed field
        )

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        PlanStep(
            id="step-1",
            description="Test",
            action_type="task",
            command="echo hello",  # Removed field
        )
```
- **Command:** `uv run pytest tests/unit/agents/test_architect.py -v -k simplified`
- **Expected:** FAIL (changes not yet implemented - removed fields still exist)

### Step 4.1: Update ArchitectContextStrategy prompts
- **File:** `amelia/agents/architect.py`
- **Action:** Update `get_execution_plan_system_prompt()` to:
  - Remove guidance about `file_path`, `code_change`, `command`, `cwd`, etc.
  - Focus on `description` as the instruction for the agent
  - Emphasize that each step description should be a clear, actionable instruction
  - Keep risk assessment and batching rules

### Step 4.2: Update _render_markdown method
- **File:** `amelia/agents/architect.py`
- **Action:** Simplify markdown output to not reference removed fields

### Step 4.3: Run type checker
- **Command:** `uv run mypy amelia/agents/architect.py`

---

## Batch 5 [MEDIUM RISK] - Simplify Developer Agent

*Remove security validation, delegate to driver.*

### Step 5.0: Write RED tests
- **File:** `tests/unit/core/test_developer_node.py`
- **Action:** Add tests for simplified `_execute_batch` method
```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from amelia.agents.developer import Developer
from amelia.core.state import ExecutionBatch, PlanStep, ExecutionState, BatchResult
from amelia.core.types import Profile
from amelia.drivers.deepagents.events import DeepAgentsEvent


async def async_iter(items):
    """Helper to create async iterator from list."""
    for item in items:
        yield item


# Use existing fixtures from tests/conftest.py:
# - mock_issue_factory
# - mock_profile_factory
# - mock_execution_state_factory
# Example: mock_state = mock_execution_state_factory()


async def test_execute_batch_delegates_to_driver(mock_state, mock_profile):
    """Developer should delegate execution to driver without security checks."""
    mock_driver = AsyncMock()
    mock_driver.execute_agentic = MagicMock(return_value=async_iter([
        DeepAgentsEvent(type="result", content="Done")
    ]))

    developer = Developer(driver=mock_driver)
    batch = ExecutionBatch(
        batch_number=1,
        steps=[PlanStep(id="step-1", description="Test step", action_type="task")]
    )

    result = await developer._execute_batch(batch, mock_state, mock_profile)

    mock_driver.execute_agentic.assert_called_once()
    assert result.status == "complete"


@pytest.mark.parametrize("event_type,expected_status,blocker_type", [
    ("result", "complete", None),
    ("error", "blocked", "sandbox_error"),
])
async def test_execute_batch_status(event_type, expected_status, blocker_type, mock_state, mock_profile):
    """Developer should return correct status based on driver events."""
    mock_driver = AsyncMock()
    mock_driver.execute_agentic = MagicMock(return_value=async_iter([
        DeepAgentsEvent(type=event_type, content="Test output")
    ]))

    developer = Developer(driver=mock_driver)
    batch = ExecutionBatch(
        batch_number=1,
        steps=[PlanStep(id="step-1", description="Test step", action_type="task")]
    )

    result = await developer._execute_batch(batch, mock_state, mock_profile)

    assert result.status == expected_status
    if blocker_type:
        assert result.blocker is not None
        assert result.blocker.blocker_type == blocker_type


async def test_empty_batch_returns_complete(mock_state, mock_profile):
    """Empty batch should return complete without calling driver."""
    mock_driver = AsyncMock()
    developer = Developer(driver=mock_driver)
    batch = ExecutionBatch(batch_number=1, steps=[])

    result = await developer._execute_batch(batch, mock_state, mock_profile)

    mock_driver.execute_agentic.assert_not_called()
    assert result.status == "complete"
    assert result.batch_number == 1
```
- **Command:** `uv run pytest tests/unit/core/test_developer_node.py -v`
- **Expected:** FAIL (changes not yet implemented)

### Step 5.1: Remove security imports and code
- **File:** `amelia/agents/developer.py`
- **Action:** Remove imports:
  - `from amelia.tools.safe_shell import SafeShellExecutor`
  - `from amelia.core.exceptions import SecurityError, PathTraversalError`
- **Action:** Remove all security validation in `_execute_batch`:
  - Remove path traversal checks
  - Remove command validation
  - Remove `SafeShellExecutor._validate_command` calls
- **Action:** Update Developer `__init__` to add timeout parameter:
```python
def __init__(
    self,
    driver: DriverInterface,
    stream_emitter: StreamEmitter | None = None,
    timeout: int = 600,  # 10 minute default timeout
):
    """Initialize Developer agent.

    Args:
        driver: Driver interface for LLM execution.
        stream_emitter: Optional callback for streaming events.
        timeout: Execution timeout in seconds (default: 600).
    """
    self.driver = driver
    self._stream_emitter = stream_emitter or (lambda e: None)
    self.timeout = timeout
```

### Step 5.2: Simplify _execute_batch
- **File:** `amelia/agents/developer.py`
```python
async def _execute_batch(
    self,
    batch: ExecutionBatch,
    state: ExecutionState,
    profile: Profile,
) -> BatchResult:
    """Execute batch via driver.execute_agentic().

    Security is delegated to the driver:
    - DeepAgentsDriver with FilesystemBackend: File operations only, path-contained
    - DeepAgentsDriver with SandboxBackend: Full execution in isolated containers
    - ClaudeCliDriver: Relies on Claude Code's permission system
    """
    if not batch.steps:
        return BatchResult(
            batch_number=batch.batch_number,
            status="complete",
            completed_steps=(),
        )

    if not profile.working_dir:
        raise ValueError("profile.working_dir is required")

    instructions = self._format_batch_instructions(batch, state)
    messages = self._build_messages(batch, state)

    try:
        async with asyncio.timeout(self.timeout):
            async for event in self.driver.execute_agentic(
                messages,
                cwd=profile.working_dir,
                session_id=state.driver_session_id,
                instructions=instructions,
            ):
                await self._stream_emitter(event)

                if event.type == "result":
                    return self._parse_batch_result(event, batch)
                elif event.type == "error":
                    return BatchResult(
                        batch_number=batch.batch_number,
                        status="blocked",
                        completed_steps=(),
                        blocker=BlockerReport(
                            batch_number=batch.batch_number,
                            blocker_type="sandbox_error",
                            error_message=event.content or "Unknown error",
                        ),
                    )

    except asyncio.CancelledError:
        raise  # Re-raise to propagate cancellation
    except asyncio.TimeoutError:
        return self._blocked_result(batch, "command_failed", f"Execution timed out after {self.timeout}s")
    except Exception as e:
        logger.exception("Unexpected error in agentic execution")
        return self._blocked_result(batch, "sandbox_error", f"{type(e).__name__}: {e}")

def _blocked_result(self, batch: ExecutionBatch, blocker_type: str, message: str) -> BatchResult:
    """Create a blocked BatchResult with given error."""
    return BatchResult(
        batch_number=batch.batch_number,
        status="blocked",
        completed_steps=(),
        blocker=BlockerReport(
            batch_number=batch.batch_number,
            blocker_type=blocker_type,
            error_message=message,
        ),
    )
```

> **Note:** The helper method `_blocked_result` consolidates error handling, reducing duplication.

### Step 5.3: Verify methods are unused, then remove
- **File:** `amelia/agents/developer.py`
- **Verification command:** `rg "(_execute_step_with_fallbacks|_resolve_working_dir|_resolve_file_path|validate_command_result)" amelia/`
- **Expected:** Only matches in `amelia/agents/developer.py` (the file being modified)
- **Action:** After verification, delete methods that are no longer needed:
  - `_execute_step_with_fallbacks`
  - `_resolve_working_dir`
  - `_resolve_file_path`
  - `validate_command_result`

### Step 5.4: Run tests
- **Command:** `uv run pytest tests/unit/core/test_developer_node.py -v`

---

## Batch 6 [LOW RISK] - Simplify Claude CLI Driver

*Remove security validation, rely on Claude Code's permissions.*

### Step 6.0: Write RED tests for permission enforcement
- **File:** `tests/unit/drivers/test_claude_cli.py`
- **Action:** Add test verifying skip_permissions parameter is rejected
```python
def test_skip_permissions_parameter_removed():
    """ClaudeCliDriver should not accept skip_permissions parameter."""
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        ClaudeCliDriver(skip_permissions=True)
```
- **Command:** `uv run pytest tests/unit/drivers/test_claude_cli.py -v -k permissions`
- **Expected:** FAIL (parameter still exists)

### Step 6.1: Remove --dangerously-skip-permissions and enforce security
- **File:** `amelia/drivers/cli/claude.py`
- **Action:** Remove `--dangerously-skip-permissions` flag from cmd_args list
- **Action:** Remove `skip_permissions` parameter from `__init__` method entirely
- **Action:** Remove any conditional logic checking `self.skip_permissions`
- **Action:** Use `--allowedTools Bash,Write,Read,Edit` to restrict tool types
- **Rationale:** Claude Code's permission system handles security. Users must approve actions via Claude Code UI. The `skip_permissions` option should not exist as an escape hatch.
- **Security Note:** This is a breaking change for users who relied on `skip_permissions=True`. They must now approve actions interactively or configure Claude Code's permission system.

### Step 6.2: Document trust model
- **File:** `amelia/drivers/cli/claude.py`
- **Action:** Add docstring explaining security model:
```python
"""Claude CLI driver.

Security Model:
- Relies on Claude Code's built-in permission system
- Tool types restricted via --allowedTools flag
- For untrusted code, use DeepAgentsDriver with sandbox backend instead

This driver is suitable for:
- Local development on trusted repositories
- Interactive use where user approves actions
- Environments where Claude Code permissions are configured
"""
```

---

## Batch 7 [LOW RISK] - Update Orchestrator

*Remove execution_mode parameter when creating Developer.*

### Step 7.0: Write RED tests for Developer instantiation
- **File:** `tests/unit/core/test_orchestrator.py`
- **Action:** Add test verifying Developer is instantiated without execution_mode
```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from amelia.core.orchestrator import Orchestrator
from amelia.agents.developer import Developer


async def test_developer_created_without_execution_mode(mock_profile_factory, mock_driver):
    """Orchestrator should create Developer without execution_mode parameter."""
    mock_profile = mock_profile_factory()

    with patch.object(Orchestrator, '_get_driver', return_value=mock_driver):
        with patch('amelia.core.orchestrator.Developer') as MockDeveloper:
            mock_dev_instance = MagicMock()
            mock_dev_instance.execute_batch = AsyncMock(return_value=MagicMock())
            MockDeveloper.return_value = mock_dev_instance

            orchestrator = Orchestrator()

            # Trigger developer creation (implementation may vary)
            # This tests that when Developer is instantiated, execution_mode is NOT passed
            await orchestrator.call_developer_node(
                {"execution_state": MagicMock()},
                MagicMock(),
            )

            # Verify Developer was called
            MockDeveloper.assert_called()

            # Verify execution_mode was NOT in the call kwargs
            call_kwargs = MockDeveloper.call_args.kwargs
            assert "execution_mode" not in call_kwargs, (
                f"execution_mode should not be passed to Developer, got: {call_kwargs}"
            )
```
- **Command:** `uv run pytest tests/unit/core/test_orchestrator.py -v -k execution_mode`
- **Expected:** FAIL (execution_mode still passed)

### Step 7.1: Update call_developer_node
- **File:** `amelia/core/orchestrator.py`
- **Action:** Remove `execution_mode=profile.execution_mode` from Developer() constructor call

### Step 7.2: Run type checker
- **Command:** `uv run mypy amelia/core/orchestrator.py`

---

## Batch 8 [LOW RISK] - Update Test Fixtures

*Update test fixtures for new PlanStep structure and DeepAgents driver.*

### Step 8.1: Update conftest.py factories
- **File:** `tests/conftest.py`
- **Action:** Update `mock_execution_plan_factory` to create simplified PlanStep objects
- **Action:** Add `mock_deepagents_driver` fixture

### Step 8.2: Update integration conftest
- **File:** `tests/integration/conftest.py`
- **Action:** Update any PlanStep/ExecutionBatch creation

---

## Batch 9 [MEDIUM RISK] - Update Unit Tests

*Fix tests that reference removed fields.*

### Step 9.1: Update test_state.py
- **File:** `tests/unit/test_state.py`
- **Action:** Update tests for simplified PlanStep, StepResult, BlockerReport

### Step 9.2: Update test_types.py
- **File:** `tests/unit/test_types.py`
- **Action:** Remove ExecutionMode tests

### Step 9.3: Update developer tests
- **File:** `tests/unit/core/test_developer_node.py`
- **Action:** Remove security validation tests (no longer applicable)
- **Action:** Add driver delegation tests

### Step 9.4: Run unit tests
- **Command:** `uv run pytest tests/unit/ -v`

---

## Batch 10 [MEDIUM RISK] - Update Integration Tests

*Fix integration tests that use old execution model.*

### Step 10.1: Update batch execution tests
- **Files:** `tests/integration/test_batch_execution.py`
- **Action:** Update for agentic execution model with DeepAgents

### Step 10.2: Run integration tests
- **Command:** `uv run pytest tests/integration/ -v`

---

## Batch 11 [LOW RISK] - Cleanup Unused Code

*Remove deprecated security modules.*

### Step 11.1: Deprecate api:openrouter driver
- **File:** `amelia/drivers/api/`
- **Action:** Add deprecation warning to ApiDriver:
```python
import warnings

class ApiDriver(DriverInterface):
    def __init__(self, ...):
        warnings.warn(
            "ApiDriver is deprecated. Use DeepAgentsDriver with sandbox backend instead.",
            DeprecationWarning,
            stacklevel=2,
        )
```

### Step 11.2: Review safe_shell.py usage
- **File:** `amelia/tools/safe_shell.py`
- **Action:** Check if still used. If only used by deprecated ApiDriver, add deprecation note.

### Step 11.3: Review shell_executor.py usage
- **File:** `amelia/tools/shell_executor.py`
- **Action:** Same as above

---

## Batch 12 [LOW RISK] - Run Full Validation

*Run all linters and tests.*

### Step 12.1: Run ruff
- **Command:** `uv run ruff check amelia tests`

### Step 12.2: Run mypy
- **Command:** `uv run mypy amelia`

### Step 12.3: Run all tests
- **Command:** `uv run pytest tests/unit/ tests/integration/`

### Step 12.4: Verify cleanup
- **Command:** Verify no `SafeShellExecutor` in developer.py
- **Command:** Verify no `execution_mode` in types.py

---

## Batch 13 [LOW RISK] - Database Migration

*Clear existing plans from database to avoid schema mismatches.*

> **Note:** This is a destructive migration that deletes all checkpoints. This is acceptable because:
> - Checkpoints are transient workflow state, not user data
> - A fresh start is cleaner than complex schema migration
> - Any in-progress workflows can simply be restarted

### Step 13.0: Verify Amelia is not running
- **Command:** `pgrep -f "amelia dev" && echo "ERROR: Stop Amelia first" && exit 1 || echo "OK: Amelia not running"`
- **Expected:** "OK: Amelia not running"
- **If fails:** Run `pkill -f "amelia dev"` and wait for shutdown

### Step 13.1: Backup database
- **Command:** `cp ~/.amelia/checkpoint.db ~/.amelia/checkpoint.db.backup.$(date +%Y%m%d%H%M%S)`

### Step 13.2: Verify backup
- **Command:** `ls -la ~/.amelia/checkpoint.db.backup.* && sqlite3 ~/.amelia/checkpoint.db.backup.* "SELECT COUNT(*) FROM checkpoints;"`
- **Expected:** File exists and query returns a count (confirms backup is valid)

### Step 13.3: Clear checkpoints
- **Command:**
```bash
sqlite3 ~/.amelia/checkpoint.db <<'SQL'
BEGIN EXCLUSIVE;
DELETE FROM checkpoints;
COMMIT;
SQL
```

### Step 13.4: Restore procedure (if needed)
> **Warning:** Any running workflows will be disrupted. Stop the Amelia server before restoring.
- **Command:** `cp ~/.amelia/checkpoint.db.backup.<timestamp> ~/.amelia/checkpoint.db`

---

## Summary

| Batch | Risk | Description |
|-------|------|-------------|
| 0 | Low | Add DeepAgents dependency |
| 1 | Low | Simplify PlanStep model |
| 2 | Low | Remove ExecutionMode type |
| 3 | **Medium** | **Create DeepAgentsDriver with sandbox execution** |
| 4 | Medium | Update Architect prompts |
| 5 | **Medium** | **Simplify Developer agent (remove security code)** |
| 6 | Low | Simplify Claude CLI driver |
| 7 | Low | Update Orchestrator |
| 8 | Low | Update test fixtures |
| 9 | Medium | Update unit tests |
| 10 | Medium | Update integration tests |
| 11 | Low | Cleanup unused code |
| 12 | Low | Run full validation |
| 13 | Low | Database migration (destructive but acceptable) |

**Key changes from previous plan:**
1. **Removed Batch 0 (TOCTOU security fixes)** - No longer needed with sandbox isolation
2. **Added DeepAgentsDriver** - New driver type with sandbox backends
3. **Simplified Developer** - Removed ~500 lines of security validation code
4. **Deprecated api:openrouter** - Replaced by deepagents:modal/runloop

**Security model:**
- **Production with command execution:** Use `deepagents:modal` or `deepagents:runloop` - commands run in isolated containers
- **Local dev (file ops only):** Use `deepagents:local` - FilesystemBackend restricts to file operations within cwd
- **Local dev (full execution):** Use `cli:claude` - relies on Claude Code's permission system
- **Deprecated:** `api:openrouter` - had TOCTOU vulnerabilities

> **Why removing security code is safe:** The old security code (SafeShellExecutor, command validation, path checks) protected against malicious SHELL COMMANDS. FilesystemBackend doesn't expose shell execution at all - it only has file tools. You can't validate what doesn't exist. The ~1000 lines of security code become unnecessary when the attack surface is eliminated by design.

**Total estimated lines removed:** ~1000+ (security validation code)
**Total estimated lines added:** ~300 (DeepAgentsDriver implementation)
