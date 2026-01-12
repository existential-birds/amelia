# Per-Agent Driver Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable configuring different drivers and models for each agent (Architect, Developer, Reviewer) in a profile.

**Architecture:** Add typed agent config models (`ArchitectConfig`, `DeveloperConfig`, `ReviewerConfig`) nested inside `Profile`. Each orchestrator node reads its agent's config instead of profile-level `driver`/`model`. Legacy flat configs error with helpful migration message.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest, YAML

---

## Task 1: Add Agent Config Models

**Files:**
- Modify: `amelia/core/types.py:36-72`
- Test: `tests/unit/core/test_types.py` (create)

**Step 1: Write the failing tests**

Create `tests/unit/core/test_types.py`:

```python
"""Tests for agent configuration types."""
import pytest
from pydantic import ValidationError

from amelia.core.types import (
    ArchitectConfig,
    DeveloperConfig,
    ReviewerConfig,
    Profile,
)


class TestArchitectConfig:
    """Tests for ArchitectConfig model."""

    def test_minimal_config(self) -> None:
        """ArchitectConfig requires driver and model."""
        config = ArchitectConfig(driver="cli:claude", model="opus")
        assert config.driver == "cli:claude"
        assert config.model == "opus"
        assert config.validator_model is None

    def test_with_validator_model(self) -> None:
        """ArchitectConfig accepts optional validator_model."""
        config = ArchitectConfig(
            driver="api:openrouter",
            model="claude-3-5-sonnet",
            validator_model="claude-3-5-haiku",
        )
        assert config.validator_model == "claude-3-5-haiku"

    def test_frozen(self) -> None:
        """ArchitectConfig is immutable."""
        config = ArchitectConfig(driver="cli:claude", model="opus")
        with pytest.raises(ValidationError):
            config.model = "haiku"  # type: ignore[misc]


class TestDeveloperConfig:
    """Tests for DeveloperConfig model."""

    def test_minimal_config(self) -> None:
        """DeveloperConfig requires driver and model."""
        config = DeveloperConfig(driver="api:openrouter", model="claude-3-5-haiku")
        assert config.driver == "api:openrouter"
        assert config.model == "claude-3-5-haiku"

    def test_frozen(self) -> None:
        """DeveloperConfig is immutable."""
        config = DeveloperConfig(driver="cli:claude", model="sonnet")
        with pytest.raises(ValidationError):
            config.driver = "api:openrouter"  # type: ignore[misc]


class TestReviewerConfig:
    """Tests for ReviewerConfig model."""

    def test_minimal_config(self) -> None:
        """ReviewerConfig requires driver and model, has default max_iterations."""
        config = ReviewerConfig(driver="cli:claude", model="opus")
        assert config.driver == "cli:claude"
        assert config.model == "opus"
        assert config.max_iterations == 3  # default

    def test_custom_max_iterations(self) -> None:
        """ReviewerConfig accepts custom max_iterations."""
        config = ReviewerConfig(
            driver="api:openrouter",
            model="z-ai/glm-4.7",
            max_iterations=5,
        )
        assert config.max_iterations == 5

    def test_frozen(self) -> None:
        """ReviewerConfig is immutable."""
        config = ReviewerConfig(driver="cli:claude", model="opus")
        with pytest.raises(ValidationError):
            config.max_iterations = 10  # type: ignore[misc]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'ArchitectConfig'`

**Step 3: Write minimal implementation**

Add to `amelia/core/types.py` after `RetryConfig` (around line 34):

```python
class ArchitectConfig(BaseModel):
    """Architect agent configuration.

    Attributes:
        driver: LLM driver type (e.g., 'cli:claude', 'api:openrouter').
        model: Model identifier for the architect agent.
        validator_model: Optional fast model for plan validation.
    """

    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str
    validator_model: str | None = None


class DeveloperConfig(BaseModel):
    """Developer agent configuration.

    Attributes:
        driver: LLM driver type.
        model: Model identifier for the developer agent.
    """

    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str


class ReviewerConfig(BaseModel):
    """Reviewer agent configuration.

    Attributes:
        driver: LLM driver type.
        model: Model identifier for the reviewer agent.
        max_iterations: Maximum review-fix iterations before terminating.
    """

    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str
    max_iterations: int = 3
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: PASS (all 8 tests)

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "feat(types): add ArchitectConfig, DeveloperConfig, ReviewerConfig models"
```

