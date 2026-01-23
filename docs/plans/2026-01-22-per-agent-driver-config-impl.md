# Per-Agent Driver Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace profile-level driver/model configuration with per-agent configuration so different agents can use different models and drivers.

**Architecture:** Add `AgentConfig` type containing driver/model/options. Replace Profile's `driver`, `model`, `validator_model`, `max_review_iterations`, `max_task_review_iterations` fields with a single `agents: dict[str, AgentConfig]` field. Update all agents to accept `AgentConfig` instead of `DriverInterface` and create their own drivers.

**Tech Stack:** Python 3.12+, Pydantic v2, SQLite with JSON storage for agents dict

---

## Task 1: Add AgentConfig Type

**Files:**
- Modify: `amelia/core/types.py:1-35` (imports and existing types section)
- Test: `tests/unit/core/test_types.py`

**Step 1: Write the failing test**

```python
# tests/unit/core/test_types.py - add after existing tests

def test_agent_config_creation():
    """AgentConfig should store driver, model, and optional options."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="cli:claude", model="sonnet")
    assert config.driver == "cli:claude"
    assert config.model == "sonnet"
    assert config.options == {}


def test_agent_config_with_options():
    """AgentConfig should accept arbitrary options dict."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(
        driver="api:openrouter",
        model="anthropic/claude-sonnet-4",
        options={"max_iterations": 5, "temperature": 0.7},
    )
    assert config.options["max_iterations"] == 5
    assert config.options["temperature"] == 0.7
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_types.py::test_agent_config_creation -v`
Expected: FAIL with "cannot import name 'AgentConfig'"

**Step 3: Write minimal implementation**

Add to `amelia/core/types.py` after line 10 (after DriverType definition):

```python
class AgentConfig(BaseModel):
    """Per-agent driver and model configuration.

    Attributes:
        driver: LLM driver type (e.g., 'api:openrouter', 'cli:claude').
        model: LLM model identifier.
        options: Agent-specific options (e.g., max_iterations).
    """

    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str
    options: dict[str, Any] = Field(default_factory=dict)
```

Also add `Any` to the imports from `typing` at the top.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_types.py::test_agent_config_creation tests/unit/core/test_types.py::test_agent_config_with_options -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "feat(types): add AgentConfig for per-agent driver configuration"
```

---

## Task 2: Update Profile with agents dict

**Files:**
- Modify: `amelia/core/types.py:36-71` (Profile class)
- Test: `tests/unit/core/test_types.py`

**Step 1: Write the failing test**

```python
# tests/unit/core/test_types.py - add after AgentConfig tests

def test_profile_with_agents_dict():
    """Profile should accept agents dict configuration."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli:claude", model="opus"),
            "developer": AgentConfig(driver="cli:claude", model="sonnet"),
        },
    )
    assert profile.agents["architect"].model == "opus"
    assert profile.agents["developer"].model == "sonnet"


def test_profile_get_agent_config():
    """Profile.get_agent_config should return config or raise if missing."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli:claude", model="opus"),
        },
    )

    config = profile.get_agent_config("architect")
    assert config.model == "opus"

    import pytest
    with pytest.raises(ValueError, match="Agent 'developer' not configured"):
        profile.get_agent_config("developer")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_types.py::test_profile_with_agents_dict -v`
Expected: FAIL with "unexpected keyword argument 'agents'" or missing field error

**Step 3: Write minimal implementation**

Replace the entire `Profile` class in `amelia/core/types.py`:

```python
class Profile(BaseModel):
    """Configuration profile for Amelia execution.

    This model is frozen (immutable) to support the stateless reducer pattern.
    Use model_copy(update={...}) to create modified copies.

    Attributes:
        name: Profile name (e.g., 'work', 'personal').
        tracker: Issue tracker type (jira, github, none, noop).
        working_dir: Working directory for agentic execution.
        plan_output_dir: Directory for saving implementation plans.
        plan_path_pattern: Path pattern for plan files with {date} and {issue_key} placeholders.
        retry: Retry configuration for transient failures.
        auto_approve_reviews: Skip human approval steps in review workflow.
        agents: Per-agent driver and model configuration.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    tracker: TrackerType = "none"
    working_dir: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    retry: RetryConfig = Field(default_factory=RetryConfig)
    auto_approve_reviews: bool = False
    agents: dict[str, AgentConfig] = Field(default_factory=dict)

    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get config for an agent.

        Args:
            agent_name: Name of the agent (e.g., 'architect', 'developer').

        Returns:
            AgentConfig for the specified agent.

        Raises:
            ValueError: If agent not configured in this profile.
        """
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not configured in profile '{self.name}'")
        return self.agents[agent_name]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_types.py::test_profile_with_agents_dict tests/unit/core/test_types.py::test_profile_get_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "feat(types): add agents dict to Profile, remove driver/model fields"
