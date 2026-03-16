# Codebase Concerns

**Analysis Date:** 2026-03-13

## Tech Debt

**Orchestrator God Object (Critical):**
- Issue: `amelia/server/orchestrator/service.py` is 3,089 lines with 52 methods in a single `OrchestratorService` class. It handles workflow creation, execution, retry logic, event emission, checkpoint management, plan validation, approval/rejection, batch workflows, review workflows, and agent message extraction.
- Files: `amelia/server/orchestrator/service.py`
- Impact: Extremely difficult to modify safely. Any change risks unintended side effects across unrelated workflow types. Adding new workflow types requires modifying this already-massive file.
- Fix approach: Extract into focused services: `WorkflowExecutionService`, `WorkflowEventService`, `WorkflowApprovalService`, `WorkflowPlanService`. The `_emit_*_messages` methods (lines 2117-2300) are a self-contained group that can be extracted first.

**Duplicated Daytona Provider Creation:**
- Issue: The `create_daytona_provider` import and instantiation pattern is copy-pasted 4 times across the orchestrator with identical boilerplate (import, try/except, pass on error).
- Files: `amelia/server/orchestrator/service.py` (lines 1257, 1387, 1668, 2453)
- Impact: Any change to sandbox provisioning logic must be replicated in 4 places. Easy to miss one.
- Fix approach: Extract a `_create_sandbox_provider()` helper method on `OrchestratorService` that encapsulates the conditional creation + error handling.

**Global Mutable State in Dependencies:**
- Issue: `amelia/server/dependencies.py` uses module-level global variables (`_database`, `_orchestrator`, `_config`, `_knowledge_service`) with getter/setter functions. No thread safety, no lifecycle management.
- Files: `amelia/server/dependencies.py`
- Impact: Makes testing harder (must manually set/clear globals). Race conditions possible during startup/shutdown. Cannot run multiple server instances in-process.
- Fix approach: Use FastAPI's built-in dependency injection with `Depends()` and application state (`app.state`) instead of module globals.

**Dynamic Module Injection for LangGraph:**
- Issue: `rebuild_implementation_state()` uses `setattr` to inject `EvaluationResult` into the module namespace to work around LangGraph's `get_type_hints()` resolution.
- Files: `amelia/pipelines/implementation/state.py` (lines 113-127)
- Impact: Fragile coupling to LangGraph internals. If LangGraph changes its type resolution strategy, this breaks silently.
- Fix approach: Monitor LangGraph releases for native forward reference support. Consider defining all referenced types in the same module.

**Leftover Tool/Config Directories:**
- Issue: `.beagle/` directory contains stale files (`dev-server.log`, `llm-artifacts-review.json`) and `.serena/` directory contains cached data from previous tooling. These appear to be remnants of renamed/removed tools.
- Files: `.beagle/`, `.serena/`
- Impact: Confusing for developers. Not in `.gitignore` (`.beagle` may be committed).
- Fix approach: Delete both directories and add them to `.gitignore` if not already there.

## Security Considerations

**Shell Injection via `create_subprocess_shell`:**
- Risk: `amelia/tools/git_utils.py` uses `asyncio.create_subprocess_shell()` which passes commands through the shell. The `command` parameter is a raw string.
- Files: `amelia/tools/git_utils.py` (line 31)
- Current mitigation: Only called with hardcoded git commands internally (`git rev-parse HEAD`).
- Recommendations: Switch to `create_subprocess_exec` with argument lists to prevent shell injection if command inputs ever become user-controllable.

**Shell=True in DeepAgents Driver:**
- Risk: `subprocess.run` with `shell=True` executes arbitrary commands from the agent.
- Files: `amelia/drivers/api/deepagents.py` (line 170)
- Current mitigation: Acknowledged via `# noqa: S602 - intentional for local dev`. This is by design for agent command execution.
- Recommendations: Ensure this code path is never exposed in production without sandbox isolation. Document the security boundary clearly.

**Path Traversal Validation:**
- Risk: Workflow requests accept file paths for worktrees.
- Files: `amelia/server/models/requests.py` (line 186 - validation exists)
- Current mitigation: Path traversal characters are rejected in request validation.
- Recommendations: Continue enforcing this at the request layer. Add integration tests for path traversal attempts.

## Performance Bottlenecks

**Synchronous subprocess in DeepAgents Driver:**
- Problem: `amelia/drivers/api/deepagents.py` line 168 uses synchronous `subprocess.run` inside what should be an async context.
- Files: `amelia/drivers/api/deepagents.py` (line 168)
- Cause: Blocking call in an async driver blocks the event loop during command execution.
- Improvement path: Replace with `asyncio.create_subprocess_exec` to avoid blocking the event loop.

**Token Pricing Cache with Global Lock:**
- Problem: `amelia/server/models/tokens.py` uses a module-level `asyncio.Lock` and global mutable state for cached pricing data.
- Files: `amelia/server/models/tokens.py` (lines 67, 134, 143)
- Cause: All concurrent requests serialize on the lock when cache is cold or expired.
- Improvement path: Use a background refresh task instead of blocking callers. Consider `asyncio.Event` or TTL cache pattern.

## Fragile Areas

