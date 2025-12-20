# Integration Test Gaps & Test Suite Rewrite Plan

**Generated**: 2025-12-16
**Codebase**: amelia-feature

## Executive Summary

The codebase has **~80 unit test files (~12,000+ lines)** but only **~10 integration test files (~2,200 lines)**. The unit tests are fundamentally broken:

1. **They mock what they test** - Tests that mock `Developer`, then assert `Developer` was called, test nothing
2. **They missed critical bugs** - 3 serious bugs exist in production code that 12,000 lines of tests didn't catch
3. **They give false confidence** - Tests pass but real execution paths break

**Recommendation: Delete ~10,000 lines of useless tests. Write ~2,000 lines of real integration tests.**

---

## Part 1: Critical Bugs Found (Missed by Existing Tests)

### Bug 1: `get_cascade_skips()` Never Called

**Location**: `amelia/agents/developer.py:518-535`

The function is defined but **never invoked** in production code:

```python
def get_cascade_skips(step_id: str, plan: ExecutionPlan, skip_reasons: dict[str, str]) -> dict[str, str]:
    """Find all steps that depend on a skipped/failed step."""
    # Implemented but not used!
```

**Impact**: If step A depends on skipped step B, A is skipped. But if step C depends on A, C is NOT automatically skipped. This breaks the dependency contract.

**Why tests missed it**: Tests mock the entire Developer class, never exercising real step execution.

### Bug 2: Index Out of Bounds Vulnerability

**Locations**:
- `amelia/core/orchestrator.py:532` - `route_after_developer()`
- `amelia/agents/developer.py:645` - `_recover_from_blocker()`
- `amelia/agents/reviewer.py:66` - batch context access
- `amelia/core/orchestrator.py` - `should_checkpoint()`

```python
# Multiple locations access state.execution_plan.batches[state.current_batch_index]
# WITHOUT validation that current_batch_index < len(batches)
```

**Impact**: Workflow crash with IndexError if batch index exceeds plan length.

**Why tests missed it**: Tests use mocked state factories with hardcoded valid indices.

### Bug 3: ExecutionPlan None Not Validated

**Locations**:
- `amelia/agents/developer.py:645` - in `_recover_from_blocker()`
- `amelia/agents/reviewer.py:63-66` - assumes plan exists
- `amelia/core/orchestrator.py:532` - in routing

**Impact**: NoneType errors when execution_plan wasn't persisted/restored correctly.

**Why tests missed it**: Tests always provide valid ExecutionPlan in mocked state.

---

## Part 2: Critical Integration Test Gaps

### Gap 1: End-to-End Orchestrator Graph Execution
**Currently**: All orchestrator node tests mock the LangGraph graph itself
**Missing**: Tests that run the actual compiled graph with real node functions

```
UNTESTED PATH:
architect_node → human_approval_node (interrupt) → [resume] →
developer_node → batch_approval_node (interrupt) → [resume] →
developer_node → reviewer_node → END
```

### Gap 2: Checkpoint Persistence & Resume
**Currently**: AsyncSqliteSaver is always mocked
**Missing**: Tests that:
- Save checkpoint to real SQLite
- Crash/restart server
- Resume from checkpoint with correct state

### Gap 3: State Synchronization (Checkpoint ↔ Database)
**Currently**: `_sync_plan_from_checkpoint()` never tested with real checkpoint
**Missing**: Verify `execution_plan` syncs correctly when workflow blocks

### Gap 4: Multi-Batch Execution with Real Commands
**Currently**: `Developer.run()` mocked, `run_shell_command` mocked
**Missing**: Tests that execute real shell commands across multiple batches

### Gap 5: Blocker Recovery with Git Revert
**Currently**: `revert_to_git_snapshot()` mocked
**Missing**: Tests that create real git commits, hit blocker, and verify revert works

