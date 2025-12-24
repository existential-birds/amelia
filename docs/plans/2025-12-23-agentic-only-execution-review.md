# Plan Review: Agentic-Only Execution

> **To apply fixes:** Open new session, run:
> `Read this file, then apply the suggested fixes to docs/plans/2025-12-23-agentic-only-execution.md`

**Reviewed:** 2025-12-23
**Verdict:** Yes - all fixes applied

---

**Plan:** `docs/plans/2025-12-23-agentic-only-execution.md`
**Tech Stack:** Python 3.12+, Pydantic, LangGraph, DeepAgents, asyncio, pytest

## Summary Table

| Criterion | Status | Notes |
|-----------|--------|-------|
| Parallelization | ✅ GOOD | Well-structured DAG, 2-3 agents optimal |
| TDD Adherence | ⚠️ ISSUES | Good for core batches (1-3, 5); missing for 4, 6, 7 |
| Type/API Match | ✅ GOOD | Plan describes changes to make, not current state |
| Library Practices | ⚠️ ISSUES | DeepAgents import paths speculative; model string outdated |
| Security/Edge Cases | ⚠️ ISSUES | Input validation gaps; security model is sound |

---

## Issues Found

### Critical (Must Fix Before Execution)

1. **[Batch 3] VAL-001: Missing `cwd` Path Validation**
   - Issue: No validation for `cwd` parameter - allows path traversal
   - Why: Attacker could specify `cwd="../../etc"` to escape containment
   - Fix: Add Pydantic validator to Profile model
   - Suggested edit for `amelia/core/types.py`:
   ```python
   from pathlib import Path

   class Profile(BaseModel):
       # ... existing fields ...

       @field_validator("working_dir")
       @classmethod
       def validate_working_dir(cls, v: str | None) -> str | None:
           if v is None:
               return v
           path = Path(v)
           if not path.is_absolute():
               raise ValueError("working_dir must be an absolute path")
           if ".." in str(path):
               raise ValueError("working_dir cannot contain '..'")
           return str(path.resolve())
   ```

2. **[Batch 13] MIG-001: Database Migration Race Condition**
   - Issue: No check if Amelia is running; backup/delete not atomic
   - Why: Concurrent writes could corrupt database or cause data loss
   - Fix: Add process check and atomic transaction
   - Suggested edit:
   ```bash
   # Step 13.1: Check not running
   if pgrep -f "amelia dev" > /dev/null; then
       echo "ERROR: Stop Amelia first: pkill -f 'amelia dev'"
       exit 1
   fi

   # Step 13.3: Atomic backup and delete
   sqlite3 ~/.amelia/checkpoint.db <<'SQL'
   BEGIN EXCLUSIVE;
   .backup ~/.amelia/checkpoint.db.backup
   DELETE FROM checkpoints;
   COMMIT;
   SQL
   ```

---

### Major (Should Fix)

3. **[Batch 3] API-001: Anthropic Model String Format Outdated**
   - Issue: Uses `claude-sonnet-4-20250514` but correct format is `claude-sonnet-4-5-YYYYMMDD`
   - Why: Model will fail to initialize with incorrect identifier
   - Fix: Update model string in driver
   - Suggested edit (line 295):
   ```python
   # Change from:
   model: str = "anthropic:claude-sonnet-4-20250514"

   # To:
   model: str = "anthropic:claude-sonnet-4-5-20250929"
   ```

4. **[Batch 3] ERR-001: Timeout Variable Undefined**
   - Issue: `_execute_batch` uses `self.timeout` but it's not stored in `__init__`
   - Why: Runtime error when timeout occurs
   - Fix: Store timeout parameter
   - Suggested edit (line 299-313):
   ```python
   def __init__(
       self,
       model: str = "anthropic:claude-sonnet-4-5-20250929",
       sandbox_provider: str | None = None,
       sandbox_config: dict[str, Any] | None = None,
       timeout: int = 600,
   ):
       self.model_id = model
       self.sandbox_provider = sandbox_provider
       self.sandbox_config = sandbox_config or {}
       self.timeout = timeout  # ADD THIS LINE
   ```

5. **[Batch 3] SEC-002: Session ID Not Sanitized**
   - Issue: `session_id` passed directly as `thread_id` without validation
   - Why: Could enable directory traversal if used in file paths
   - Fix: Add sanitization function
   - Suggested edit (add after line 407):
   ```python
   import re

   def _sanitize_session_id(self, session_id: str | None) -> str:
       if session_id is None:
           return "default"
       if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
           raise ValueError(f"Invalid session_id format: {session_id}")
       return session_id

   # Usage:
   config = {"configurable": {"thread_id": self._sanitize_session_id(session_id)}}
   ```