**Orchestrator Event Emission:**
- Files: `amelia/server/orchestrator/service.py` (lines 1485-2300)
- Why fragile: 8 separate `_emit_*_messages` methods parse node output dictionaries with manual key access. If any pipeline node changes its output schema, the corresponding emitter silently fails or emits incorrect events.
- Safe modification: Always update the emitter method when changing pipeline node output shapes. Add integration tests that verify event emission for each node type.
- Test coverage: Unit tests exist (`tests/unit/server/orchestrator/test_event_mapping.py`) but are limited to 81 lines.

**Broad Exception Handling:**
- Files: `amelia/server/orchestrator/service.py` (17 `except Exception` blocks), `amelia/drivers/api/deepagents.py`, `amelia/server/services/brainstorm.py`, `amelia/agents/oracle.py`
- Why fragile: Over 40 bare `except Exception` catches across the codebase. Many silently log and continue, which can mask bugs. Some catch-and-reraise patterns add noise without value (e.g., line 1222).
- Safe modification: Replace with specific exception types where possible. The `TRANSIENT_EXCEPTIONS` tuple in the orchestrator (line 68) shows the right pattern.
- Test coverage: Hard to test that exceptions are handled correctly when the catch is so broad.

**Pipeline State Reconstruction:**
- Files: `amelia/server/orchestrator/service.py` (method `_reconstruct_initial_state` at line 1013)
- Why fragile: Reconstructs `ImplementationState` from database records for workflow resume. If the state model evolves, reconstruction may produce invalid state.
- Safe modification: Add a version field to persisted state. Validate reconstructed state against the current model.
- Test coverage: Covered in `tests/unit/server/orchestrator/test_service.py` but the 1722-line test file is itself becoming unwieldy.

**Assert Statements in Production Code:**
- Files: `amelia/server/orchestrator/service.py` (lines 552, 678, 793, 1953), `amelia/server/dev.py` (lines 142, 173, 357, 358), `amelia/core/retry.py` (line 65)
- Why fragile: Python's `assert` is stripped when running with `-O` (optimized mode). If the server is ever run optimized, these safety checks disappear silently.
- Safe modification: Replace `assert` with explicit `if not ... : raise` checks in production code paths. The orchestrator asserts on `execution_state.issue is not None` are particularly critical.

## Test Coverage Gaps

**Shell Executor (No Tests):**
- What's not tested: `amelia/tools/shell_executor.py` has no dedicated test file.
- Files: `amelia/tools/shell_executor.py`
- Risk: Command execution logic untested. Timeout handling, output truncation could fail silently.
- Priority: Medium

**Git Utilities (No Tests):**
- What's not tested: `amelia/tools/git_utils.py` has no dedicated test file. Only `get_current_commit` exists but process timeout handling and error paths are untested.
- Files: `amelia/tools/git_utils.py`
- Risk: Git operations could fail in unexpected ways during workflow execution.
- Priority: Medium

**Integration Tests Sparse:**
- What's not tested: Only 40 integration test files vs 159 unit test files. The orchestrator (the most complex component) has zero integration tests. Integration tests only cover `server/database/` and `knowledge/`.
- Files: `tests/integration/`
- Risk: The end-to-end workflow execution path (orchestrator -> pipeline -> agent -> driver) is only tested via heavily mocked unit tests. Real component interactions are unverified.
- Priority: High

**Orchestrator Test File Bloat:**
- What's not tested: `tests/unit/server/orchestrator/test_service.py` at 1722 lines mirrors the orchestrator's own complexity. Hard to maintain and extend.
- Files: `tests/unit/server/orchestrator/test_service.py`
- Risk: Tests may not cover all paths in the 3089-line orchestrator. Test maintenance burden is high.
- Priority: Medium - split alongside orchestrator refactor.

## Dependencies at Risk

**LangGraph Tight Coupling:**
- Risk: The codebase has deep coupling to LangGraph's checkpointing, streaming, and state management internals. The dynamic `setattr` module injection in `amelia/pipelines/implementation/state.py` and `cast()` calls on stream chunks in the orchestrator indicate working around LangGraph API limitations.
- Impact: LangGraph API changes could require significant refactoring across orchestrator, pipelines, and state modules.
- Migration plan: Isolate LangGraph interactions behind adapter interfaces. The `amelia/pipelines/` layer partially does this but the orchestrator reaches through the abstraction.

**Type Stubs for DeepAgents:**
- Risk: `stubs/deepagents/` contains hand-written type stubs for an external dependency. These must be manually kept in sync with the actual package.
- Impact: Type checking may pass while runtime behavior diverges if stubs become stale.
- Migration plan: Contribute type annotations upstream or use `py.typed` marker if available.

## Scaling Limits

**Single-Process Orchestrator:**
- Current capacity: One `OrchestratorService` instance manages all workflows in-memory via `_active_tasks` dict and `_planning_tasks` dict.
- Limit: Cannot scale horizontally. If the server process crashes, all in-flight workflow state is lost (only DB state persists).
- Scaling path: Persist task queues to the database. Use a distributed task runner (e.g., Celery, Dramatiq) or implement leader election for multi-instance deployment.

**SQLite/PostgreSQL Checkpoint Storage:**
- Current capacity: LangGraph checkpoints stored in the database grow with each workflow step.
- Limit: Long-running workflows with many tasks accumulate large JSONB checkpoint data. No automatic cleanup observed beyond the retention service.
- Scaling path: Implement checkpoint compaction or archival for completed workflows.

---

*Concerns audit: 2026-03-13*