### Gap 6: Cascade Skip Propagation
**Currently**: `get_cascade_skips()` is defined but **NEVER CALLED** in production code
**Missing**: Tests that verify dependent steps are skipped when parent fails

### Gap 7: Review Loop (Reject → Fix → Approve)
**Currently**: Only unit tests for `should_continue_review_loop()` routing
**Missing**: Full loop where reviewer rejects, developer fixes, reviewer approves

### Gap 8: Server Mode Interrupt/Resume Cycle
**Currently**: `__interrupt__` detection tested with mocked graph output
**Missing**: Real LangGraph interrupt → REST API approval → resume

### Gap 9: WebSocket Reconnection with Backfill
**Currently**: Reconnection logic tested with mocked repository
**Missing**: Real reconnection with `?since=event_id` and database backfill

### Gap 10: Index Out of Bounds Edge Cases
**Currently**: No tests verify behavior when `current_batch_index >= len(batches)`
**Missing**: Tests for boundary conditions in routing and checkpoint logic

---

## Part 3: Tests to DELETE (~10,000 lines)

These tests mock everything and provide no value:

### Orchestrator Tests (DELETE ALL - ~1,200 lines)
```
tests/unit/test_orchestrator_developer_node.py   (128 lines) - Mocks Developer entirely
tests/unit/test_orchestrator_reviewer_node.py    (68 lines)  - Mocks Reviewer entirely
tests/unit/test_orchestrator_batch_approval.py   (121 lines) - Mocks state, tests nothing
tests/unit/test_orchestrator_routing.py          (347 lines) - Covered by integration tests
tests/unit/test_orchestrator_review_loop.py      (200 lines) - Covered by integration tests
tests/unit/test_orchestrator_interrupt.py        (28 lines)  - Trivial, covered by integration
tests/unit/test_orchestrator_checkpoint.py       (95 lines)  - Mocks checkpoint, tests nothing
tests/unit/test_orchestrator_blocker_resolution.py (226 lines) - Mocks git, tests nothing
```

### Agent Tests (DELETE ALL - ~3,000 lines)
```
tests/unit/agents/test_architect.py              (954 lines)  - Mocks driver, tests prompts not behavior
tests/unit/agents/test_developer.py              (965 lines)  - Mocks shell, tests nothing real
tests/unit/agents/test_developer_execute_batch.py (1000 lines) - Mocks everything
tests/unit/agents/test_reviewer.py               (60 lines)   - Mocks driver
```

### Server Tests (DELETE ALL - ~1,500 lines)
```
tests/unit/server/orchestrator/test_service.py   (974 lines)  - Patches _run_workflow
tests/unit/server/orchestrator/test_execution_bridge.py (251 lines)
tests/unit/server/orchestrator/test_retry_logic.py (261 lines)
```

### Client Tests (DELETE ALL - ~730 lines)
```
tests/unit/client/test_api.py                    (246 lines)  - Mocks HTTP client
tests/unit/client/test_cli.py                    (481 lines)  - Mocks subprocess
```

### Driver Tests (DELETE MOST - ~500 lines)
```
tests/unit/test_claude_driver.py                 (604 lines)  - Keep message conversion only (~100 lines)
tests/unit/drivers/test_execute_agentic_messages.py - DELETE
```

### Trivial Tests (DELETE - ~200 lines)
```
tests/unit/test_exceptions.py                    - Tests exception classes exist
tests/unit/test_logging.py                       - Tests logger configured
tests/unit/test_types.py (portions)              - Tests Pydantic does its job
```

---

## Part 4: Tests to KEEP (~2,000 lines)

These test real, isolated logic:

### Security Tests (KEEP ALL)
```
tests/unit/test_safe_shell_executor.py           (142 lines) - Command blocking/validation
tests/unit/test_safe_file_writer.py              (113 lines) - Path traversal prevention
```

### Model Validation (KEEP)
```
tests/unit/test_state.py                         (~400 lines) - State model validation
tests/unit/test_profile_constraints.py           - Configuration validation
tests/unit/test_tracker_config_validation.py     - Tracker config validation
```