---

## Task 2: Update Profile Model with Nested Agent Configs

**Files:**
- Modify: `amelia/core/types.py:36-72` (Profile class)
- Test: `tests/unit/core/test_types.py` (extend)

**Step 1: Write the failing tests**

Add to `tests/unit/core/test_types.py`:

```python
class TestProfile:
    """Tests for Profile with nested agent configs."""

    def test_profile_with_agent_configs(self) -> None:
        """Profile accepts nested agent configurations."""
        profile = Profile(
            name="work",
            architect=ArchitectConfig(driver="cli:claude", model="opus"),
            developer=DeveloperConfig(driver="api:openrouter", model="haiku"),
            reviewer=ReviewerConfig(driver="api:openrouter", model="glm-4.7"),
            tracker="github",
        )
        assert profile.architect.driver == "cli:claude"
        assert profile.architect.model == "opus"
        assert profile.developer.driver == "api:openrouter"
        assert profile.reviewer.max_iterations == 3

    def test_profile_requires_all_agent_configs(self) -> None:
        """Profile requires architect, developer, and reviewer configs."""
        with pytest.raises(ValidationError) as exc_info:
            Profile(
                name="incomplete",
                architect=ArchitectConfig(driver="cli:claude", model="opus"),
                # missing developer and reviewer
            )
        assert "developer" in str(exc_info.value).lower()

    def test_profile_rejects_legacy_flat_config(self) -> None:
        """Profile rejects legacy flat driver/model with helpful error."""
        with pytest.raises(ValidationError) as exc_info:
            Profile(
                name="legacy",
                driver="cli:claude",  # legacy field
                model="opus",  # legacy field
                tracker="github",
            )
        error_msg = str(exc_info.value)
        assert "deprecated flat config" in error_msg.lower()
        assert "architect:" in error_msg  # Shows migration example

    def test_profile_frozen(self) -> None:
        """Profile is immutable."""
        profile = Profile(
            name="test",
            architect=ArchitectConfig(driver="cli:claude", model="opus"),
            developer=DeveloperConfig(driver="cli:claude", model="opus"),
            reviewer=ReviewerConfig(driver="cli:claude", model="opus"),
        )
        with pytest.raises(ValidationError):
            profile.name = "changed"  # type: ignore[misc]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_types.py::TestProfile -v`
Expected: FAIL (Profile still uses flat fields)

**Step 3: Write implementation**

Replace the `Profile` class in `amelia/core/types.py`:

```python
class Profile(BaseModel):
    """Configuration profile for Amelia execution.

    This model is frozen (immutable) to support the stateless reducer pattern.
    Use model_copy(update={...}) to create modified copies.

    Attributes:
        name: Profile name (e.g., 'work', 'personal').
        architect: Architect agent configuration.
        developer: Developer agent configuration.
        reviewer: Reviewer agent configuration.
        tracker: Issue tracker type (jira, github, none, noop).
        working_dir: Working directory for agentic execution.
        plan_output_dir: Directory for saving implementation plans.
        plan_path_pattern: Path pattern for plan files with {date} and {issue_key} placeholders.
        retry: Retry configuration for transient failures.
        max_task_review_iterations: Per-task review iteration limit (for task-based execution).
        auto_approve_reviews: Skip human approval steps in review workflow.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    architect: ArchitectConfig
    developer: DeveloperConfig
    reviewer: ReviewerConfig
    tracker: TrackerType = "none"
    working_dir: str | None = None
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    retry: RetryConfig = Field(default_factory=RetryConfig)
    max_task_review_iterations: int = 5
    auto_approve_reviews: bool = False

    # Legacy fields - only exist to detect and provide helpful error
    driver: DriverType | None = Field(default=None, exclude=True)
    model: str | None = Field(default=None, exclude=True)
    validator_model: str | None = Field(default=None, exclude=True)
    max_review_iterations: int | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def reject_legacy_config(self) -> "Profile":
        """Reject legacy flat config with helpful migration message."""
        if self.driver or self.model:
            driver = self.driver or "cli:claude"
            model = self.model or "opus"
            raise ValueError(
                f"Profile '{self.name}' uses deprecated flat config. "
                f"Please update to per-agent configuration:\n\n"
                f"  {self.name}:\n"
                f"    architect:\n"
                f"      driver: {driver}\n"
                f"      model: {model}\n"
                f"    developer:\n"
                f"      driver: {driver}\n"
                f"      model: {model}\n"
                f"    reviewer:\n"
                f"      driver: {driver}\n"
                f"      model: {model}\n"
                f"    tracker: ...\n\n"
                f"See docs/configuration.md for details."
            )
        return self
```