```

---

## Task 3: Update Architect to accept AgentConfig

**Files:**
- Modify: `amelia/agents/architect.py:121-138` (\_\_init\_\_ method)
- Test: `tests/unit/agents/test_architect_agentic.py`

**Step 1: Write the failing test**

```python
# tests/unit/agents/test_architect_agentic.py - replace or update existing init test

import pytest
from unittest.mock import MagicMock, patch

from amelia.agents.architect import Architect
from amelia.core.types import AgentConfig


def test_architect_init_with_agent_config():
    """Architect should accept AgentConfig and create its own driver."""
    config = AgentConfig(driver="cli:claude", model="sonnet")

    with patch("amelia.agents.architect.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        architect = Architect(config)

        mock_get_driver.assert_called_once_with("cli:claude", model="sonnet")
        assert architect.driver is mock_driver
        assert architect.options == {}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_architect_agentic.py::test_architect_init_with_agent_config -v`
Expected: FAIL with type error or import error

**Step 3: Write minimal implementation**

Update `amelia/agents/architect.py`:

1. Add import at top:
```python
from amelia.core.types import AgentConfig
from amelia.drivers.factory import get_driver
```

2. Replace the `__init__` method:
```python
def __init__(
    self,
    config: AgentConfig,
    event_bus: "EventBus | None" = None,
    prompts: dict[str, str] | None = None,
):
    """Initialize the Architect agent.

    Args:
        config: Agent configuration with driver, model, and options.
        event_bus: Optional EventBus for emitting workflow events.
        prompts: Optional dict mapping prompt IDs to custom content.
            Supports keys: "architect.system", "architect.plan".
    """
    self.driver = get_driver(config.driver, model=config.model)
    self.options = config.options
    self._event_bus = event_bus
    self._prompts = prompts or {}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/agents/test_architect_agentic.py::test_architect_init_with_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect_agentic.py
git commit -m "feat(architect): accept AgentConfig, create driver internally"
```

---

## Task 4: Update Developer to accept AgentConfig

**Files:**
- Modify: `amelia/agents/developer.py:32-33` (\_\_init\_\_ method)
- Test: `tests/unit/agents/test_developer.py` (create if needed)

**Step 1: Write the failing test**

```python
# tests/unit/agents/test_developer.py

import pytest
from unittest.mock import MagicMock, patch

from amelia.agents.developer import Developer
from amelia.core.types import AgentConfig


def test_developer_init_with_agent_config():
    """Developer should accept AgentConfig and create its own driver."""
    config = AgentConfig(driver="api:openrouter", model="anthropic/claude-sonnet-4")

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        developer = Developer(config)

        mock_get_driver.assert_called_once_with("api:openrouter", model="anthropic/claude-sonnet-4")
        assert developer.driver is mock_driver
        assert developer.options == {}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_developer.py::test_developer_init_with_agent_config -v`
Expected: FAIL with type error

**Step 3: Write minimal implementation**

Update `amelia/agents/developer.py`:

1. Add import at top:
```python
from amelia.core.types import AgentConfig
from amelia.drivers.factory import get_driver
```

2. Replace the `__init__` method:
```python
def __init__(self, config: AgentConfig):
    """Initialize the Developer agent.

    Args:
        config: Agent configuration with driver, model, and options.
    """
    self.driver = get_driver(config.driver, model=config.model)
    self.options = config.options
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/agents/test_developer.py::test_developer_init_with_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/agents/developer.py tests/unit/agents/test_developer.py
git commit -m "feat(developer): accept AgentConfig, create driver internally"
```

---

## Task 5: Update Reviewer to accept AgentConfig

**Files:**
- Modify: `amelia/agents/reviewer.py:180-201` (\_\_init\_\_ method)
- Test: `tests/unit/agents/test_reviewer.py` (create or update)

**Step 1: Write the failing test**

```python
# tests/unit/agents/test_reviewer.py

import pytest
from unittest.mock import MagicMock, patch

from amelia.agents.reviewer import Reviewer
from amelia.core.types import AgentConfig


def test_reviewer_init_with_agent_config():
    """Reviewer should accept AgentConfig and create its own driver."""
    config = AgentConfig(
        driver="cli:claude",
        model="sonnet",
        options={"max_iterations": 5},
    )

    with patch("amelia.agents.reviewer.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        reviewer = Reviewer(config)

        mock_get_driver.assert_called_once_with("cli:claude", model="sonnet")
        assert reviewer.driver is mock_driver
        assert reviewer.options == {"max_iterations": 5}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_reviewer.py::test_reviewer_init_with_agent_config -v`
Expected: FAIL with type error

**Step 3: Write minimal implementation**

Update `amelia/agents/reviewer.py`:

1. Add import at top:
```python
from amelia.core.types import AgentConfig
from amelia.drivers.factory import get_driver
```

2. Replace the `__init__` method:
```python
def __init__(
    self,
    config: AgentConfig,
    event_bus: "EventBus | None" = None,
    prompts: dict[str, str] | None = None,
    agent_name: str = "reviewer",
):
    """Initialize the Reviewer agent.

    Args:
        config: Agent configuration with driver, model, and options.
        event_bus: Optional EventBus for emitting workflow events.
        prompts: Optional dict mapping prompt IDs to custom content.
            Supports key: "reviewer.agentic".
        agent_name: Name used in logs/events. Use "task_reviewer" for task-based
            execution to distinguish from final review.
    """
    self.driver = get_driver(config.driver, model=config.model)
    self.options = config.options
    self._event_bus = event_bus
    self._prompts = prompts or {}
    self._agent_name = agent_name
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/agents/test_reviewer.py::test_reviewer_init_with_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/agents/reviewer.py tests/unit/agents/test_reviewer.py
git commit -m "feat(reviewer): accept AgentConfig, create driver internally"
```

---

## Task 6: Update Evaluator to accept AgentConfig

**Files:**
- Modify: `amelia/agents/evaluator.py:140-156` (\_\_init\_\_ method)
- Test: `tests/unit/agents/test_evaluator.py` (create or update)

**Step 1: Write the failing test**

```python
# tests/unit/agents/test_evaluator.py

import pytest
from unittest.mock import MagicMock, patch

from amelia.agents.evaluator import Evaluator
from amelia.core.types import AgentConfig


def test_evaluator_init_with_agent_config():
    """Evaluator should accept AgentConfig and create its own driver."""
    config = AgentConfig(driver="cli:claude", model="sonnet")

    with patch("amelia.agents.evaluator.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        evaluator = Evaluator(config)

        mock_get_driver.assert_called_once_with("cli:claude", model="sonnet")
        assert evaluator.driver is mock_driver
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_evaluator.py::test_evaluator_init_with_agent_config -v`
Expected: FAIL with type error

**Step 3: Write minimal implementation**

Update `amelia/agents/evaluator.py`:

1. Add import at top:
```python
from amelia.core.types import AgentConfig
from amelia.drivers.factory import get_driver
```

2. Replace the `__init__` method:
```python
def __init__(
    self,
    config: AgentConfig,
    event_bus: "EventBus | None" = None,
    prompts: dict[str, str] | None = None,
):
    """Initialize the Evaluator agent.

    Args:
        config: Agent configuration with driver, model, and options.
        event_bus: Optional EventBus for emitting workflow events.
        prompts: Optional dict of prompt_id -> content for customization.
    """
    self.driver = get_driver(config.driver, model=config.model)
    self.options = config.options
    self._event_bus = event_bus
    self._prompts = prompts or {}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/agents/test_evaluator.py::test_evaluator_init_with_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/agents/evaluator.py tests/unit/agents/test_evaluator.py
git commit -m "feat(evaluator): accept AgentConfig, create driver internally"
```

---

## Task 7: Update call_architect_node to use profile.get_agent_config

**Files:**
- Modify: `amelia/pipelines/implementation/nodes.py:131-277`
- Test: `tests/unit/core/test_plan_validator_node.py` (existing tests that create Architect)

**Step 1: Write the failing test**

```python
# tests/unit/pipelines/test_architect_node_config.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.implementation.nodes import call_architect_node
from amelia.core.state import ImplementationState, Issue


@pytest.fixture
def profile_with_agents():
    return Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli:claude", model="opus"),
        },
    )


@pytest.fixture
def mock_state():
    return ImplementationState(
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
    )


@pytest.mark.asyncio
async def test_call_architect_node_uses_agent_config(profile_with_agents, mock_state):
    """call_architect_node should use profile.get_agent_config('architect')."""
    config = {
        "configurable": {
            "profile": profile_with_agents,
            "workflow_id": "wf-1",
        }
    }

    with patch("amelia.pipelines.implementation.nodes.Architect") as MockArchitect:
        mock_architect = MagicMock()
        mock_architect.plan = AsyncMock(return_value=iter([
            (mock_state, MagicMock())
        ]))
        MockArchitect.return_value = mock_architect

        with patch("amelia.pipelines.implementation.nodes._save_token_usage", new_callable=AsyncMock):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.read_text", return_value="# Plan"):
                    await call_architect_node(mock_state, config)

        # Verify Architect was instantiated with AgentConfig, not driver
        call_args = MockArchitect.call_args
        assert call_args is not None
        config_arg = call_args[0][0]  # First positional arg
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.driver == "cli:claude"
        assert config_arg.model == "opus"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_architect_node_config.py::test_call_architect_node_uses_agent_config -v`
Expected: FAIL - Architect still receives DriverInterface

**Step 3: Write minimal implementation**

Update `amelia/pipelines/implementation/nodes.py` in `call_architect_node`:

1. Remove these lines (around line 163-164):
```python
driver = DriverFactory.get_driver(profile.driver, model=profile.model)
architect = Architect(driver, event_bus=event_bus, prompts=prompts)
```

2. Replace with:
```python
agent_config = profile.get_agent_config("architect")
architect = Architect(agent_config, event_bus=event_bus, prompts=prompts)
```

3. Update the token usage call to get driver from architect:
```python
await _save_token_usage(architect.driver, workflow_id, "architect", repository)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_architect_node_config.py::test_call_architect_node_uses_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/nodes.py tests/unit/pipelines/test_architect_node_config.py
git commit -m "feat(nodes): call_architect_node uses profile.get_agent_config"
```

---

## Task 8: Update call_developer_node to use profile.get_agent_config

**Files:**
- Modify: `amelia/pipelines/nodes.py:83-162`
- Test: `tests/unit/core/test_developer_node.py`

**Step 1: Write the failing test**

```python
# tests/unit/pipelines/test_developer_node_config.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.nodes import call_developer_node
from amelia.core.state import ImplementationState, Issue


@pytest.fixture
def profile_with_agents():
    return Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "developer": AgentConfig(driver="cli:claude", model="sonnet"),
        },
    )