### Pure Logic Tests (KEEP)
```
tests/unit/test_context.py                       (357 lines) - Context compilation
tests/unit/agents/test_architect_context.py      (372 lines) - Prompt generation
tests/unit/agents/test_reviewer_context.py       (294 lines) - Prompt generation
tests/unit/test_git_utils.py                     (343 lines) - Git utilities
tests/unit/drivers/cli/test_claude_convert.py    - Message conversion
```

### Database Tests (KEEP - actually integration tests)
```
tests/unit/server/database/test_repository.py    (348 lines) - Real database
tests/unit/server/database/test_connection.py    - Real connection
```

---

## Part 5: New Integration Tests to WRITE (~2,000 lines)

### Core Workflow Tests
```
tests/integration/
├── test_full_workflow_cycle.py         (~400 lines)
│   - Happy path: plan → approve → execute → review → done
│   - Uses real LangGraph graph with MemorySaver
│   - Uses TestModel driver for deterministic responses
│
├── test_multi_batch_execution.py       (~300 lines)
│   - Multiple batches with trust level variations
│   - Checkpoint after each batch
│   - Verify state persists correctly
│
├── test_blocker_recovery.py            (~300 lines)
│   - Step fails → blocker raised
│   - Skip resolution → continue
│   - Retry resolution → re-execute
│   - Abort resolution → workflow ends
│   - Abort+revert → git state restored
│
├── test_review_loop.py                 (~200 lines)
│   - Reviewer rejects → developer continues
│   - Reviewer approves → workflow completes
│   - Max iterations reached → workflow fails
│
├── test_cascade_skip_propagation.py    (~200 lines)
│   - Step A fails
│   - Step B (depends on A) auto-skipped
│   - Step C (depends on B) auto-skipped
│   - Step D (no deps) executes
```

### State & Persistence Tests
```
├── test_checkpoint_persistence.py      (~200 lines)
│   - Save checkpoint to SQLite
│   - "Crash" (clear in-memory state)
│   - Resume from checkpoint
│   - Verify state integrity
│
├── test_boundary_conditions.py         (~150 lines)
│   - current_batch_index >= len(batches)
│   - ExecutionPlan is None
│   - Empty batches list
│   - Circular dependencies
```

### Server Integration Tests
```
├── test_server_interrupt_resume.py     (~200 lines)
│   - Workflow hits interrupt
│   - REST API returns blocked status
│   - POST /approve resumes workflow
│   - Verify next interrupt or completion
│
├── test_websocket_events.py            (~150 lines)
│   - Connect WebSocket
│   - Start workflow
│   - Receive all events in order
│   - Reconnect with ?since= for backfill
```

### Example Test Structure

```python
# tests/integration/test_full_workflow_cycle.py
import pytest
from langgraph.checkpoint.memory import MemorySaver

from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile


@pytest.fixture
def orchestrator_graph():
    """Real LangGraph graph with in-memory checkpoint."""
    return create_orchestrator_graph(
        checkpoint_saver=MemorySaver(),
        interrupt_before=["human_approval_node", "batch_approval_node"],
    )


@pytest.fixture
def initial_state():
    """Real ExecutionState with test issue."""
    return ExecutionState(
        issue=Issue(id="TEST-1", title="Add feature", description="..."),
        profile=Profile(name="test", driver="test:model", tracker="noop"),
    )


async def test_happy_path_completes(orchestrator_graph, initial_state):
    """Full workflow: plan → approve → execute → review → done."""
    config = {"configurable": {"thread_id": "test-001"}}

    # Phase 1: Run until first interrupt (plan approval)
    async for chunk in orchestrator_graph.astream(
        initial_state.model_dump(mode="json"), config
    ):
        if "__interrupt__" in chunk:
            break

    # Verify plan exists
    state = await orchestrator_graph.aget_state(config)
    assert state.values.get("execution_plan") is not None
    assert len(state.values["execution_plan"]["batches"]) > 0

    # Phase 2: Approve and run to completion
    await orchestrator_graph.aupdate_state(config, {"human_approved": True})

    async for chunk in orchestrator_graph.astream(None, config):
        if "__interrupt__" in chunk:
            # Auto-approve batch checkpoints for this test
            await orchestrator_graph.aupdate_state(config, {"human_approved": True})

    # Verify completion
    final = await orchestrator_graph.aget_state(config)
    assert final.values.get("workflow_status") == "completed"


async def test_blocker_skip_continues(orchestrator_graph, initial_state):
    """Blocker with skip resolution continues to next step."""
    # ... test implementation


async def test_index_out_of_bounds_handled(orchestrator_graph):
    """Graceful handling when batch index exceeds plan length."""
    # ... test implementation
```