Note: Import `model_validator` from pydantic at the top of the file.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_types.py::TestProfile -v`
Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "feat(types): update Profile to use nested agent configs"
```

---

## Task 3: Update Test Fixtures

**Files:**
- Modify: `tests/conftest.py:293-319`

**Step 1: Write failing test to verify fixtures work**

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: Tests should still pass, but other tests using `mock_profile_factory` will break

**Step 2: Update mock_profile_factory**

Replace `mock_profile_factory` in `tests/conftest.py`:

```python
@pytest.fixture
def mock_profile_factory(tmp_path_factory: TempPathFactory) -> Callable[..., Profile]:
    """Factory fixture for creating test Profile instances with presets.

    Uses tmp_path_factory to create a unique temp directory for working_dir,
    preventing tests from writing artifacts to the main codebase.
    """
    from amelia.core.types import ArchitectConfig, DeveloperConfig, ReviewerConfig

    # Create a shared temp directory for all profiles in this test session
    base_tmp = tmp_path_factory.mktemp("workdir")

    def _create(
        preset: str | None = None,
        name: str = "test",
        architect: ArchitectConfig | None = None,
        developer: DeveloperConfig | None = None,
        reviewer: ReviewerConfig | None = None,
        tracker: TrackerType = "noop",
        # Legacy params for convenience - will be converted to agent configs
        driver: DriverType = "cli:claude",
        model: str = "sonnet",
        **kwargs: Any
    ) -> Profile:
        # Use temp directory for working_dir unless explicitly overridden
        if "working_dir" not in kwargs:
            kwargs["working_dir"] = str(base_tmp)

        # Build agent configs from legacy params if not provided
        if architect is None:
            architect = ArchitectConfig(driver=driver, model=model)
        if developer is None:
            developer = DeveloperConfig(driver=driver, model=model)
        if reviewer is None:
            reviewer = ReviewerConfig(driver=driver, model=model)

        if preset == "cli_single":
            return Profile(
                name="test_cli",
                architect=ArchitectConfig(driver="cli:claude", model="sonnet"),
                developer=DeveloperConfig(driver="cli:claude", model="sonnet"),
                reviewer=ReviewerConfig(driver="cli:claude", model="sonnet"),
                tracker="noop",
                **kwargs,
            )
        elif preset == "api_single":
            api_model = "anthropic/claude-sonnet-4-20250514"
            return Profile(
                name="test_api",
                architect=ArchitectConfig(driver="api:openrouter", model=api_model),
                developer=DeveloperConfig(driver="api:openrouter", model=api_model),
                reviewer=ReviewerConfig(driver="api:openrouter", model=api_model),
                tracker="noop",
                **kwargs,
            )

        return Profile(
            name=name,
            architect=architect,
            developer=developer,
            reviewer=reviewer,
            tracker=tracker,
            **kwargs,
        )

    return _create
```

Also update the imports at the top of `tests/conftest.py` to include the new config types:

```python
from amelia.core.types import (
    ArchitectConfig,
    DeveloperConfig,
    Design,
    DriverType,
    Issue,
    Profile,
    ReviewerConfig,
    Settings,
    TrackerType,
)
```

