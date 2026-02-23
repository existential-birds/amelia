# Plan Validation Feedback Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a feedback loop from plan_validator_node back to architect_node when plan quality issues are detected, and separate schema validation errors from transient network errors.

**Architecture:** Expand plan_validator_node with deterministic structural checks. Add conditional routing back to architect on failure, escalating to human_approval on max revisions. New SchemaValidationError exception prevents full workflow restarts for content issues. Follows the existing developer-reviewer feedback loop pattern (routing, state fields, prompt injection).

**Tech Stack:** Python 3.12+, Pydantic, LangGraph, pytest-asyncio

---

### Task 1: Add SchemaValidationError Exception

**Files:**
- Modify: `amelia/core/exceptions.py` (add after `ModelProviderError` class, ~line 39)
- Create: `tests/unit/core/test_exceptions.py`

**Step 1: Write the failing test**

```python
# tests/unit/core/test_exceptions.py
from amelia.core.exceptions import AmeliaError, ModelProviderError, SchemaValidationError


class TestSchemaValidationError:
    """Tests for SchemaValidationError exception type."""

    def test_is_amelia_error(self) -> None:
        err = SchemaValidationError("bad schema", provider_name="codex")
        assert isinstance(err, AmeliaError)

    def test_is_not_model_provider_error(self) -> None:
        err = SchemaValidationError("bad schema", provider_name="codex")
        assert not isinstance(err, ModelProviderError)

    def test_attributes(self) -> None:
        err = SchemaValidationError(
            "Schema validation failed",
            provider_name="codex",
            original_message="raw output",
        )
        assert err.provider_name == "codex"
        assert err.original_message == "raw output"
        assert str(err) == "Schema validation failed"

    def test_not_in_transient_exceptions(self) -> None:
        from amelia.server.orchestrator.service import TRANSIENT_EXCEPTIONS

        assert SchemaValidationError not in TRANSIENT_EXCEPTIONS
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
    Should NOT trigger full workflow restart — the graph-level
    feedback loop handles it instead.
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

Note: The signature mirrors `ModelProviderError.__init__` for consistency across drivers.

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
- Modify: `amelia/core/types.py` (add after `ReviewResult` at ~line 240)
- Modify: `tests/unit/core/test_types.py` (add test class)

**Context:** `ReviewResult` at `amelia/core/types.py:224-240` is the pattern to follow. Both use `ConfigDict(frozen=True)`, `Severity`, and a list of issue strings.

**Step 1: Write the failing test**

```python
# Add to tests/unit/core/test_types.py
from amelia.core.types import PlanValidationResult, Severity


class TestPlanValidationResult:
    """Tests for PlanValidationResult model."""

    def test_valid_result(self) -> None:
        result = PlanValidationResult(valid=True, issues=[], severity=Severity.NONE)
        assert result.valid is True
        assert result.issues == []
        assert result.severity == Severity.NONE

    def test_invalid_result(self) -> None:
        result = PlanValidationResult(
            valid=False,
            issues=["Missing ### Task headers", "Goal section not found"],
            severity=Severity.MAJOR,
        )
        assert result.valid is False
        assert len(result.issues) == 2
        assert result.severity == Severity.MAJOR

    def test_is_frozen(self) -> None:
        result = PlanValidationResult(valid=True, issues=[], severity=Severity.NONE)
        with pytest.raises(ValidationError):
            result.valid = False  # type: ignore[misc]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_types.py::TestPlanValidationResult -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add after `ReviewResult` in `amelia/core/types.py`:

```python
class PlanValidationResult(BaseModel):
    """Result from plan structure validation.

    Mirrors ReviewResult but for plan quality checks.

    Attributes:
        valid: Whether the plan passed all structural checks.
        issues: Human-readable descriptions of problems found.
        severity: Overall severity of issues (none if valid).
    """

    model_config = ConfigDict(frozen=True)

    valid: bool
    issues: list[str]
    severity: Severity
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_types.py::TestPlanValidationResult -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "feat: add PlanValidationResult model"
```

---

### Task 3: Add State Fields to ImplementationState

**Files:**
- Modify: `amelia/pipelines/implementation/state.py` (add fields after existing plan fields)
- Modify: `tests/unit/pipelines/implementation/test_state.py` (add test method)