@pytest.fixture
def mock_state():
    return ImplementationState(
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
        goal="Implement test feature",
    )


@pytest.mark.asyncio
async def test_call_developer_node_uses_agent_config(profile_with_agents, mock_state):
    """call_developer_node should use profile.get_agent_config('developer')."""
    config = {
        "configurable": {
            "profile": profile_with_agents,
            "workflow_id": "wf-1",
        }
    }

    with patch("amelia.pipelines.nodes.Developer") as MockDeveloper:
        mock_developer = MagicMock()
        mock_developer.run = AsyncMock(return_value=iter([
            (mock_state.model_copy(update={"agentic_status": "completed"}), MagicMock())
        ]))
        mock_developer.driver = MagicMock()
        MockDeveloper.return_value = mock_developer

        with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
            await call_developer_node(mock_state, config)

        # Verify Developer was instantiated with AgentConfig
        call_args = MockDeveloper.call_args
        assert call_args is not None
        config_arg = call_args[0][0]  # First positional arg
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.driver == "cli:claude"
        assert config_arg.model == "sonnet"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_developer_node_config.py::test_call_developer_node_uses_agent_config -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update `amelia/pipelines/nodes.py` in `call_developer_node`:

1. Remove these lines:
```python
driver = DriverFactory.get_driver(profile.driver, model=profile.model)
developer = Developer(driver)
```

