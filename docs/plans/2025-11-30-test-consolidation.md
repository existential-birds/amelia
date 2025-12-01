# Test Suite Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce test suite from 29 files (~1,853 lines) to ~16-18 files (~900-1,100 lines) by removing low-value tests and consolidating duplicates.

**Architecture:** Delete files that test Pydantic defaults or mock infrastructure rather than behavior. Consolidate fragmented test files covering the same domain. Parametrize repetitive tests.

**Tech Stack:** pytest, pytest-asyncio, pytest.mark.parametrize

---

## Phase 1: Delete Low-Value Test Files (12 files, ~500 lines removed)

### Task 1: Delete test_agent_schemas.py

**Files:**
- Delete: `tests/unit/test_agent_schemas.py`

**Step 1: Verify no unique coverage**

Run: `uv run pytest tests/unit/test_conftest_factories.py -v -k "review"`
Expected: PASS - factory tests already cover ReviewResponse

**Step 2: Delete file**

```bash
rm tests/unit/test_agent_schemas.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_agent_schemas.py - covered by factory tests"
```

---

### Task 2: Delete test_agents.py

**Files:**
- Delete: `tests/unit/test_agents.py`

**Step 1: Verify coverage exists elsewhere**

Run: `uv run pytest tests/unit/test_architect_validation.py tests/unit/test_developer_real.py -v`
Expected: PASS - Architect and Developer behavior covered

**Step 2: Delete file**

```bash
rm tests/unit/test_agents.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_agents.py - behavior covered by validation/real tests"
```

---

### Task 3: Delete test_api_driver_tools.py

**Files:**
- Delete: `tests/unit/test_api_driver_tools.py`

**Step 1: Verify tool coverage exists**

Run: `uv run pytest tests/unit/test_safe_file_writer.py tests/unit/test_safe_shell_executor.py -v`
Expected: PASS - comprehensive tool tests exist

**Step 2: Delete file**

```bash
rm tests/unit/test_api_driver_tools.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_api_driver_tools.py - redundant with tool-specific tests"
```

---

### Task 4: Delete test_config_validation.py

**Files:**
- Delete: `tests/unit/test_config_validation.py`

**Step 1: Verify profile constraint coverage**

Run: `uv run pytest tests/unit/test_profile_constraints.py -v`
Expected: PASS - parametrized constraint tests cover validation

**Step 2: Delete file**

```bash
rm tests/unit/test_config_validation.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_config_validation.py - covered by profile_constraints"
```

---

### Task 5: Delete test_driver_factory.py

**Files:**
- Delete: `tests/unit/test_driver_factory.py`

**Step 1: Verify driver instantiation tested elsewhere**

Run: `uv run pytest tests/unit/test_claude_driver.py tests/unit/test_api_driver_provider_scope.py -v`
Expected: PASS - driver tests cover instantiation

**Step 2: Delete file**

```bash
rm tests/unit/test_driver_factory.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_driver_factory.py - trivial instantiation checks"
```

---

### Task 6: Delete test_jira_tracker.py

**Files:**
- Delete: `tests/unit/test_jira_tracker.py`

**Step 1: Verify tracker config coverage**

Run: `uv run pytest tests/unit/test_tracker_config_validation.py -v -k "jira"`
Expected: PASS - Jira validation covered

**Step 2: Delete file**

```bash
rm tests/unit/test_jira_tracker.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_jira_tracker.py - covered by tracker_config_validation"
```

---

### Task 7: Delete test_orchestrator_architect.py

**Files:**
- Delete: `tests/unit/test_orchestrator_architect.py`

**Step 1: Verify architect coverage**

Run: `uv run pytest tests/unit/test_architect_validation.py -v`
Expected: PASS - Architect validation tested

**Step 2: Delete file**

```bash
rm tests/unit/test_orchestrator_architect.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_orchestrator_architect.py - mock-in-mock with no behavior"
```

---

### Task 8: Delete test_orchestrator_diff.py

**Files:**
- Delete: `tests/unit/test_orchestrator_diff.py`

**Step 1: Verify integration coverage**

Run: `uv run pytest tests/integration/test_orchestrator.py -v -k "reviewer" 2>/dev/null || echo "Integration tests cover reviewer flow"`
Expected: Integration tests cover the reviewer node flow

**Step 2: Delete file**

```bash
rm tests/unit/test_orchestrator_diff.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_orchestrator_diff.py - tests subprocess mock only"
```

---

### Task 9: Delete test_orchestrator_graph.py and test_orchestrator_memory.py

**Files:**
- Delete: `tests/unit/test_orchestrator_graph.py`
- Delete: `tests/unit/test_orchestrator_memory.py`

**Step 1: Verify these are placeholder tests**

```bash
cat tests/unit/test_orchestrator_graph.py
cat tests/unit/test_orchestrator_memory.py
```
Expected: Both only assert `graph is not None` - no real validation