**Step 1: Write the failing test**

```python
# Add to tests/unit/pipelines/implementation/test_state.py, in TestImplementationState class
from amelia.core.types import PlanValidationResult, Severity

    def test_plan_validation_fields_defaults(self) -> None:
        """Should have plan validation fields with correct defaults."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="default",
            created_at=datetime.now(UTC),
            status="pending",
        )
        assert state.plan_validation_result is None
        assert state.plan_revision_count == 0

    def test_plan_validation_fields_set(self) -> None:
        """Should accept plan validation result and revision count."""
        result = PlanValidationResult(valid=False, issues=["no tasks"], severity=Severity.MAJOR)
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="default",
            created_at=datetime.now(UTC),
            status="running",
            plan_validation_result=result,
            plan_revision_count=1,
        )
        assert state.plan_validation_result is not None
        assert not state.plan_validation_result.valid
        assert state.plan_revision_count == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/implementation/test_state.py -v -k plan_validation`
Expected: FAIL (fields don't exist)

**Step 3: Write minimal implementation**

Add to `ImplementationState` in `amelia/pipelines/implementation/state.py`, after the existing plan/task fields:

```python
    # Plan validation feedback loop (mirrors last_review + task_review_iteration)
    plan_validation_result: PlanValidationResult | None = None
    plan_revision_count: int = 0
```

Add import: `from amelia.core.types import PlanValidationResult` (add to existing imports from `amelia.core.types`).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/implementation/test_state.py -v -k plan_validation`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/state.py tests/unit/pipelines/implementation/test_state.py
git commit -m "feat: add plan validation fields to ImplementationState"
```

---

### Task 4: Add validate_plan_structure Function

**Files:**
- Modify: `amelia/pipelines/implementation/utils.py` (add function after `extract_task_count`)
- Modify: `tests/unit/pipelines/implementation/test_utils.py` (add test class)

**Context:** `extract_task_count` in `utils.py` already uses the `### Task \d+` regex pattern. The validation function reuses this pattern.

**Step 1: Write the failing tests**

```python
# Add to tests/unit/pipelines/implementation/test_utils.py
from amelia.core.types import Severity
from amelia.pipelines.implementation.utils import validate_plan_structure


class TestValidatePlanStructure:
    """Tests for validate_plan_structure function."""

    def test_valid_plan(self) -> None:
        """A well-structured plan should pass validation."""
        result = validate_plan_structure(
            goal="Add user authentication",
            plan_markdown="""# Implementation Plan

**Goal:** Add user authentication

### Task 1: Add login endpoint
Create the auth handler with JWT validation.

### Task 2: Add tests
Write comprehensive test suite for auth.
""",
        )
        assert result.valid is True
        assert result.issues == []
        assert result.severity == Severity.NONE

    def test_missing_task_headers(self) -> None:
        """A plan with no ### Task N: headers should fail."""
        result = validate_plan_structure(
            goal="Add feature",
            plan_markdown="""# Implementation Plan

**Goal:** Add feature

## Step 1
Do something.

## Step 2
Do something else.
""",
        )
        assert result.valid is False
        assert any("Task" in i for i in result.issues)

    def test_missing_goal(self) -> None:
        """A plan with no goal should fail."""
        result = validate_plan_structure(
            goal=None,
            plan_markdown="""# Plan

### Task 1: Do something
Steps here.
""",
        )
        assert result.valid is False
        assert any("goal" in i.lower() for i in result.issues)

    def test_fallback_goal_detected(self) -> None:
        """The default fallback goal 'Implementation plan' should count as missing."""
        result = validate_plan_structure(
            goal="Implementation plan",
            plan_markdown="""### Task 1: Something
Content here that is long enough to pass length check.
""",
        )
        assert result.valid is False
        assert any("goal" in i.lower() for i in result.issues)

    def test_too_short(self) -> None:
        """A plan that is too short should fail."""
        result = validate_plan_structure(
            goal="Add feature",
            plan_markdown="### Task 1: Do it",
        )
        assert result.valid is False
        assert any("short" in i.lower() for i in result.issues)

    def test_multiple_issues_severity_critical(self) -> None:
        """Multiple issues should produce critical severity."""
        result = validate_plan_structure(
            goal=None,
            plan_markdown="short",
        )
        assert result.valid is False
        assert len(result.issues) >= 2
        assert result.severity == Severity.CRITICAL

    def test_single_issue_severity_major(self) -> None:
        """A single issue should produce major severity."""
        result = validate_plan_structure(
            goal="Add feature",
            plan_markdown="""# Implementation Plan

**Goal:** Add feature

This is a freeform plan without task headers but with enough content
to pass the minimum length check. It describes what needs to be done
in a reasonable amount of detail for the implementation.
""",
        )
        assert result.valid is False
        assert len(result.issues) == 1
        assert result.severity == Severity.MAJOR
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/pipelines/implementation/test_utils.py::TestValidatePlanStructure -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

Add to `amelia/pipelines/implementation/utils.py`:

```python
import re

from amelia.core.types import PlanValidationResult, Severity


def validate_plan_structure(
    goal: str | None,
    plan_markdown: str,
) -> PlanValidationResult:
    """Run structural checks on a plan.

    Checks:
    - At least one ### Task N: header (simple or hierarchical)
    - Goal present and not a fallback placeholder
    - Minimum content length (200 chars)

    Args:
        goal: Extracted goal string (may be None or fallback placeholder).
        plan_markdown: The full plan markdown content.

    Returns:
        PlanValidationResult with valid=True if all checks pass.
    """
    issues: list[str] = []

    # Check for task headers (reuses same pattern as extract_task_count)
    task_pattern = re.compile(r"^### Task \d+", re.MULTILINE)
    if not task_pattern.search(plan_markdown):
        issues.append(
            "No '### Task N:' headers found. Plan must have structured tasks "
            "with headers like '### Task 1: Component Name'."
        )

    # Check for goal
    if not goal or goal == "Implementation plan":
        issues.append(
            "No goal found. Plan must include a clear goal statement "
            "(e.g. '**Goal:** Add user authentication')."
        )

    # Check minimum content length
    if len(plan_markdown.strip()) < 200:
        issues.append(
            "Plan content is too short to be a complete implementation plan. "
            "Expected at least 200 characters."
        )

    if issues:
        severity = Severity.CRITICAL if len(issues) >= 2 else Severity.MAJOR
        return PlanValidationResult(valid=False, issues=issues, severity=severity)

    return PlanValidationResult(valid=True, issues=[], severity=Severity.NONE)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/pipelines/implementation/test_utils.py::TestValidatePlanStructure -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/utils.py tests/unit/pipelines/implementation/test_utils.py
git commit -m "feat: add validate_plan_structure function"
```

---

### Task 5: Integrate Validation into plan_validator_node

**Files:**
- Modify: `amelia/pipelines/implementation/nodes.py:34-121` (the `plan_validator_node` function)
- Modify: `tests/unit/core/test_plan_validator_node.py` (add validation tests)

**Context:** The node currently returns `{goal, plan_markdown, plan_path, key_files, total_tasks}`. After this task it also returns `{plan_validation_result, plan_revision_count}`. Validation runs on both the LLM extraction happy path and the regex fallback path.

**Step 1: Write the failing tests**

Add to `tests/unit/core/test_plan_validator_node.py` in a new class:

```python
from amelia.core.types import PlanValidationResult, Severity


class TestPlanValidatorNodeValidation:
    """Tests for plan validation within plan_validator_node."""

    async def test_returns_valid_result_for_good_plan(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """A well-structured plan should pass validation."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = """# Feature Implementation Plan

**Goal:** Add user auth

### Task 1: Add login endpoint
- Create: `src/auth.py`
- Deliverable: Working /login route

### Task 2: Add tests
- Create: `tests/test_auth.py`
- Deliverable: Passing test suite

This plan has enough content to pass the minimum length check.
It describes the implementation in reasonable detail.
"""
        create_plan_file(tmp_path, plan)

        mock_output = MarkdownPlanOutput(
            goal="Add user auth",
            plan_markdown=plan,
            key_files=["src/auth.py"],
        )

        config = make_config(mock_profile)

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            return_value=mock_output,
        ):
            result = await plan_validator_node(mock_state, config)

        assert result["plan_validation_result"].valid is True
        assert result["plan_validation_result"].issues == []
        assert result["plan_revision_count"] == 0

    async def test_returns_invalid_for_no_tasks(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """A plan with no ### Task headers should fail structural validation."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = """# Some Plan

**Goal:** Do something

Just some text with no task structure.
This plan does not have any task headers at all.
It is long enough to pass minimum length but
lacks the required ### Task N: formatting that
the downstream task processor expects.
"""
        create_plan_file(tmp_path, plan)

        mock_output = MarkdownPlanOutput(
            goal="Do something",
            plan_markdown=plan,
            key_files=[],
        )

        config = make_config(mock_profile)

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            return_value=mock_output,
        ):
            result = await plan_validator_node(mock_state, config)

        assert result["plan_validation_result"].valid is False
        assert any("Task" in i for i in result["plan_validation_result"].issues)

    async def test_increments_revision_count_on_invalid(
        self,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Revision count should increment when validation fails."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = "short"  # Will fail validation
        create_plan_file(tmp_path, plan)

        # State already has revision_count=1
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=Issue(id="TEST-123", title="Test", description="Test"),
            plan_revision_count=1,
        )

        mock_output = MarkdownPlanOutput(
            goal="Implementation plan",
            plan_markdown=plan,
            key_files=[],
        )

        config = make_config(mock_profile)

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            return_value=mock_output,
        ):
            result = await plan_validator_node(state, config)

        assert result["plan_revision_count"] == 2

    async def test_does_not_increment_revision_count_on_valid(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Revision count should NOT increment when validation passes."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = """# Feature Plan

**Goal:** Add feature

### Task 1: Implement feature
Detailed implementation steps with enough content to pass validation.
Create the necessary files and write comprehensive tests.

### Task 2: Add tests
Write tests covering all edge cases and error paths.
"""
        create_plan_file(tmp_path, plan)

        mock_output = MarkdownPlanOutput(
            goal="Add feature",
            plan_markdown=plan,
            key_files=[],
        )

        config = make_config(mock_profile)

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            return_value=mock_output,
        ):
            result = await plan_validator_node(mock_state, config)

        assert result["plan_revision_count"] == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_plan_validator_node.py::TestPlanValidatorNodeValidation -v`
Expected: FAIL (node doesn't return plan_validation_result yet)

**Step 3: Write implementation**

Modify `plan_validator_node` in `amelia/pipelines/implementation/nodes.py`. After the existing extraction logic (both happy path and fallback), add structural validation:

```python
from amelia.pipelines.implementation.utils import validate_plan_structure

    # ... existing extraction code (both try/except paths) ...

    # Parse task count from plan markdown
    total_tasks = extract_task_count(plan_content)

    # Run structural validation (on both happy path and fallback output)
    validation_result = validate_plan_structure(goal, plan_markdown)

    revision_count = state.plan_revision_count
    if not validation_result.valid:
        revision_count += 1
        logger.warning(
            "Plan structural validation failed",
            issues=validation_result.issues,
            severity=validation_result.severity.value,
            revision_count=revision_count,
            workflow_id=workflow_id,
        )

    # ... existing logging ...

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
Expected: PASS (both old and new tests)

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/nodes.py tests/unit/core/test_plan_validator_node.py
git commit -m "feat: add structural validation to plan_validator_node"
```

---

### Task 6: Add route_after_plan_validation Routing Function

**Files:**
- Modify: `amelia/pipelines/implementation/routing.py` (add function after `route_after_task_review`)
- Modify: `tests/unit/pipelines/test_routing.py` (add test class)

**Context:** `route_after_task_review` at `routing.py:42-113` is the pattern. The new function has the same shape: check result validity → check iteration count → route. Key difference: max revisions exhausted routes to `"escalate"` (human_approval) instead of `"__end__"`.

**Step 1: Write the failing tests**

```python
# Add to tests/unit/pipelines/test_routing.py
from amelia.core.types import PlanValidationResult
from amelia.pipelines.implementation.routing import route_after_plan_validation


class TestRouteAfterPlanValidation:
    """Tests for route_after_plan_validation routing function."""

    @pytest.fixture
    def profile(self) -> Profile:
        """Profile with plan_validator max_iterations=3."""
        return Profile(
            name="test",
            repo_root="/tmp/test",
            agents={
                "plan_validator": AgentConfig(
                    driver=DriverType.CLAUDE, model="sonnet", options={"max_iterations": 3}
                ),
            },
        )

    def test_valid_plan_routes_to_approved(self, profile: Profile) -> None:
        """Valid plan -> approved."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            plan_validation_result=PlanValidationResult(
                valid=True, issues=[], severity=Severity.NONE
            ),
        )
        assert route_after_plan_validation(state, profile) == "approved"

    def test_no_result_defaults_to_approved(self, profile: Profile) -> None:
        """Missing plan_validation_result (backward compat) -> approved."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
        )
        assert route_after_plan_validation(state, profile) == "approved"

    def test_invalid_with_retries_remaining_routes_to_revise(self, profile: Profile) -> None:
        """Invalid plan + retries remaining -> revise."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            plan_validation_result=PlanValidationResult(
                valid=False, issues=["no tasks"], severity=Severity.MAJOR
            ),
            plan_revision_count=1,
        )
        assert route_after_plan_validation(state, profile) == "revise"

    def test_max_revisions_exhausted_routes_to_escalate(self, profile: Profile) -> None:
        """Invalid plan + max revisions reached -> escalate (human decides)."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            plan_validation_result=PlanValidationResult(
                valid=False, issues=["no tasks"], severity=Severity.MAJOR
            ),
            plan_revision_count=3,  # == max_iterations
        )
        assert route_after_plan_validation(state, profile) == "escalate"

    def test_default_max_iterations(self) -> None:
        """Should use default max_iterations=3 when not configured."""
        profile = Profile(
            name="test",
            repo_root="/tmp/test",
            agents={
                "plan_validator": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
            },
        )
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            plan_validation_result=PlanValidationResult(
                valid=False, issues=["issue"], severity=Severity.MAJOR
            ),
            plan_revision_count=3,  # == default max 3
        )
        assert route_after_plan_validation(state, profile) == "escalate"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/pipelines/test_routing.py::TestRouteAfterPlanValidation -v`
Expected: FAIL (function doesn't exist)

**Step 3: Write implementation**

Add to `amelia/pipelines/implementation/routing.py` after `route_after_task_review`:

```python
def route_after_plan_validation(
    state: ImplementationState,
    profile: Profile,
) -> Literal["approved", "revise", "escalate"]:
    """Route after plan validation: approve, revise, or escalate to human.

    Follows the same pattern as route_after_task_review:
    check result → check iteration count → route.

    Args:
        state: Current state with plan_validation_result and plan_revision_count.
        profile: Profile with plan_validator agent config for max_iterations.

    Returns:
        "approved" if valid (or no result for backward compat).
        "revise" if invalid and revisions remain.
        "escalate" if max revisions exhausted (let human decide).
    """
    result = state.plan_validation_result
    if result is None or result.valid:
        return "approved"

    max_iterations = 3
    if "plan_validator" in profile.agents:
        max_iterations = profile.agents["plan_validator"].options.get("max_iterations", 3)

    if state.plan_revision_count >= max_iterations:
        logger.warning(
            "Plan validation failed after max revisions, escalating to human",
            revision_count=state.plan_revision_count,
            max_iterations=max_iterations,
            issues=result.issues,
        )
        return "escalate"

    logger.debug(
        "Plan validation failed, routing to architect for revision",
        revision_count=state.plan_revision_count,
        max_iterations=max_iterations,
        issues=result.issues,
    )
    return "revise"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/pipelines/test_routing.py -v`
Expected: PASS (both old and new tests)

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/routing.py tests/unit/pipelines/test_routing.py
git commit -m "feat: add route_after_plan_validation routing function"
```

---

### Task 7: Wire Conditional Edge in Graph

**Files:**
- Modify: `amelia/pipelines/implementation/graph.py:99` (replace direct edge)
- Modify: `tests/unit/pipelines/test_graph_routing.py` (add routing test)

**Context:** Line 99 currently reads `workflow.add_edge("plan_validator_node", "human_approval_node")`. The `_route_after_review_or_task` wrapper at lines 37-50 shows the pattern for extracting profile from config and delegating to the routing function.

**Step 1: Write the failing test**

```python
# Add to tests/unit/pipelines/test_graph_routing.py

    def test_graph_has_plan_validation_conditional_routing(self) -> None:
        """Graph should have conditional routing from plan_validator_node."""
        graph = create_implementation_graph()
        graph_dict = graph.get_graph().to_json()

        # Find plan_validator_node edges
        validator_edges = [
            edge for edge in graph_dict["edges"]
            if edge["source"] == "plan_validator_node"
        ]

        # Should have conditional edges to human_approval_node AND architect_node
        target_nodes = {edge["target"] for edge in validator_edges}
        assert "human_approval_node" in target_nodes, "plan_validator should route to human_approval"
        assert "architect_node" in target_nodes, "plan_validator should route back to architect"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_graph_routing.py::TestGraphExternalPlanRouting::test_graph_has_plan_validation_conditional_routing -v`
Expected: FAIL (currently only has direct edge to human_approval)

**Step 3: Write implementation**

In `amelia/pipelines/implementation/graph.py`:

1. Add a wrapper function (like `_route_after_review_or_task`) near line 37:

```python
def _route_after_plan_validation(
    state: ImplementationState, config: RunnableConfig
) -> Literal["approved", "revise", "escalate"]:
    """Route after plan validation: approve, revise, or escalate.

    Args:
        state: Current execution state.
        config: Runnable config with profile.

    Returns:
        Routing target.
    """
    _, _, profile = extract_config_params(config)
    return route_after_plan_validation(state, profile)
```

2. Replace line 99:

```python
# Before:
workflow.add_edge("plan_validator_node", "human_approval_node")

# After:
workflow.add_conditional_edges(
    "plan_validator_node",
    _route_after_plan_validation,
    {
        "approved": "human_approval_node",
        "revise": "architect_node",
        "escalate": "human_approval_node",
    }
)
```

3. Add import: `from amelia.pipelines.implementation.routing import route_after_plan_validation`

4. Update the docstring comment at line 59 to reflect the new flow.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/pipelines/test_graph_routing.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/graph.py tests/unit/pipelines/test_graph_routing.py
git commit -m "feat: wire plan_validator conditional edge back to architect"
```

---

### Task 8: Add Revision Feedback to Architect Prompt

**Files:**
- Modify: `amelia/agents/architect.py:249-394` (the `_build_agentic_prompt` method)
- Modify: `tests/unit/agents/test_architect_prompts.py` (add test methods)

**Context:** `Developer._build_prompt()` at `developer.py:222-224` shows the feedback injection pattern:
```python
if state.last_review and not state.last_review.approved:
    feedback = "\n".join(f"- {c}" for c in state.last_review.comments)
    parts.append(f"\n\nThe reviewer requested the following changes:\n{feedback}")
```
The architect uses the same pattern with `plan_validation_result.issues`.

**Step 1: Write the failing tests**

```python
# Add to tests/unit/agents/test_architect_prompts.py
from amelia.core.types import PlanValidationResult, Severity


class TestArchitectValidationFeedback:
    """Tests for validation feedback in architect prompts."""

    async def test_prompt_includes_validation_feedback(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """When plan_validation_result has issues, prompt should include them."""
        from amelia.agents.architect import Architect

        state, profile = mock_execution_state_factory(
            plan_validation_result=PlanValidationResult(
                valid=False,
                issues=["No ### Task headers found", "Goal section missing"],
                severity=Severity.MAJOR,
            ),
        )
        config = AgentConfig(driver="claude", model="sonnet")

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            architect = Architect(config)
            prompt = architect._build_agentic_prompt(state, profile)

        assert "No ### Task headers found" in prompt
        assert "Goal section missing" in prompt

    async def test_prompt_no_feedback_when_valid(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """When no validation issues, prompt should not include revision section."""
        from amelia.agents.architect import Architect

        state, profile = mock_execution_state_factory()
        config = AgentConfig(driver="claude", model="sonnet")

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            architect = Architect(config)
            prompt = architect._build_agentic_prompt(state, profile)

        assert "plan validator" not in prompt.lower()
        assert "structural issues" not in prompt.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/test_architect_prompts.py::TestArchitectValidationFeedback -v`
Expected: FAIL (prompt doesn't include validation feedback yet)

**Step 3: Write implementation**

Add to `Architect._build_agentic_prompt()` in `amelia/agents/architect.py`, just before the final `return "\n".join(parts)`:

```python
        # Plan revision feedback (mirrors Developer's review feedback injection)
        if state.plan_validation_result and not state.plan_validation_result.valid:
            issues = "\n".join(f"- {i}" for i in state.plan_validation_result.issues)
            parts.append(
                f"\n\n## Plan Revision Required\n\n"
                f"Your previous plan had these structural issues:\n{issues}\n\n"
                "Please revise the plan file to address all issues above."
            )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/test_architect_prompts.py -v`
Expected: PASS (both old and new tests)

**Step 5: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect_prompts.py
git commit -m "feat: architect includes validation feedback in revision prompts"
```

---

### Task 9: Switch Drivers to Use SchemaValidationError

**Files:**
- Modify: `amelia/drivers/cli/codex.py:248-258` (`_validate_schema`) and `amelia/drivers/cli/codex.py:349-354` (`generate` schema block)
- Modify: `amelia/drivers/cli/claude.py:399` (`generate` ValidationError catch)
- Modify: `amelia/drivers/api/deepagents.py:405` (schema not populated RuntimeError)
- Modify: `tests/unit/drivers/test_codex_driver.py` (add schema error test)

**Context:**
- Codex `_validate_schema()` at line 253: catches `(ValidationError, json.JSONDecodeError)` → raises `ModelProviderError`
- Codex `generate()` at line 349: same pattern
- Codex streaming at line 208: catches `ValidationError` → `continue` (DO NOT CHANGE)
- Claude `generate()` at line 399: catches `ValidationError` → raises `RuntimeError`
- DeepAgents `generate()` at line 405: raises `RuntimeError` when model doesn't call schema tool

**Step 1: Write the failing tests**

```python
# Add to tests/unit/drivers/test_codex_driver.py
from amelia.core.exceptions import SchemaValidationError


@pytest.mark.asyncio
async def test_generate_schema_validation_raises_schema_error() -> None:
    """Schema validation failure should raise SchemaValidationError, not ModelProviderError."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    # Return invalid JSON that won't match _Schema
    payload = json.dumps({"wrong_field": "value"})
    with (
        patch.object(driver, "_run_codex", new=AsyncMock(return_value=payload)),
        pytest.raises(SchemaValidationError, match="Schema validation failed"),
    ):
        await driver.generate("question", schema=_Schema)