6. **[Batch 5] TEST-001: Test Fixtures Duplicate conftest.py**
   - Issue: Tests create new `mock_issue`, `mock_profile`, `mock_state` fixtures
   - Why: Violates DRY principle; conftest.py already has factories
   - Fix: Use existing factories from conftest.py
   - Suggested edit (Step 5.0, lines 546-559):
   ```python
   # Remove duplicate fixtures, use existing:
   from tests.conftest import mock_issue_factory, mock_profile_factory

   @pytest.fixture
   def mock_state(mock_issue_factory):
       return ExecutionState(issue=mock_issue_factory())
   ```

7. **[Batch 6] SEC-003: ClaudeCliDriver Still Uses --dangerously-skip-permissions**
   - Issue: Current code (line 611) uses `--dangerously-skip-permissions` by default
   - Why: Bypasses Claude Code's security; plan claims to rely on this security
   - Fix: Remove flag entirely and document requirement for user approval
   - Suggested edit: In Step 6.1, be explicit:
   ```markdown
   - **Action:** Remove `--dangerously-skip-permissions` flag from cmd_args list
   - **Action:** Remove `skip_permissions` parameter from `__init__`
   - **Action:** Update docstring to note: "Users must approve actions via Claude Code UI"
   ```

8. **[Batches 4,6,7] TDD-001: Missing Tests for Prompt/Driver Changes**
    - Issue: Batches 4, 6, 7 have no tests - only type checking
    - Why: Behavioral changes without tests can introduce subtle bugs
    - Fix: Add behavioral tests for each batch
    - Suggested edit - Add to Batch 4:
    ```markdown
    ### Step 4.0: Write RED tests
    - **File:** `tests/unit/agents/test_architect.py`
    - **Action:** Add tests verifying prompt changes produce simplified PlanStep
    ```

---

### Minor (Nice to Have)

9. **[Batch 3] LOG-001: Event Mapping Swallows Errors Silently**
    - Issue: Malformed events logged as warning, then `None` returned
    - Fix: Add error count tracking and circuit breaker

10. **[Batch 3] DOC-001: Missing `instructions` Length Validation**
    - Issue: No limit on instructions parameter length
    - Fix: Add `MAX_INSTRUCTION_LENGTH = 10000` validation

11. **[Batch 11] DEP-001: Deprecated Driver Still Usable**
    - Issue: `DeprecationWarning` easily ignored by users
    - Fix: Use `SecurityWarning` and add config to block deprecated drivers

---

## Parallelization Recommendations

The plan is well-structured for parallel execution:

**Optimal: 2-3 agents**

```
Phase 1 (Parallel: 3 agents):
  - Batch 0: Add DeepAgents dependency
  - Batch 1: Simplify PlanStep model
  - Batch 2: Remove ExecutionMode

Phase 2a (Sequential):
  - Batch 3: Create DeepAgentsDriver (depends on Batch 0)

Phase 2b (Parallel: 3 agents after Batch 3):
  - Batch 4: Update Architect (depends on Batch 1)
  - Batch 5: Simplify Developer (depends on 1, 2, 3)
  - Batch 6: Simplify Claude CLI (independent)

Phase 2c (Sequential):
  - Batch 7: Update Orchestrator (depends on Batch 2)

Phase 3 (Parallel: 2 agents after Phase 2):
  - Batch 8: Test fixtures → Batch 9: Unit tests
  - Batch 10: Integration tests (after Batch 8)

Phase 4 (Sequential):
  - Batch 11: Cleanup → Batch 12: Validation → Batch 13: Migration
```

**Critical Path:** 0 → 3 → 5 → 8 → 10 → 12 → 13 (7 batches)

---

## Verdict

**Ready to execute?** Yes, with fixes (1-8)

**Reasoning:** The plan's security model is sound - DeepAgents is a production-grade library with clear separation between FilesystemBackend (file ops) and SandboxBackend (command execution). The plan author correctly leverages this distinction.

**Before execution:**
1. Fix Critical issues #1-2 (input validation, migration safety)
2. Fix Major issues #3-8 (model string, timeout bug, session sanitization, test hygiene)

**During execution:**
- Step 0.2 already verifies DeepAgents imports work correctly
- The plan acknowledges API paths are "speculative" and includes verification

---

## Next Steps

**Review saved to:** `docs/plans/2025-12-23-agentic-only-execution-review.md`

**Recommended approach:**

1. **Apply fixes #1-8** to the plan file
2. **Execute with parallel strategy** (2-3 agents, phases as described above)
3. **Minor issues #9-11** can be addressed during implementation

Proceed with applying fixes?