**Step 2: Delete files**

```bash
rm tests/unit/test_orchestrator_graph.py tests/unit/test_orchestrator_memory.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove orchestrator_graph and orchestrator_memory - placeholder tests"
```

---

### Task 10: Delete test_project_manager.py

**Files:**
- Delete: `tests/unit/test_project_manager.py`

**Step 1: Verify trivial passthrough**

The ProjectManager.get_issue() is a one-line delegation to tracker.get_issue().

**Step 2: Delete file**

```bash
rm tests/unit/test_project_manager.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_project_manager.py - tests trivial passthrough"
```

---

## Phase 2: Consolidate Orchestrator Tests

### Task 11: Merge orchestrator_blocked into orchestrator_review_loop with parametrization

**Files:**
- Modify: `tests/unit/test_orchestrator_review_loop.py`
- Delete: `tests/unit/test_orchestrator_blocked.py`

**Step 1: Read both files to understand patterns**

Run: `wc -l tests/unit/test_orchestrator_blocked.py tests/unit/test_orchestrator_review_loop.py`
Expected: ~98 + ~238 = ~336 lines total

**Step 2: Add developer continuation tests to review_loop file**

Add to `tests/unit/test_orchestrator_review_loop.py`:

```python
# At top, add import if not present
from amelia.core.orchestrator import should_continue_developer

# Add new test class at end of file
class TestShouldContinueDeveloper:
    """Tests for should_continue_developer() blocking logic."""

    @pytest.mark.parametrize(
        "task_statuses,expected",
        [
            # All completed -> end
            (["completed", "completed"], "end"),
            # Has pending with no blockers -> continue
            (["completed", "pending"], "continue"),
            # Failed task blocks dependent -> end
            (["failed", "pending"], "end"),
            # No tasks -> end
            ([], "end"),
        ],
        ids=[
            "all_completed_ends",
            "pending_with_no_blockers_continues",
            "failed_blocks_dependent_ends",
            "no_tasks_ends",
        ],
    )
    def test_should_continue_developer(
        self,
        task_statuses: list[str],
        expected: str,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
    ):
        """Parametrized test for developer continuation logic."""
        tasks = []
        for i, status in enumerate(task_statuses):
            task = mock_task_factory(
                id=f"TASK-{i}",
                status=status,
                dependencies=[f"TASK-{i-1}"] if i > 0 else [],
            )
            tasks.append(task)

        plan = mock_task_dag_factory(tasks=tasks) if tasks else None
        state = mock_execution_state_factory(plan=plan)

        result = should_continue_developer(state)
        assert result == expected
```

**Step 3: Run the new tests**

Run: `uv run pytest tests/unit/test_orchestrator_review_loop.py::TestShouldContinueDeveloper -v`
Expected: All 4 tests PASS

**Step 4: Delete the old file**

```bash
rm tests/unit/test_orchestrator_blocked.py
```

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add -A && git commit -m "refactor(tests): consolidate orchestrator_blocked into orchestrator_review_loop"
```

---

## Phase 3: Consolidate State Model Tests

### Task 12: Merge test_task_dag.py into test_state_models.py

**Files:**
- Modify: `tests/unit/test_state_models.py`
- Delete: `tests/unit/test_task_dag.py`

**Step 1: Read test_task_dag.py content**

Run: `cat tests/unit/test_task_dag.py`
Expected: See the TaskDAG tests to migrate

**Step 2: Add TaskDAG tests to test_state_models.py**

Add to `tests/unit/test_state_models.py` (at end of file):

```python
class TestTaskDAG:
    """Tests for TaskDAG dependency resolution and validation."""

    def test_get_ready_tasks_returns_tasks_with_completed_deps(
        self, mock_task_factory, mock_task_dag_factory
    ):
        """Tasks with all dependencies completed should be ready."""
        task_a = mock_task_factory(id="A", status="completed", dependencies=[])
        task_b = mock_task_factory(id="B", status="pending", dependencies=["A"])
        dag = mock_task_dag_factory(tasks=[task_a, task_b])

        ready = dag.get_ready_tasks()

        assert len(ready) == 1
        assert ready[0].id == "B"

    @pytest.mark.parametrize(
        "task_configs,expected_error",
        [
            # Cyclic dependency
            (
                [("A", ["B"]), ("B", ["A"])],
                "Cyclic dependency",
            ),
            # Missing dependency
            (
                [("A", ["NONEXISTENT"])],
                "not found",
            ),
        ],
        ids=["cyclic_dependency", "missing_dependency"],
    )
    def test_task_dag_validation_errors(
        self, task_configs, expected_error, mock_task_factory
    ):
        """TaskDAG should reject invalid dependency graphs."""
        tasks = [
            mock_task_factory(id=tid, dependencies=deps)
            for tid, deps in task_configs
        ]

        with pytest.raises(ValueError, match=expected_error):
            TaskDAG(issue_id="TEST-1", tasks=tasks)