@pytest.mark.asyncio
async def test_validate_schema_raises_schema_error() -> None:
    """_validate_schema should raise SchemaValidationError for invalid data."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    with pytest.raises(SchemaValidationError, match="Schema validation failed"):
        driver._validate_schema({"wrong": "data"}, _Schema, "source")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/drivers/test_codex_driver.py -v -k schema_validation`
Expected: FAIL (still raises ModelProviderError)

**Step 3: Write implementation**

In `amelia/drivers/cli/codex.py`:

1. Add import: `from amelia.core.exceptions import SchemaValidationError`

2. In `_validate_schema` (line 253-258), change:
```python
# Before:
except (ValidationError, json.JSONDecodeError) as e:
    raise ModelProviderError(
        f"Schema validation failed: {e}",
        provider_name=self.PROVIDER_NAME,
        original_message=str(source_content)[:500],
    ) from e

# After:
except (ValidationError, json.JSONDecodeError) as e:
    raise SchemaValidationError(
        f"Schema validation failed: {e}",
        provider_name=self.PROVIDER_NAME,
        original_message=str(source_content)[:500],
    ) from e
```

3. In `generate` (line 349-354), same change:
```python
# Before:
except (ValidationError, json.JSONDecodeError) as e:
    raise ModelProviderError(...)

# After:
except (ValidationError, json.JSONDecodeError) as e:
    raise SchemaValidationError(...)
```

In `amelia/drivers/cli/claude.py`:

1. Add import: `from amelia.core.exceptions import SchemaValidationError`

2. At line 399-400, change:
```python
# Before:
except ValidationError as e:
    raise RuntimeError(f"Claude SDK output did not match schema: {e}") from e

# After:
except ValidationError as e:
    raise SchemaValidationError(
        f"Claude SDK output did not match schema: {e}",
        provider_name="claude",
        original_message=str(e),
    ) from e
```

3. At line 427, update the `isinstance` check to also pass through `SchemaValidationError`:
```python
# Before:
if isinstance(e, RuntimeError):
    raise

# After:
if isinstance(e, (RuntimeError, SchemaValidationError)):
    raise
```

In `amelia/drivers/api/deepagents.py`:

1. Add import: `from amelia.core.exceptions import SchemaValidationError`

2. At line 405-409, change:
```python
# Before:
raise RuntimeError(
    f"Model did not call the {schema.__name__} tool to return structured output. ..."
)

# After:
raise SchemaValidationError(
    f"Model did not call the {schema.__name__} tool to return structured output. "
    f"Got {len(messages)} messages, last was {last_msg_type}. "
    "Ensure the model supports tool calling and the prompt instructs it to use the schema tool.",
    provider_name="api",
    original_message=f"Last message type: {last_msg_type}",
)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/drivers/test_codex_driver.py -v`
Expected: PASS

Run: `uv run pytest tests/unit/drivers/ -v`
Expected: PASS (check that no existing tests break)

**Step 5: Commit**

```bash
git add amelia/drivers/cli/codex.py amelia/drivers/cli/claude.py amelia/drivers/api/deepagents.py tests/unit/drivers/test_codex_driver.py
git commit -m "refactor: use SchemaValidationError for schema failures in all drivers"
```

---

### Task 10: Update plan_validator_node to Catch SchemaValidationError

**Files:**
- Modify: `amelia/pipelines/implementation/nodes.py:85-103` (the try/except block)
- Modify: `tests/unit/core/test_plan_validator_node.py` (add test)

**Context:** The node currently catches `RuntimeError` from `extract_structured` and falls back to regex extraction. After Task 9, drivers raise `SchemaValidationError` instead. The except clause must catch both for the fallback to work.

**Step 1: Write the failing test**

```python
# Add to tests/unit/core/test_plan_validator_node.py
from amelia.core.exceptions import SchemaValidationError


class TestPlanValidatorNodeSchemaError:
    """Tests for SchemaValidationError handling in plan_validator_node."""

    async def test_catches_schema_validation_error_and_uses_fallback(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """SchemaValidationError from extract_structured should use fallback, not crash."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = """# Feature Plan

