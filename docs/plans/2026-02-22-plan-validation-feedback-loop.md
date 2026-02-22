# Plan Validation Feedback Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a feedback loop from plan_validator_node back to architect_node when plan quality issues are detected, and separate schema validation errors from transient network errors.

**Architecture:** Expand plan_validator_node with structural + LLM quality checks. Add conditional routing back to architect on failure. New SchemaValidationError exception prevents full workflow restarts for content issues. Follows the existing developer-reviewer feedback loop pattern.

**Tech Stack:** Python 3.12+, Pydantic, LangGraph, pytest-asyncio

---

### Task 1: Add SchemaValidationError Exception

**Files:**
- Modify: `amelia/core/exceptions.py:5-39`
- Test: `tests/unit/core/test_exceptions.py` (create if needed)

**Step 1: Write the failing test**

```python
# tests/unit/core/test_exceptions.py
from amelia.core.exceptions import AmeliaError, ModelProviderError, SchemaValidationError


def test_schema_validation_error_is_amelia_error():
    err = SchemaValidationError("bad schema", provider_name="codex")
    assert isinstance(err, AmeliaError)


def test_schema_validation_error_is_not_model_provider_error():
    err = SchemaValidationError("bad schema", provider_name="codex")
    assert not isinstance(err, ModelProviderError)


def test_schema_validation_error_attributes():
    err = SchemaValidationError(
        "Schema validation failed",
        provider_name="codex",
        original_message="raw output",
    )
    assert err.provider_name == "codex"
    assert err.original_message == "raw output"
    assert str(err) == "Schema validation failed"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_exceptions.py -v`