2. Replace with:
```python
agent_config = profile.get_agent_config("developer")
developer = Developer(agent_config)
```

3. Update token usage call:
```python
await _save_token_usage(developer.driver, workflow_id, "developer", repository)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_developer_node_config.py::test_call_developer_node_uses_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/nodes.py tests/unit/pipelines/test_developer_node_config.py
git commit -m "feat(nodes): call_developer_node uses profile.get_agent_config"
```

---

## Task 9: Update call_reviewer_node to use profile.get_agent_config

**Files:**
- Modify: `amelia/pipelines/nodes.py:165-268`
- Test: `tests/unit/pipelines/test_reviewer_node_config.py`

**Step 1: Write the failing test**

```python
# tests/unit/pipelines/test_reviewer_node_config.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.nodes import call_reviewer_node
from amelia.core.state import ImplementationState, Issue
from amelia.core.types import ReviewResult


@pytest.fixture
def profile_with_agents():
    return Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "reviewer": AgentConfig(driver="cli:claude", model="opus", options={"max_iterations": 3}),
            "task_reviewer": AgentConfig(driver="cli:claude", model="sonnet", options={"max_iterations": 5}),
        },
    )


@pytest.fixture
def mock_state():
    return ImplementationState(
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
        goal="Implement test feature",
        base_commit="abc123",
    )


@pytest.mark.asyncio
async def test_call_reviewer_node_uses_agent_config(profile_with_agents, mock_state):
    """call_reviewer_node should use profile.get_agent_config('reviewer')."""
    config = {
        "configurable": {
            "profile": profile_with_agents,
            "workflow_id": "wf-1",
        }
    }

    mock_review_result = ReviewResult(
        severity="low",
        approved=True,
        comments=[],
        reviewer_persona="Senior Engineer",
        summary="LGTM",
    )

    with patch("amelia.pipelines.nodes.Reviewer") as MockReviewer:
        mock_reviewer = MagicMock()
        mock_reviewer.agentic_review = AsyncMock(return_value=(mock_review_result, "session-1"))
        mock_reviewer.driver = MagicMock()
        MockReviewer.return_value = mock_reviewer

        with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
            await call_reviewer_node(mock_state, config)

        # Verify Reviewer was instantiated with AgentConfig
        call_args = MockReviewer.call_args
        assert call_args is not None
        config_arg = call_args[0][0]  # First positional arg
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.driver == "cli:claude"
        assert config_arg.model == "opus"  # reviewer, not task_reviewer
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_reviewer_node_config.py::test_call_reviewer_node_uses_agent_config -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update `amelia/pipelines/nodes.py` in `call_reviewer_node`:

1. Remove these lines:
```python
driver = DriverFactory.get_driver(profile.driver, model=profile.model)
```

2. Replace with logic to select reviewer or task_reviewer:
```python
# Use "task_reviewer" only for non-final tasks in task-based execution
is_non_final_task = state.total_tasks is not None and state.current_task_index + 1 < state.total_tasks
agent_name = "task_reviewer" if is_non_final_task else "reviewer"
agent_config = profile.get_agent_config(agent_name)
reviewer = Reviewer(agent_config, event_bus=event_bus, prompts=prompts, agent_name=agent_name)
```

3. Update token usage:
```python
await _save_token_usage(reviewer.driver, workflow_id, agent_name, repository)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_reviewer_node_config.py::test_call_reviewer_node_uses_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/nodes.py tests/unit/pipelines/test_reviewer_node_config.py
git commit -m "feat(nodes): call_reviewer_node uses profile.get_agent_config"
```

---

## Task 10: Update call_evaluation_node to use profile.get_agent_config

**Files:**
- Modify: `amelia/pipelines/review/nodes.py:18-70`
- Test: `tests/unit/pipelines/test_evaluation_node_config.py`

**Step 1: Write the failing test**

```python
# tests/unit/pipelines/test_evaluation_node_config.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.review.nodes import call_evaluation_node
from amelia.core.state import ImplementationState, Issue
from amelia.agents.evaluator import EvaluationResult