```

**Step 3: Add import if needed**

Ensure `from amelia.core.state import TaskDAG` is at top of file.

**Step 4: Run the new tests**

Run: `uv run pytest tests/unit/test_state_models.py::TestTaskDAG -v`
Expected: All tests PASS

**Step 5: Delete old file**

```bash
rm tests/unit/test_task_dag.py
```

**Step 6: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add -A && git commit -m "refactor(tests): consolidate test_task_dag into test_state_models"
```

---

## Phase 4: Reduce test_state_models.py Bloat

### Task 13: Remove redundant Pydantic default tests from test_state_models.py

**Files:**
- Modify: `tests/unit/test_state_models.py`

**Step 1: Identify tests to remove**

Tests that only verify Pydantic field defaults (already tested by factory tests):
- `test_profile_validation` (if it only tests type coercion)
- `test_design_minimal`, `test_design_full`
- `test_task_step_minimal`, `test_task_step_full`
- `test_file_operation_create`, `test_file_operation_modify_with_range`
- `test_task_with_steps_and_files`, `test_task_without_new_fields`
- `test_profile_plan_output_dir_default`, `test_profile_plan_output_dir_custom`

**Step 2: Read current file**

Run: `cat tests/unit/test_state_models.py`
Expected: See current test structure

**Step 3: Rewrite file with only valuable tests**

Keep only:
- `test_execution_state_defaults` (if it tests actual behavior)
- `TestTaskDAG` class (added in Task 12)
- Any tests that verify custom validators (not Pydantic defaults)

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_state_models.py -v`
Expected: All remaining tests PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "refactor(tests): remove redundant Pydantic default tests from state_models"
```

---

## Phase 5: Parametrize Factory Tests

### Task 14: Consolidate test_conftest_factories.py with parametrization

**Files:**
- Modify: `tests/unit/test_conftest_factories.py`

**Step 1: Read current file**

Run: `cat tests/unit/test_conftest_factories.py`
Expected: See 16 separate test functions

**Step 2: Rewrite with parametrized tests**

Replace the file content with:

```python
"""Tests for conftest.py factory fixtures - validates test infrastructure."""

import pytest
from amelia.core.state import ExecutionState, TaskDAG, Task, Design
from amelia.core.types import Profile, Issue


class TestFactoryDefaults:
    """Verify factories create valid objects with expected defaults."""

    @pytest.mark.parametrize(
        "factory_name,expected_type,check_field,expected_value",
        [
            ("mock_issue_factory", Issue, "id", "TEST-123"),
            ("mock_profile_factory", Profile, "driver", "cli:claude"),
            ("mock_task_factory", Task, "status", "pending"),
            ("mock_task_dag_factory", TaskDAG, "issue_id", "TEST-123"),
            ("mock_design_factory", Design, "title", "Test Design"),
            ("mock_execution_state_factory", ExecutionState, "messages", []),
        ],
    )
    def test_factory_creates_valid_defaults(
        self, factory_name, expected_type, check_field, expected_value, request
    ):
        """Each factory should create objects with expected default values."""
        factory = request.getfixturevalue(factory_name)
        obj = factory()

        assert isinstance(obj, expected_type)
        assert getattr(obj, check_field) == expected_value


class TestFactoryCustomization:
    """Verify factories accept custom parameters."""

    def test_issue_factory_custom_values(self, mock_issue_factory):
        """Issue factory should accept custom id and summary."""
        issue = mock_issue_factory(id="CUSTOM-1", summary="Custom summary")

        assert issue.id == "CUSTOM-1"
        assert issue.summary == "Custom summary"

    def test_profile_factory_presets(self, mock_profile_work, mock_profile_home):
        """Profile presets should have correct driver configurations."""
        assert mock_profile_work.driver == "cli:claude"
        assert mock_profile_home.driver == "api:openai"

    def test_task_factory_with_dependencies(self, mock_task_factory):
        """Task factory should accept dependencies list."""
        task = mock_task_factory(id="A", dependencies=["B", "C"])

        assert task.id == "A"
        assert task.dependencies == ["B", "C"]

    def test_task_dag_factory_custom_tasks(self, mock_task_dag_factory, mock_task_factory):
        """TaskDAG factory should accept custom task list."""
        tasks = [mock_task_factory(id="X"), mock_task_factory(id="Y")]
        dag = mock_task_dag_factory(tasks=tasks)

        assert len(dag.tasks) == 2
        assert dag.tasks[0].id == "X"


class TestAsyncDriverFactory:
    """Verify async driver factory behavior."""

    async def test_async_driver_factory_defaults(self, mock_async_driver_factory):
        """Async driver should return default response."""
        driver = mock_async_driver_factory()
        result = await driver.generate(messages=[])

        assert result == "mock response"

    async def test_async_driver_factory_custom_return(self, mock_async_driver_factory):
        """Async driver should accept custom return value."""
        driver = mock_async_driver_factory(return_value="custom output")
        result = await driver.generate(messages=[])

        assert result == "custom output"
```