**Step 3: Run tests to verify fixtures work**

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test(fixtures): update mock_profile_factory for nested agent configs"
```

---

## Task 4: Update Orchestrator - Architect Node

**Files:**
- Modify: `amelia/core/orchestrator.py:519-657`
- Test: `tests/unit/core/test_orchestrator_architect.py` (verify existing tests pass)

**Step 1: Identify changes needed**

In `call_architect_node` (line 553):
- Change: `DriverFactory.get_driver(profile.driver, model=profile.model)`
- To: `DriverFactory.get_driver(profile.architect.driver, model=profile.architect.model)`

In `plan_validator_node` (line 466, 484):
- Change: `model = profile.validator_model or profile.model`
- To: `model = profile.architect.validator_model or profile.architect.model`
- Change: `driver_type=profile.driver`
- To: `driver_type=profile.architect.driver`

**Step 2: Run existing tests to establish baseline**

Run: `uv run pytest tests/unit/agents/test_architect_plan_path.py -v`
Expected: May fail if they use old profile format (that's expected)

**Step 3: Update orchestrator code**

In `amelia/core/orchestrator.py`, update `call_architect_node`:

```python
async def call_architect_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    # ... docstring unchanged ...

    # ... (lines 539-551 unchanged) ...

    driver = DriverFactory.get_driver(
        profile.architect.driver, model=profile.architect.model
    )
    architect = Architect(driver, event_bus=event_bus, prompts=prompts)

    # ... rest unchanged ...
```

Update `plan_validator_node`:

```python
async def plan_validator_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    # ... (lines 418-465 unchanged) ...

    # Extract structured fields using lightweight extraction (no tools needed)
    model = profile.architect.validator_model or profile.architect.model
    # ... (line 467-477 unchanged) ...

    try:
        output = await _extract_structured(
            prompt=prompt,
            schema=MarkdownPlanOutput,
            model=model,
            driver_type=profile.architect.driver,
        )
    # ... rest unchanged ...
```

**Step 4: Run tests to verify**

Run: `uv run pytest tests/unit/agents/test_architect_plan_path.py -v`
Expected: PASS (after fixture updates)

**Step 5: Commit**

```bash
git add amelia/core/orchestrator.py
git commit -m "refactor(orchestrator): use profile.architect config in architect node"
```

---

## Task 5: Update Orchestrator - Developer Node

**Files:**
- Modify: `amelia/core/orchestrator.py:707-792`

**Step 1: Identify changes needed**

In `call_developer_node` (line 763):
- Change: `DriverFactory.get_driver(profile.driver, model=profile.model)`
- To: `DriverFactory.get_driver(profile.developer.driver, model=profile.developer.model)`

**Step 2: Update orchestrator code**

```python
async def call_developer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    # ... (lines 707-761 unchanged) ...

    driver = DriverFactory.get_driver(
        profile.developer.driver, model=profile.developer.model
    )
    developer = Developer(driver)

    # ... rest unchanged ...
```

**Step 3: Run tests to verify**

Run: `uv run pytest tests/unit/agents/test_developer.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add amelia/core/orchestrator.py
git commit -m "refactor(orchestrator): use profile.developer config in developer node"
```

---

## Task 6: Update Orchestrator - Reviewer Node

**Files:**
- Modify: `amelia/core/orchestrator.py:795-898`

**Step 1: Identify changes needed**

In `call_reviewer_node` (line 823):
- Change: `DriverFactory.get_driver(profile.driver, model=profile.model)`
- To: `DriverFactory.get_driver(profile.reviewer.driver, model=profile.reviewer.model)`

**Step 2: Update orchestrator code**

```python
async def call_reviewer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    # ... (lines 795-822 unchanged) ...

    driver = DriverFactory.get_driver(
        profile.reviewer.driver, model=profile.reviewer.model
    )
    # ... rest unchanged ...