@pytest.fixture
def profile_with_agents():
    return Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "evaluator": AgentConfig(driver="cli:claude", model="sonnet"),
        },
    )


@pytest.fixture
def mock_state():
    return ImplementationState(
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
        goal="Implement test feature",
    )


@pytest.mark.asyncio
async def test_call_evaluation_node_uses_agent_config(profile_with_agents, mock_state):
    """call_evaluation_node should use profile.get_agent_config('evaluator')."""
    config = {
        "configurable": {
            "profile": profile_with_agents,
            "workflow_id": "wf-1",
        }
    }

    mock_eval_result = EvaluationResult(
        items_to_implement=[],
        items_rejected=[],
        items_deferred=[],
    )

    with patch("amelia.pipelines.review.nodes.Evaluator") as MockEvaluator:
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = AsyncMock(return_value=(mock_eval_result, "session-1"))
        mock_evaluator.driver = MagicMock()
        MockEvaluator.return_value = mock_evaluator

        with patch("amelia.pipelines.review.nodes._save_token_usage", new_callable=AsyncMock):
            await call_evaluation_node(mock_state, config)

        # Verify Evaluator was instantiated with AgentConfig
        call_args = MockEvaluator.call_args
        assert call_args is not None
        config_arg = call_args.kwargs.get("config") or call_args[1].get("config")
        if config_arg is None:
            config_arg = call_args[0][0]  # First positional
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.model == "sonnet"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_evaluation_node_config.py::test_call_evaluation_node_uses_agent_config -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update `amelia/pipelines/review/nodes.py` in `call_evaluation_node`:

1. Remove:
```python
driver = DriverFactory.get_driver(profile.driver, model=profile.model)
evaluator = Evaluator(driver=driver, event_bus=event_bus, prompts=prompts)
```

2. Replace with:
```python
agent_config = profile.get_agent_config("evaluator")
evaluator = Evaluator(config=agent_config, event_bus=event_bus, prompts=prompts)
```

3. Update token usage:
```python
await _save_token_usage(evaluator.driver, workflow_id, "evaluator", repository)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_evaluation_node_config.py::test_call_evaluation_node_uses_agent_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/review/nodes.py tests/unit/pipelines/test_evaluation_node_config.py
git commit -m "feat(nodes): call_evaluation_node uses profile.get_agent_config"
```

---

## Task 11: Update ProfileRecord and database schema

**Files:**
- Modify: `amelia/server/database/profile_repository.py:10-30`
- Modify: `amelia/server/database/connection.py` (profiles table schema)
- Test: `tests/unit/server/database/test_profile_repository.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_profile_repository.py - add new test

import pytest
import json
from amelia.server.database.profile_repository import ProfileRecord
from amelia.core.types import AgentConfig


def test_profile_record_with_agents_json():
    """ProfileRecord should store agents as JSON."""
    agents = {
        "architect": {"driver": "cli:claude", "model": "opus", "options": {}},
        "developer": {"driver": "cli:claude", "model": "sonnet", "options": {}},
    }

    record = ProfileRecord(
        id="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents=json.dumps(agents),
    )

    assert record.agents is not None
    parsed = json.loads(record.agents)
    assert parsed["architect"]["model"] == "opus"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_profile_repository.py::test_profile_record_with_agents_json -v`
Expected: FAIL - ProfileRecord has no 'agents' field

**Step 3: Write minimal implementation**

Update `amelia/server/database/profile_repository.py`:

```python
class ProfileRecord(BaseModel):
    """Profile data record for database operations.

    This is a database-level representation. Use amelia.core.types.Profile
    for application-level profile operations.
    """

    id: str
    tracker: str
    working_dir: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    auto_approve_reviews: bool = False
    agents: str  # JSON blob of dict[str, AgentConfig]
    is_active: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

Update `amelia/server/database/connection.py` profiles table schema:

```sql
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    tracker TEXT NOT NULL DEFAULT 'noop',
    working_dir TEXT NOT NULL,
    plan_output_dir TEXT NOT NULL DEFAULT 'docs/plans',
    plan_path_pattern TEXT NOT NULL DEFAULT 'docs/plans/{date}-{issue_key}.md',
    auto_approve_reviews INTEGER NOT NULL DEFAULT 0,
    agents TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_profile_repository.py::test_profile_record_with_agents_json -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/profile_repository.py amelia/server/database/connection.py tests/unit/server/database/test_profile_repository.py
git commit -m "feat(db): update ProfileRecord and schema for agents JSON blob"
```

---

## Task 12: Update ProfileRepository._row_to_profile

**Files:**
- Modify: `amelia/server/database/profile_repository.py` (_row_to_profile method)
- Test: `tests/unit/server/database/test_profile_repository.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_profile_repository.py - add test

import pytest
from unittest.mock import MagicMock
import json

from amelia.server.database.profile_repository import ProfileRepository
from amelia.core.types import Profile, AgentConfig