---

## Part 6: Execution Plan

### Phase 1: Fix Critical Bugs (Before Any Test Changes)
1. Add bounds check in `route_after_developer()` for `current_batch_index`
2. Add ExecutionPlan None checks before accessing `.batches`
3. Wire up `get_cascade_skips()` to actually be called

### Phase 2: Delete Useless Tests
```bash
# Delete orchestrator unit tests
rm tests/unit/test_orchestrator_*.py

# Delete agent unit tests (keep context tests)
rm tests/unit/agents/test_architect.py
rm tests/unit/agents/test_developer.py
rm tests/unit/agents/test_developer_execute_batch.py
rm tests/unit/agents/test_reviewer.py

# Delete server orchestrator unit tests
rm tests/unit/server/orchestrator/test_service.py
rm tests/unit/server/orchestrator/test_execution_bridge.py
rm tests/unit/server/orchestrator/test_retry_logic.py

# Delete client unit tests
rm tests/unit/client/test_api.py
rm tests/unit/client/test_cli.py

# Delete trivial tests
rm tests/unit/test_exceptions.py
rm tests/unit/test_logging.py
```

### Phase 3: Write New Integration Tests
1. `test_full_workflow_cycle.py` - Basic happy path
2. `test_boundary_conditions.py` - Edge cases and bug regression tests
3. `test_cascade_skip_propagation.py` - Dependency handling
4. `test_blocker_recovery.py` - All resolution paths
5. `test_checkpoint_persistence.py` - State durability

### Phase 4: Verify Coverage
```bash
# Run new tests
uv run pytest tests/integration/ -v

# Check coverage of critical paths
uv run pytest --cov=amelia.core.orchestrator --cov=amelia.agents tests/integration/
```

---

## Summary

| Metric | Before | After |
|--------|--------|-------|
| Unit test files | 80+ | ~15 |
| Unit test lines | ~12,000 | ~2,000 |
| Integration test files | 10 | 15 |
| Integration test lines | ~2,200 | ~4,200 |
| **Total test lines** | **~14,200** | **~6,200** |
| Critical bugs caught | 0 of 3 | All |
| False confidence | High | None |

**Delete 10,000 lines. Write 2,000 lines. Catch real bugs.**

---

## Appendix: File Locations

### Files with Critical Bugs
| Bug | Location |
|-----|----------|
| `get_cascade_skips()` unused | `amelia/agents/developer.py:518-535` |
| Index out of bounds | `amelia/core/orchestrator.py:532`, `amelia/agents/developer.py:645`, `amelia/agents/reviewer.py:66` |
| ExecutionPlan None | Same locations as above |

### Core Code Under Test
| Component | Location |
|-----------|----------|
| Orchestrator | `amelia/core/orchestrator.py` |
| State | `amelia/core/state.py` |
| Developer | `amelia/agents/developer.py` |
| Architect | `amelia/agents/architect.py` |
| Reviewer | `amelia/agents/reviewer.py` |
| Server Service | `amelia/server/orchestrator/service.py` |