```

**Step 3: Run tests to verify**

Run: `uv run pytest tests/unit/agents/test_reviewer.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add amelia/core/orchestrator.py
git commit -m "refactor(orchestrator): use profile.reviewer config in reviewer node"
```

---

## Task 7: Update Orchestrator - Evaluator Node

**Files:**
- Modify: `amelia/core/orchestrator.py:901-950`

**Step 1: Identify changes needed**

In `call_evaluation_node` (line 923):
- Change: `DriverFactory.get_driver(profile.driver, model=profile.model)`
- To: `DriverFactory.get_driver(profile.reviewer.driver, model=profile.reviewer.model)`

Note: Evaluator uses reviewer config since it's part of the review workflow.

**Step 2: Update orchestrator code**

```python
async def call_evaluation_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    # ... (lines 901-922 unchanged) ...

    driver = DriverFactory.get_driver(
        profile.reviewer.driver, model=profile.reviewer.model
    )
    evaluator = Evaluator(driver=driver, event_bus=event_bus, prompts=prompts)

    # ... rest unchanged ...
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/ -v -k "evaluator"`
Expected: PASS

**Step 4: Commit**

```bash
git add amelia/core/orchestrator.py
git commit -m "refactor(orchestrator): use profile.reviewer config in evaluator node"
```

---

## Task 8: Update Orchestrator - Route Functions

**Files:**
- Modify: `amelia/core/orchestrator.py:993-1027` and `1168-1232`

**Step 1: Identify changes needed**

In `route_after_review` (line 1017):
- Change: `max_iterations = profile.max_review_iterations`
- To: `max_iterations = profile.reviewer.max_iterations`

In `route_after_task_review` (line 1211):
- This uses `profile.max_task_review_iterations` which stays at profile level (not agent-specific)
- No change needed here.

**Step 2: Update orchestrator code**

```python
def route_after_review(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> Literal["developer", "__end__"]:
    # ... (lines 993-1015 unchanged) ...

    _, _, profile = _extract_config_params(config)
    max_iterations = profile.reviewer.max_iterations

    # ... rest unchanged ...
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/core/ -v -k "route"`
Expected: PASS

**Step 4: Commit**

```bash
git add amelia/core/orchestrator.py
git commit -m "refactor(orchestrator): use profile.reviewer.max_iterations in routing"
```

---

## Task 9: Update Settings File

**Files:**
- Modify: `settings.amelia.yaml`

**Step 1: Update to new format**

Replace `settings.amelia.yaml`:

```yaml
active_profile: test
profiles:
  test:
    name: test
    architect:
      driver: api:openrouter
      model: x-ai/grok-code-fast-1
    developer:
      driver: api:openrouter
      model: x-ai/grok-code-fast-1
    reviewer:
      driver: api:openrouter
      model: x-ai/grok-code-fast-1
    tracker: github
```

**Step 2: Verify config loads**

Run: `uv run python -c "from amelia.config import load_settings; print(load_settings())"`
Expected: Settings object prints without error

**Step 3: Commit**

```bash
git add settings.amelia.yaml
git commit -m "config: update settings.amelia.yaml to per-agent format"
```

---

## Task 10: Fix Remaining Test Failures

**Files:**
- Various test files that may still use old Profile format

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: Some tests may fail if they construct Profile directly

**Step 2: Fix any remaining failures**

Look for patterns like:
- `Profile(name=..., driver=..., model=...)` - needs agent configs
- `profile.driver` - needs `profile.<agent>.driver`
- `profile.model` - needs `profile.<agent>.model`
- `profile.validator_model` - needs `profile.architect.validator_model`
- `profile.max_review_iterations` - needs `profile.reviewer.max_iterations`

**Step 3: Run tests again**

Run: `uv run pytest tests/unit/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add -A
git commit -m "test: fix remaining tests for per-agent config"
```

---

## Task 11: Run Full Verification

**Files:** None (verification only)

**Step 1: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No errors

**Step 2: Run type checking**

Run: `uv run mypy amelia`
Expected: No errors

**Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All tests pass

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "fix: address linting and type errors"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add agent config models | `types.py`, `test_types.py` |
| 2 | Update Profile model | `types.py`, `test_types.py` |
| 3 | Update test fixtures | `conftest.py` |
| 4 | Update architect node | `orchestrator.py` |
| 5 | Update developer node | `orchestrator.py` |
| 6 | Update reviewer node | `orchestrator.py` |
| 7 | Update evaluator node | `orchestrator.py` |
| 8 | Update route functions | `orchestrator.py` |
| 9 | Update settings file | `settings.amelia.yaml` |
| 10 | Fix remaining tests | various |
| 11 | Full verification | none |