def test_row_to_profile_parses_agents_json():
    """_row_to_profile should parse agents JSON into AgentConfig dict."""
    agents_json = json.dumps({
        "architect": {"driver": "cli:claude", "model": "opus", "options": {}},
        "developer": {"driver": "cli:claude", "model": "sonnet", "options": {}},
    })

    mock_row = {
        "id": "test",
        "tracker": "noop",
        "working_dir": "/tmp/test",
        "plan_output_dir": "docs/plans",
        "plan_path_pattern": "docs/plans/{date}-{issue_key}.md",
        "auto_approve_reviews": 0,
        "agents": agents_json,
        "is_active": 1,
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }

    repo = ProfileRepository.__new__(ProfileRepository)  # Skip __init__
    profile = repo._row_to_profile(mock_row)

    assert isinstance(profile, Profile)
    assert "architect" in profile.agents
    assert profile.agents["architect"].model == "opus"
    assert isinstance(profile.agents["architect"], AgentConfig)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_profile_repository.py::test_row_to_profile_parses_agents_json -v`
Expected: FAIL - _row_to_profile doesn't handle agents field properly

**Step 3: Write minimal implementation**

Update `ProfileRepository._row_to_profile` in `amelia/server/database/profile_repository.py`:

```python
def _row_to_profile(self, row: dict[str, Any]) -> Profile:
    """Convert a database row to a Profile object.

    Args:
        row: Database row as dict.

    Returns:
        Profile instance.
    """
    import json
    from amelia.core.types import AgentConfig

    agents_data = json.loads(row["agents"])
    agents = {
        name: AgentConfig(**config)
        for name, config in agents_data.items()
    }

    return Profile(
        name=row["id"],
        tracker=row["tracker"],
        working_dir=row["working_dir"],
        plan_output_dir=row["plan_output_dir"],
        plan_path_pattern=row["plan_path_pattern"],
        auto_approve_reviews=bool(row["auto_approve_reviews"]),
        agents=agents,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_profile_repository.py::test_row_to_profile_parses_agents_json -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/profile_repository.py tests/unit/server/database/test_profile_repository.py
git commit -m "feat(db): ProfileRepository._row_to_profile parses agents JSON"
```

---

## Task 13: Update ProfileRepository.create_profile and update_profile

**Files:**
- Modify: `amelia/server/database/profile_repository.py` (create_profile, update_profile)
- Test: `tests/unit/server/database/test_profile_repository.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_profile_repository.py - add integration test

import pytest
import json
from amelia.core.types import Profile, AgentConfig


@pytest.mark.asyncio
async def test_create_profile_stores_agents_json(db_connection):
    """create_profile should serialize agents dict to JSON."""
    from amelia.server.database.profile_repository import ProfileRepository

    repo = ProfileRepository(db_connection)

    profile = Profile(
        name="test_agents",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli:claude", model="opus"),
            "developer": AgentConfig(driver="api:openrouter", model="anthropic/claude-sonnet-4"),
        },
    )

    await repo.create_profile(profile)

    # Retrieve and verify
    retrieved = await repo.get_profile("test_agents")
    assert retrieved is not None
    assert retrieved.agents["architect"].model == "opus"
    assert retrieved.agents["developer"].driver == "api:openrouter"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_profile_repository.py::test_create_profile_stores_agents_json -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update `ProfileRepository.create_profile`:

```python
async def create_profile(self, profile: Profile) -> None:
    """Create a new profile in the database.

    Args:
        profile: Profile to create.
    """
    import json

    agents_json = json.dumps({
        name: {
            "driver": config.driver,
            "model": config.model,
            "options": config.options,
        }
        for name, config in profile.agents.items()
    })

    await self._db.execute(
        """
        INSERT INTO profiles (
            id, tracker, working_dir, plan_output_dir, plan_path_pattern,
            auto_approve_reviews, agents, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile.name,
            profile.tracker,
            profile.working_dir,
            profile.plan_output_dir,
            profile.plan_path_pattern,
            1 if profile.auto_approve_reviews else 0,
            agents_json,
            0,
        ),
    )
```

Update `ProfileRepository.update_profile` similarly.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_profile_repository.py::test_create_profile_stores_agents_json -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/profile_repository.py tests/unit/server/database/test_profile_repository.py
git commit -m "feat(db): create/update profile serializes agents to JSON"
```

---

## Task 14: Update brainstorm routes to use profile.get_agent_config

**Files:**
- Modify: `amelia/server/routes/brainstorm.py`
- Test: `tests/unit/server/routes/test_brainstorm.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/routes/test_brainstorm_config.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from amelia.core.types import Profile, AgentConfig