Expected: FAIL with ImportError (SchemaValidationError doesn't exist yet)

**Step 3: Write minimal implementation**

Add after `ModelProviderError` in `amelia/core/exceptions.py`:

```python
class SchemaValidationError(AmeliaError):
    """Raised when LLM output fails Pydantic schema validation.

    This is a content error, not a transient provider error.
    Should NOT trigger full workflow restart.
    """

    def __init__(
        self,
        message: str,
        provider_name: str | None = None,
        original_message: str | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.original_message = original_message
        super().__init__(message)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_exceptions.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/exceptions.py tests/unit/core/test_exceptions.py
git commit -m "feat: add SchemaValidationError exception type"
```

---

### Task 2: Add PlanValidationResult Model

**Files:**
- Modify: `amelia/core/types.py:224-241` (add after ReviewResult)
- Test: `tests/unit/core/test_types.py` (add to existing or create)

**Step 1: Write the failing test**

```python
# In tests/unit/core/test_types.py (or new file)
from amelia.core.types import PlanValidationResult, Severity


def test_plan_validation_result_valid():
    result = PlanValidationResult(valid=True, issues=[], severity=Severity.NONE)
    assert result.valid is True
    assert result.issues == []
    assert result.severity == Severity.NONE


def test_plan_validation_result_invalid():
    result = PlanValidationResult(
        valid=False,
        issues=["Missing ### Task headers", "Goal section not found"],
        severity=Severity.MAJOR,
    )
    assert result.valid is False
    assert len(result.issues) == 2
    assert result.severity == Severity.MAJOR


def test_plan_validation_result_is_frozen():
    result = PlanValidationResult(valid=True, issues=[], severity=Severity.NONE)
    try:
        result.valid = False
        assert False, "Should have raised"
    except ValidationError:
        pass
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_types.py::test_plan_validation_result_valid -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add after `ReviewResult` in `amelia/core/types.py`:

```python
class PlanValidationResult(BaseModel):
    """Result from plan structure and quality validation.

    Attributes:
        valid: Whether the plan passed all checks.
        issues: Human-readable descriptions of problems found.
        severity: Overall severity of issues (none if valid).
    """

    model_config = ConfigDict(frozen=True)

    valid: bool
    issues: list[str]
    severity: Severity
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_types.py -v -k plan_validation`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "feat: add PlanValidationResult model"
```

---

### Task 3: Add State Fields to ImplementationState

**Files:**
- Modify: `amelia/pipelines/implementation/state.py:90-91`

**Step 1: Write the failing test**

```python
# tests/unit/pipelines/implementation/test_state.py (add to existing)
from amelia.pipelines.implementation.state import ImplementationState
from amelia.core.types import PlanValidationResult, Severity


def test_implementation_state_has_plan_validation_fields():
    state = ImplementationState()
    assert state.plan_validation_result is None
    assert state.plan_revision_count == 0


def test_implementation_state_plan_validation_result():
    result = PlanValidationResult(valid=False, issues=["no tasks"], severity=Severity.MAJOR)
    state = ImplementationState(plan_validation_result=result, plan_revision_count=1)
    assert state.plan_validation_result.valid is False
    assert state.plan_revision_count == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/implementation/test_state.py -v -k plan_validation`
Expected: FAIL (fields don't exist)

**Step 3: Write minimal implementation**

Add to `ImplementationState` in `state.py`, after the external_plan fields:

```python
    # Plan validation feedback loop
    plan_validation_result: PlanValidationResult | None = None
    plan_revision_count: int = 0
```

Add import: `from amelia.core.types import PlanValidationResult` (add to existing imports from types).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/implementation/test_state.py -v -k plan_validation`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/state.py tests/unit/pipelines/implementation/test_state.py
git commit -m "feat: add plan validation fields to ImplementationState"
```

---

### Task 4: Switch Drivers to Use SchemaValidationError

**Files:**
- Modify: `amelia/drivers/cli/codex.py:248-258` and `amelia/drivers/cli/codex.py:349-354`
- Modify: `amelia/drivers/cli/claude.py:399`
- Modify: `amelia/drivers/api/deepagents.py` (schema validation path)
- Modify: `amelia/core/extraction.py:14-38`
- Test: existing driver test files

**Step 1: Write the failing tests**

Add tests to verify each driver raises `SchemaValidationError` (not `ModelProviderError`) for schema validation failures.

For codex driver (`tests/unit/drivers/cli/test_codex.py`):
```python
from amelia.core.exceptions import SchemaValidationError

async def test_generate_schema_validation_raises_schema_error(codex_driver, ...):
    """Schema validation failure should raise SchemaValidationError, not ModelProviderError."""
    # Mock subprocess to return invalid JSON for schema
    ...
    with pytest.raises(SchemaValidationError):
        await codex_driver.generate(prompt="test", schema=SomeSchema)
```

For claude driver (`tests/unit/drivers/cli/test_claude.py`):
```python
async def test_generate_schema_validation_raises_schema_error(...):
    """Schema validation failure should raise SchemaValidationError."""
    with pytest.raises(SchemaValidationError):
        ...
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/drivers/ -v -k schema_validation`
Expected: FAIL (drivers still raise ModelProviderError/RuntimeError)

**Step 3: Write implementation**

In `amelia/drivers/cli/codex.py`, change both `_validate_schema` (line 253) and `generate` (line 349):
```python
from amelia.core.exceptions import SchemaValidationError

# Replace: raise ModelProviderError(f"Schema validation failed: {e}", ...)
# With:    raise SchemaValidationError(f"Schema validation failed: {e}", ...)
```

In `amelia/drivers/cli/claude.py` (line 399):
```python
from amelia.core.exceptions import SchemaValidationError

# Replace: raise RuntimeError(f"Claude SDK output did not match schema: {e}")
# With:    raise SchemaValidationError(f"Claude SDK output did not match schema: {e}", provider_name="claude")
```

In `amelia/drivers/api/deepagents.py`, if schema validation fails through the ToolStrategy path, wrap as `SchemaValidationError`. Check the exact path — may need to catch `ValidationError` from Pydantic specifically.

In `amelia/core/extraction.py`, update the `extract_structured` function to catch `SchemaValidationError` (it currently lets `ModelProviderError` propagate — now it needs to handle `SchemaValidationError` which won't be in TRANSIENT_EXCEPTIONS).

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/drivers/ -v -k schema_validation`
Expected: PASS

**Step 5: Run full driver test suites**

Run: `uv run pytest tests/unit/drivers/ -v`
Expected: All pass (existing tests that expected ModelProviderError need updating)

**Step 6: Commit**

```bash
git add amelia/drivers/cli/codex.py amelia/drivers/cli/claude.py amelia/drivers/api/deepagents.py amelia/core/extraction.py tests/unit/drivers/
git commit -m "refactor: use SchemaValidationError for schema failures in all drivers"
```

---

### Task 5: Add Plan Validation Logic to plan_validator_node

**Files:**
- Modify: `amelia/pipelines/implementation/nodes.py:35-122`
- Modify: `amelia/pipelines/implementation/external_plan.py` (reuse `build_plan_extraction_prompt`)
- Test: `tests/unit/core/test_plan_validator_node.py`

**Step 1: Write the failing tests**

```python
# tests/unit/core/test_plan_validator_node.py (add to existing)
from amelia.core.types import PlanValidationResult, Severity


async def test_plan_validator_returns_valid_result_for_good_plan(
    tmp_path, mock_config, ...
):
    """A well-structured plan should pass validation."""
    plan = """# Feature Implementation Plan
**Goal:** Add user auth

### Task 1: Add login endpoint
- Create: `src/auth.py`
- Deliverable: Working /login route

### Task 2: Add tests
- Create: `tests/test_auth.py`
- Deliverable: Passing test suite
"""
    plan_file = tmp_path / "docs" / "plans" / "test-plan.md"
    plan_file.parent.mkdir(parents=True)
    plan_file.write_text(plan)
    # ... setup state and config ...
    result = await plan_validator_node(state, config)
    assert result["plan_validation_result"].valid is True
    assert result["plan_validation_result"].issues == []


async def test_plan_validator_returns_invalid_for_no_tasks(
    tmp_path, mock_config, ...
):
    """A plan with no ### Task headers should fail structural validation."""
    plan = """# Some Plan
**Goal:** Do something
Just some text with no task structure.
"""
    # ... setup ...
    result = await plan_validator_node(state, config)
    assert result["plan_validation_result"].valid is False
    assert any("task" in i.lower() for i in result["plan_validation_result"].issues)


async def test_plan_validator_returns_invalid_for_no_goal(
    tmp_path, mock_config, ...
):
    """A plan with no goal section should fail structural validation."""
    plan = """# Some Plan
### Task 1: Do something
Some steps.
"""
    # ... setup ...
    result = await plan_validator_node(state, config)
    assert result["plan_validation_result"].valid is False
    assert any("goal" in i.lower() for i in result["plan_validation_result"].issues)


async def test_plan_validator_increments_revision_count(
    tmp_path, mock_config, ...
):
    """Revision count should increment when validation fails."""
    # state.plan_revision_count = 1
    # ... plan with issues ...
    result = await plan_validator_node(state, config)
    assert result["plan_revision_count"] == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_plan_validator_node.py -v -k "valid_result or invalid_for or revision_count"`
Expected: FAIL

**Step 3: Write implementation**

Add a `_validate_plan_structure` function in `nodes.py`:

```python
def _validate_plan_structure(plan_content: str, goal: str | None) -> PlanValidationResult:
    """Run structural checks on a plan.

    Checks:
    - At least one ### Task N: header
    - Goal present (from extraction or **Goal:** marker)
    - Minimum content length
    """
    issues: list[str] = []

    # Check for task headers
    task_pattern = re.compile(r"^### Task \d+", re.MULTILINE)
    if not task_pattern.search(plan_content):
        issues.append("No '### Task N:' headers found. Plan must have structured tasks.")

    # Check for goal
    if not goal or goal == "Implementation plan":
        if "**Goal:**" not in plan_content and "**goal:**" not in plan_content.lower():
            issues.append("No goal section found. Plan must include a **Goal:** section.")

    # Check minimum content
    if len(plan_content.strip()) < 100:
        issues.append("Plan content is too short to be a complete implementation plan.")

    if issues:
        severity = Severity.CRITICAL if len(issues) >= 2 else Severity.MAJOR
        return PlanValidationResult(valid=False, issues=issues, severity=severity)

    return PlanValidationResult(valid=True, issues=[], severity=Severity.NONE)
```

Update `plan_validator_node` to call `_validate_plan_structure` after extraction and include result in return dict. Also increment `plan_revision_count` when invalid:

```python
    # After extraction...
    validation_result = _validate_plan_structure(plan_content, goal)

    revision_count = state.plan_revision_count
    if not validation_result.valid:
        revision_count += 1
        logger.warning(
            "Plan validation failed",
            issues=validation_result.issues,
            severity=validation_result.severity,
            revision_count=revision_count,
            workflow_id=workflow_id,
        )

    return {
        "goal": goal,
        "plan_markdown": plan_markdown,
        "plan_path": plan_path,
        "key_files": key_files,
        "total_tasks": total_tasks,
        "plan_validation_result": validation_result,
        "plan_revision_count": revision_count,
    }
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_plan_validator_node.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/nodes.py tests/unit/core/test_plan_validator_node.py
git commit -m "feat: add structural validation to plan_validator_node"
```

---

### Task 6: Add Routing Logic for Plan Validation

**Files:**
- Modify: `amelia/pipelines/implementation/routing.py:15-27`
- Test: `tests/unit/pipelines/test_graph_routing.py`

**Step 1: Write the failing tests**

```python
# tests/unit/pipelines/test_graph_routing.py (add to existing)
from amelia.pipelines.implementation.routing import route_after_plan_validation
from amelia.core.types import PlanValidationResult, Severity


def test_route_after_plan_validation_valid():
    state = ImplementationState(
        plan_validation_result=PlanValidationResult(valid=True, issues=[], severity=Severity.NONE),
    )
    assert route_after_plan_validation(state) == "approved"


def test_route_after_plan_validation_invalid_with_retries():
    state = ImplementationState(
        plan_validation_result=PlanValidationResult(
            valid=False, issues=["no tasks"], severity=Severity.MAJOR
        ),
        plan_revision_count=1,
    )
    # Default max_revisions=2, so 1 < 2 means revise
    assert route_after_plan_validation(state) == "revise"


def test_route_after_plan_validation_max_retries_exhausted():
    state = ImplementationState(
        plan_validation_result=PlanValidationResult(
            valid=False, issues=["no tasks"], severity=Severity.MAJOR
        ),
        plan_revision_count=2,
    )
    # 2 >= 2 means fail
    assert route_after_plan_validation(state) == "fail"


def test_route_after_plan_validation_no_result_defaults_approved():
    """If validator didn't set result (backward compat), treat as approved."""
    state = ImplementationState()
    assert route_after_plan_validation(state) == "approved"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/pipelines/test_graph_routing.py -v -k plan_validation`
Expected: FAIL (function doesn't exist)

**Step 3: Write implementation**

Add to `amelia/pipelines/implementation/routing.py`:

```python
def route_after_plan_validation(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> Literal["approved", "revise", "fail"]:
    """Route based on plan validation result.

    Args:
        state: Current state with plan_validation_result and plan_revision_count.
        config: Optional config with profile for max_revisions setting.

    Returns:
        'approved' if valid, 'revise' if retries remain, 'fail' if exhausted.
    """
    result = state.plan_validation_result
    if result is None or result.valid:
        return "approved"

    max_revisions = 2
    if config:
        profile = config.get("configurable", {}).get("profile")
        if profile:
            agent_config = profile.get_agent_config("plan_validator")
            max_revisions = agent_config.options.get("max_revisions", 2)

    if state.plan_revision_count >= max_revisions:
        logger.warning(
            "Plan validation failed after max revisions",
            revision_count=state.plan_revision_count,
            max_revisions=max_revisions,
            issues=result.issues,
        )
        return "fail"

    return "revise"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/pipelines/test_graph_routing.py -v -k plan_validation`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/routing.py tests/unit/pipelines/test_graph_routing.py
git commit -m "feat: add route_after_plan_validation routing function"
```

---

### Task 7: Update Graph to Wire Conditional Edge

**Files:**
- Modify: `amelia/pipelines/implementation/graph.py:98-99`
- Test: `tests/unit/pipelines/test_graph_routing.py` (graph compilation test)

**Step 1: Write the failing test**

```python
# tests/unit/pipelines/test_graph_routing.py (add to existing)
def test_graph_has_plan_validation_routing():
    """Graph should route from plan_validator to architect on revision."""
    graph = create_implementation_graph()
    # Verify the graph compiles and has the conditional edge
    # The graph's nodes should include plan_validator_node with conditional routing
    assert "plan_validator_node" in graph.nodes
    assert "architect_node" in graph.nodes
```

**Step 2: Run test to verify current state**

Run: `uv run pytest tests/unit/pipelines/test_graph_routing.py::test_graph_has_plan_validation_routing -v`
Expected: PASS (graph already has these nodes — this is a smoke test)

**Step 3: Write implementation**

In `amelia/pipelines/implementation/graph.py`, replace line 99:

```python
# Before:
workflow.add_edge("plan_validator_node", "human_approval_node")

# After:
workflow.add_conditional_edges(
    "plan_validator_node",
    route_after_plan_validation,
    {
        "approved": "human_approval_node",
        "revise": "architect_node",
        "fail": END,
    }
)
```

Add import: `from amelia.pipelines.implementation.routing import route_after_plan_validation`

**Step 4: Run tests**

Run: `uv run pytest tests/unit/pipelines/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/graph.py
git commit -m "feat: wire plan_validator conditional edge back to architect"
```

---

### Task 8: Add Revision Prompt to Architect

**Files:**
- Modify: `amelia/agents/architect.py` (the `_build_agentic_prompt` method)
- Modify: `amelia/pipelines/implementation/nodes.py` (call_architect_node — pass validation result)
- Test: `tests/unit/agents/test_architect.py`

**Step 1: Write the failing test**

```python
# tests/unit/agents/test_architect.py (add to existing)
from amelia.core.types import PlanValidationResult, Severity


def test_architect_prompt_includes_validation_feedback():
    """When plan_validation_result has issues, prompt should include them."""
    state = ImplementationState(
        issue=Issue(id="test", title="Test", description="Test issue"),
        plan_validation_result=PlanValidationResult(
            valid=False,
            issues=["No ### Task headers found", "Goal section missing"],
            severity=Severity.MAJOR,
        ),
    )
    architect = Architect(agent_config, prompts={})
    prompt = architect._build_agentic_prompt(state, profile)
    assert "No ### Task headers found" in prompt
    assert "Goal section missing" in prompt
    assert "revise" in prompt.lower() or "fix" in prompt.lower()


def test_architect_prompt_no_feedback_when_valid():
    """When no validation issues, prompt should not include revision section."""
    state = ImplementationState(
        issue=Issue(id="test", title="Test", description="Test issue"),
    )
    architect = Architect(agent_config, prompts={})
    prompt = architect._build_agentic_prompt(state, profile)
    assert "previous plan" not in prompt.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/test_architect.py -v -k validation_feedback`
Expected: FAIL

**Step 3: Write implementation**

In `Architect._build_agentic_prompt()`, add after the existing prompt construction:

```python
    # Plan revision feedback (if validation failed)
    if state.plan_validation_result and not state.plan_validation_result.valid:
        issues = "\n".join(f"- {i}" for i in state.plan_validation_result.issues)
        parts.append(
            f"\n\nYour previous plan had these issues that must be fixed:\n{issues}\n"
            "Please revise the plan file to address all issues above."
        )
```

This mirrors the developer's pattern at `developer.py:222-224`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/test_architect.py -v -k validation_feedback`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect.py
git commit -m "feat: architect includes validation feedback in revision prompts"
```

---

### Task 9: Update plan_validator_node to Catch SchemaValidationError

**Files:**
- Modify: `amelia/pipelines/implementation/nodes.py:85-103` (the try/except block)
- Test: `tests/unit/core/test_plan_validator_node.py`

**Step 1: Write the failing test**

```python
async def test_plan_validator_catches_schema_validation_error(tmp_path, mock_config):
    """SchemaValidationError from extract_structured should use fallback, not crash."""
    # Setup plan file with valid content
    # Mock extract_structured to raise SchemaValidationError
    # Verify fallback extraction runs and result is returned
    ...
```

**Step 2: Run test to verify it fails**

Expected: FAIL (node doesn't catch SchemaValidationError yet)

**Step 3: Write implementation**

In `plan_validator_node`, update the except clause:

```python
# Before:
except RuntimeError as e:

# After:
except (RuntimeError, SchemaValidationError) as e:
```

Add import: `from amelia.core.exceptions import SchemaValidationError`

**Step 4: Run tests**

Run: `uv run pytest tests/unit/core/test_plan_validator_node.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/nodes.py tests/unit/core/test_plan_validator_node.py
git commit -m "fix: plan_validator catches SchemaValidationError for fallback"
```

---

### Task 10: Integration Smoke Test

**Files:**
- Test: `tests/unit/pipelines/implementation/test_pipeline.py` (add to existing)

**Step 1: Write an integration-style test**

Test the full flow: architect produces bad plan → validator detects issues → routes back to architect → architect revises → validator approves → continues to human_approval.

```python
async def test_plan_validation_feedback_loop_routes_to_architect(mock_graph_config):
    """When plan validation fails, graph should route back to architect."""
    # Build graph
    # Set up state with a bad plan (no tasks)
    # Step through nodes manually:
    #   1. plan_validator_node returns invalid result
    #   2. route_after_plan_validation returns "revise"
    #   3. call_architect_node sees validation feedback
    ...
```

**Step 2: Run test**

Run: `uv run pytest tests/unit/pipelines/implementation/test_pipeline.py -v -k feedback_loop`

**Step 3: Commit**

```bash
git add tests/unit/pipelines/implementation/test_pipeline.py
git commit -m "test: add plan validation feedback loop integration test"
```

---

### Task 11: Run Full Test Suite and Lint

**Step 1: Run linter**

Run: `uv run ruff check --fix amelia tests`

**Step 2: Run type checker**

Run: `uv run mypy amelia`

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v`

**Step 4: Fix any issues found**

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: fix lint and type issues from plan validation feature"
```