**Goal:** Add authentication

### Task 1: Setup
Create auth module.

### Task 2: Tests
Write tests for auth module with coverage.
This content is long enough to pass the minimum length validation.
"""
        create_plan_file(tmp_path, plan)
        config = make_config(mock_profile)

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            side_effect=SchemaValidationError(
                "Schema validation failed",
                provider_name="codex",
            ),
        ):
            result = await plan_validator_node(mock_state, config)

        # Should fall back to regex extraction, not crash
        assert result["goal"] is not None
        assert result["plan_markdown"] is not None
        # Validation should still run on fallback output
        assert result["plan_validation_result"] is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_plan_validator_node.py::TestPlanValidatorNodeSchemaError -v`
Expected: FAIL (node doesn't catch SchemaValidationError, raises it)

**Step 3: Write implementation**

In `plan_validator_node` in `amelia/pipelines/implementation/nodes.py`, update the except clause:

```python
# Before:
except RuntimeError as e:

# After:
except (RuntimeError, SchemaValidationError) as e:
```

Add import at top of file: `from amelia.core.exceptions import SchemaValidationError`

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_plan_validator_node.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/nodes.py tests/unit/core/test_plan_validator_node.py
git commit -m "fix: plan_validator catches SchemaValidationError for fallback"
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

Address any lint errors, type errors, or test failures. Common issues:
- Missing imports in `__init__.py` files
- Type annotation mismatches
- Unused imports after refactoring

**Step 5: Final commit**

```bash
git add -u
git commit -m "chore: fix lint and type issues from plan validation feature"
```
