---
description: perform comprehensive backend code review for Python/FastAPI/LangGraph projects using parallel agents
---

# Backend Code Review (Python/FastAPI/LangGraph)

You are performing a comprehensive backend code review for this branch/PR.

## Step 1: Load Skills Based on Technologies

First, detect what technologies are in the changed files and load the relevant skills:

```bash
# Get changed Python files
git diff --name-only $(git merge-base HEAD main)..HEAD | grep -E '\.py$'

# Check for LangGraph usage
git diff $(git merge-base HEAD main)..HEAD -- '*.py' | grep -E 'StateGraph|langgraph|add_messages'

# Check for Pydantic-AI usage
git diff $(git merge-base HEAD main)..HEAD -- '*.py' | grep -E 'pydantic_ai|@agent\.tool|RunContext'
```

**Load skills using the Skill tool based on detected technologies:**

| If you see... | Load skill |
|---------------|------------|
| `StateGraph`, `langgraph`, `add_edge`, `Command` | `langgraph-code-review` |
| `pydantic_ai`, `Agent(`, `@agent.tool` | `pydantic-ai-common-pitfalls` |
| `RunContext`, `deps_type` | `pydantic-ai-dependency-injection` |
| `@agent.tool`, tool definitions | `pydantic-ai-tool-system` |
| `TestModel`, `FunctionModel` | `pydantic-ai-testing` |

## Step 2: Identify Changed Files

```bash
git diff --name-only $(git merge-base HEAD main)..HEAD | grep -E '\.py$'
```

Categorize changes:
- **Core/Orchestrator**: `amelia/core/`, `**/orchestrator.py`, `**/state.py`
- **Agents**: `amelia/agents/`
- **Server/Routes**: `amelia/server/`
- **Tests**: `tests/`

## Step 3: Launch Parallel Review Agents

Launch specialized agents using `Task` tool with `subagent_type="superpowers:code-reviewer"`.

**Only launch agents for categories with changed files.**

### Agent 1: Python Quality (Always Run)

Review all changed `.py` files for general Python quality:

**Type Safety:**
- Type hints on all function parameters and return types
- No `Any` unless necessary (with comment explaining why)
- Proper `T | None` syntax (Python 3.12+)
- `Literal` types for string enums

**Async Patterns:**
- No blocking calls (`time.sleep`, `requests`) in async functions
- Proper `await` on all coroutines
- `asyncio.gather()` for concurrent independent operations
- `async with` for async context managers (httpx, aiosqlite)

**Error Handling:**
- `ValueError` with clear messages for validation failures
- No bare `except:` clauses
- Specific exception types, not `Exception`
- Re-raising with `from` to preserve stack trace

**Database & Queries:**
- Query parameters validated (LIMIT < 0 raises or returns early; LIMIT 0 is valid for empty results)
- No SQLite quirks exploitable (e.g., LIMIT -1 = no limit in SQLite)
- Connection/session cleanup in error paths

**Code Quality:**
- Google-style docstrings on public functions
- No `print()` statements (use `logger` from loguru)
- No mutable default arguments
- f-strings preferred

**Observability:**
- Critical paths have `logger.debug()` for diagnostics (broadcast counts, target counts)
- Key operations have `logger.info()` for operational visibility
- Errors include context (IDs, counts) not just messages

### Agent 2: LangGraph Review (If core/orchestrator changed)

**IMPORTANT: Read the `langgraph-code-review` skill first using the Skill tool.**

The skill contains a comprehensive checklist for LangGraph code. Key areas:
- State mutation vs return patterns
- Missing reducers for list fields
- Conditional edge return types
- Checkpointer requirements for interrupts
- Thread ID with checkpointers

### Agent 3: Pydantic-AI Review (If agents/ changed)

**IMPORTANT: Read the `pydantic-ai-common-pitfalls` skill first using the Skill tool.**

Additional checks:
- `Agent()` with explicit `model` parameter
- `system_prompt` defined (static or dynamic)
- `result_type` for structured outputs
- Tools have clear docstrings (used as tool descriptions)
- Tool parameters use Pydantic types

### Agent 4: FastAPI Review (If server/routes changed)

**Route Design:**
- `APIRouter` with proper `prefix` and `tags`
- Response models with `response_model=`
- Proper HTTP methods (GET reads, POST creates, etc.)

**Dependency Injection:**
- Shared dependencies in `dependencies.py`
- `Depends()` for database sessions, auth, config
- Proper cleanup with `yield` dependencies

**Error Handling:**
- `HTTPException` with appropriate status codes
- Validation errors return 422

**Async Compliance:**
- All route handlers are `async def`
- No blocking I/O in route handlers

### Agent 5: Test Quality (If tests/ changed)

**Async Testing:**
- No `@pytest.mark.asyncio` needed (asyncio_mode = "auto")
- `async def test_*` for async tests

**Fixtures:**
- Shared fixtures in `conftest.py`
- Small fixture duplication (≤3 instances, ~3 lines) is acceptable; centralize when duplication exceeds threshold or logic is non-trivial
- Factory fixtures (`make_foo()`) for variations, not static fixtures

**Assertions:**
- One concept per test
- Descriptive test names
- `pytest.raises` for expected exceptions
- Assertions are precise (avoid `>=` or `>` when exact count is known)

**DRY Patterns:**
- Repetitive tests use `@pytest.mark.parametrize` instead of copy-paste
- Use `AsyncMock` built-in tracking (`.await_count`, `.call_args`) instead of manual counters
- Small setup duplication (≤3 instances, ~3 lines) is acceptable; extract to fixtures when duplication exceeds threshold or logic is non-trivial

## Step 4: Post-Fix Verification

**After fixes are applied**, run verification:

```bash
uv run ruff check amelia tests
uv run mypy amelia
uv run pytest
```

All checks must pass before approval.

## Output Format

Output MUST be structured as numbered items for use with `/amelia:eval-feedback`.

```
## Review Summary

[1-2 sentence overview of findings]

## Issues

### Critical (Blocking)

1. [FILE:LINE] ISSUE_TITLE
   - Issue: Description of what's wrong
   - Why: Why this matters (bug, type safety, data loss, security)
   - Fix: Specific recommended fix

### Major (Should Fix)

2. [FILE:LINE] ISSUE_TITLE
   - Issue: ...
   - Why: ...
   - Fix: ...

### Minor (Nice to Have)

N. [FILE:LINE] ISSUE_TITLE
   - Issue: ...
   - Why: ...
   - Fix: ...

## Good Patterns

- [FILE:LINE] Pattern description (preserve this)

## Verdict

Ready: Yes | No | With fixes 1-N
Rationale: [1-2 sentences]
```

## Critical Rules

**DO:**
- Load relevant skills BEFORE reviewing (langgraph-code-review, pydantic-ai-*)
- Number every issue sequentially (1, 2, 3...)
- Include FILE:LINE for each issue
- Separate Issue/Why/Fix clearly
- Categorize by actual severity
- Run verification after fixes applied

**DON'T:**
- Skip loading skills - they contain critical patterns
- Assume Django/Flask patterns (this is FastAPI)
- Mark style preferences as Critical
- Approve without running tests after fixes