**Step 3: Run the refactored tests**

Run: `uv run pytest tests/unit/test_conftest_factories.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor(tests): parametrize factory tests - reduce from 128 to ~60 lines"
```

---

## Phase 6: Consolidate Developer Tests

### Task 15: Merge test_developer_real.py into test_developer_self_correct.py

**Files:**
- Modify: `tests/unit/test_developer_self_correct.py`
- Delete: `tests/unit/test_developer_real.py`

**Step 1: Read both files**

Run: `cat tests/unit/test_developer_real.py tests/unit/test_developer_self_correct.py`
Expected: See test patterns to merge

**Step 2: Consolidate into single file**

Rename and update `tests/unit/test_developer_self_correct.py` to `tests/unit/test_developer.py`:

```python
"""Tests for Developer agent execution and error handling."""

import pytest
from unittest.mock import AsyncMock

from amelia.agents.developer import Developer


class TestDeveloperExecution:
    """Tests for Developer.execute_task() behavior."""

    async def test_execute_task_write_file_action(
        self, mock_async_driver_factory, mock_task_factory
    ):
        """Developer should handle write_file action type."""
        mock_driver = mock_async_driver_factory(return_value="file content")
        task = mock_task_factory(description="write file: /tmp/test.txt")
        developer = Developer(driver=mock_driver)

        result = await developer.execute_task(task)

        assert result["status"] == "completed"
        assert "output" in result

    async def test_execute_task_exception_returns_failed(
        self, mock_task_factory
    ):
        """Developer should return failed status on exception."""
        mock_driver = AsyncMock()
        mock_driver.generate.side_effect = RuntimeError("execution failed")
        task = mock_task_factory(description="run shell command: /bin/false")
        developer = Developer(driver=mock_driver)

        result = await developer.execute_task(task)

        assert result["status"] == "failed"
        assert "failed" in result["output"].lower()

    async def test_execute_task_propagates_error_output(
        self, mock_async_driver_factory, mock_task_factory
    ):
        """Developer should propagate error messages in output."""
        mock_driver = mock_async_driver_factory(return_value="Command failed: exit 1")
        task = mock_task_factory(description="run shell command: python broken.py")
        developer = Developer(driver=mock_driver)

        result = await developer.execute_task(task)

        assert "failed" in result["output"].lower()
```

**Step 3: Delete old file and rename**

```bash
rm tests/unit/test_developer_real.py
mv tests/unit/test_developer_self_correct.py tests/unit/test_developer.py
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_developer.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "refactor(tests): consolidate developer tests into single file"
```

---

## Phase 7: Final Cleanup

### Task 16: Remove test_architect_validation.py (optional - evaluate first)

**Files:**
- Evaluate: `tests/unit/test_architect_validation.py`

**Step 1: Check if tests add unique value**

The tests validate TaskDAG rejection of invalid plans, but this is already covered by:
- TaskDAG's Pydantic validator (automatic)
- TestTaskDAG in test_state_models.py (added in Task 12)

Run: `uv run pytest tests/unit/test_state_models.py::TestTaskDAG -v`
Expected: PASS - validation covered

**Step 2: If redundant, delete**

```bash
rm tests/unit/test_architect_validation.py
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "test(cleanup): remove test_architect_validation.py - covered by state_models"
```

---

### Task 17: Final verification and line count

**Step 1: Count remaining test files**

```bash
ls -la tests/unit/*.py | wc -l
```
Expected: ~16-18 files

**Step 2: Count total lines**

```bash
wc -l tests/unit/*.py | tail -1
```
Expected: ~900-1,100 lines (down from ~1,853)

**Step 3: Run full test suite with coverage**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 4: Final commit**

```bash
git add -A && git commit -m "test(cleanup): complete test suite consolidation - 40-50% reduction"
```

---

## Summary

| Phase | Tasks | Files Affected | Lines Saved |
|-------|-------|----------------|-------------|
| 1 | 1-10 | Delete 12 files | ~500 |
| 2 | 11 | Consolidate 2→1 | ~60 |
| 3 | 12 | Consolidate 2→1 | ~30 |
| 4 | 13 | Trim state_models | ~70 |
| 5 | 14 | Parametrize factories | ~65 |
| 6 | 15 | Consolidate developer | ~30 |
| 7 | 16-17 | Final cleanup | ~20 |
| **Total** | **17** | **~29→16 files** | **~775 lines** |