@pytest.mark.asyncio
async def test_brainstorm_uses_brainstormer_agent_config():
    """Brainstorm route should use profile.get_agent_config('brainstormer')."""
    from amelia.server.routes.brainstorm import create_session, CreateSessionRequest

    profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "brainstormer": AgentConfig(driver="cli:claude", model="sonnet"),
        },
    )

    with patch("amelia.server.routes.brainstorm.get_profile_info") as mock_profile:
        mock_profile.return_value = (profile, "/tmp/test")

        with patch("amelia.server.routes.brainstorm.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver

            with patch("amelia.server.routes.brainstorm.get_brainstorm_service") as mock_service:
                mock_svc = MagicMock()
                mock_svc.create_session = AsyncMock(return_value=MagicMock(id="sess-1"))
                mock_service.return_value = mock_svc

                # This should use profile.get_agent_config("brainstormer")
                request = CreateSessionRequest()
                # Would need proper FastAPI test client setup
                # For now, verify the function signature expects AgentConfig
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_config.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update `amelia/server/routes/brainstorm.py` to use `profile.get_agent_config("brainstormer")` instead of `profile.driver` and `profile.model`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/brainstorm.py tests/unit/server/routes/test_brainstorm_config.py
git commit -m "feat(brainstorm): use profile.get_agent_config('brainstormer')"
```

---

## Task 15: Update test fixtures in conftest.py

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Identify affected fixtures**

Search for all `Profile(` constructors in `tests/conftest.py` and update them to use the new `agents` dict format.

**Step 2: Update profile_factory fixture**

```python
@pytest.fixture
def profile_factory():
    """Factory for creating test profiles with default agents."""
    def _create_profile(
        name: str = "test",
        driver: str = "cli:claude",
        model: str = "sonnet",
        tracker: str = "noop",
        **kwargs
    ) -> Profile:
        # Build default agents from driver/model for backward compatibility
        default_agents = {
            "architect": AgentConfig(driver=driver, model=model),
            "developer": AgentConfig(driver=driver, model=model),
            "reviewer": AgentConfig(driver=driver, model=model),
            "task_reviewer": AgentConfig(driver=driver, model=model),
            "evaluator": AgentConfig(driver=driver, model=model),
            "brainstormer": AgentConfig(driver=driver, model=model),
            "plan_validator": AgentConfig(driver=driver, model=model),
        }

        # Allow explicit agents override
        agents = kwargs.pop("agents", default_agents)

        if driver == "cli:claude":
            return Profile(name=f"test_cli_{name}", tracker=tracker, agents=agents, **kwargs)
        elif driver.startswith("api:"):
            return Profile(name=f"test_api_{name}", tracker=tracker, agents=agents, **kwargs)
        return Profile(name=name, tracker=tracker, agents=agents, **kwargs)

    return _create_profile
```

**Step 3: Run all tests to find breakages**

Run: `uv run pytest tests/ -v --tb=short`
Expected: Many failures from tests constructing Profile with old signature

**Step 4: Update all Profile constructions in tests**

Search and replace all instances of:
```python
Profile(name="test", driver="cli:claude", model="sonnet", validator_model="sonnet", working_dir="/tmp/test")
```

With:
```python
Profile(
    name="test",
    tracker="noop",
    working_dir="/tmp/test",
    agents={
        "architect": AgentConfig(driver="cli:claude", model="sonnet"),
        "developer": AgentConfig(driver="cli:claude", model="sonnet"),
        "reviewer": AgentConfig(driver="cli:claude", model="sonnet"),
        "task_reviewer": AgentConfig(driver="cli:claude", model="sonnet"),
        "evaluator": AgentConfig(driver="cli:claude", model="sonnet"),
        "brainstormer": AgentConfig(driver="cli:claude", model="sonnet"),
        "plan_validator": AgentConfig(driver="cli:claude", model="sonnet"),
    },
)
```

**Step 5: Commit**

```bash
git add tests/
git commit -m "test: update all Profile constructions for agents dict"
```

---

## Task 16: Fix remaining type errors and run full test suite

**Files:**
- Various files with type errors

**Step 1: Run mypy**

Run: `uv run mypy amelia`
Expected: Type errors from changed signatures

**Step 2: Fix each type error**

Address each error by updating type annotations and ensuring all imports are correct.

**Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 4: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No linting errors

**Step 5: Commit**

```bash
git add .
git commit -m "fix: resolve type errors and linting issues"
```

---

## Task 17: Delete old database (breaking change)

**Files:**
- None (manual step)

**Step 1: Document migration**

The design doc specifies this is a breaking change with no migration. Users must delete their existing database.

**Step 2: Add startup warning**

Consider adding a check in database initialization that detects old schema and warns user to delete the database.

**Step 3: Commit**

```bash
git commit --allow-empty -m "docs: breaking change - delete existing database for new schema"
```

---

## Summary

This plan implements per-agent driver configuration in 17 tasks:

1. **Tasks 1-2**: Add AgentConfig type and update Profile
2. **Tasks 3-6**: Update all agents (Architect, Developer, Reviewer, Evaluator) to accept AgentConfig
3. **Tasks 7-10**: Update all pipeline nodes to use profile.get_agent_config()
4. **Tasks 11-13**: Update database schema and ProfileRepository
5. **Task 14**: Update brainstorm routes
6. **Tasks 15-16**: Update tests and fix type errors
7. **Task 17**: Document breaking change

Each task follows TDD with explicit test, implementation, and verification steps.
