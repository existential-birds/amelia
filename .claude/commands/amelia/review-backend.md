---
description: perform comprehensive backend code review for Python/FastAPI/LangGraph projects using parallel agents
---

# Backend Code Review (Python/FastAPI/LangGraph)

You are performing a comprehensive backend code review for this branch/PR.

## Step 1: Detect Project Technologies

First, examine the project to understand what technologies are in use:

```bash
# Check pyproject.toml for dependencies
grep -E '(langgraph|pydantic-ai|fastapi|typer|httpx|aiosqlite)' pyproject.toml

# Detect FastAPI usage
find amelia -name "*.py" -exec grep -l "from fastapi\|import fastapi" {} \; | head -5

# Detect LangGraph usage
find amelia -name "*.py" -exec grep -l "StateGraph\|langgraph" {} \; | head -5

# Detect Pydantic-AI usage
find amelia -name "*.py" -exec grep -l "pydantic_ai\|Agent\(" {} \; | head -5
```

## Step 2: Load Relevant Skills

Based on detected technologies, load applicable skills from `.claude/skills/`:

```bash
# Find available backend skills
find .claude/skills -name "SKILL.md" | xargs grep -l -E "(langgraph|python|fastapi)" 2>/dev/null | head -10
```

Key skills to load:
- `langgraph-graphs` - StateGraph, nodes, edges, conditional routing
- `langgraph-persistence` - Checkpointing, human-in-loop, event streaming

## Step 3: Identify Changed Files

```bash
git diff --name-only $(git merge-base HEAD main)..HEAD | grep -E '\.py$'
```

## Step 4: Launch Parallel Review Agents

Launch specialized agents using `Task` tool with `subagent_type="superpowers:code-reviewer"`.

**Adapt agents based on detected technologies.** Only launch agents for areas with changed files.

### Core Agent: Python Quality (Always Run)

Review all changed `.py` files.

Check for:

**Type Safety:**
- Type hints on all function parameters and return types
- No `Any` unless absolutely necessary (with comment explaining why)
- `TypeVar` usage for generic functions
- Proper `Optional[T]` vs `T | None` (prefer `T | None` for Python 3.12+)
- `Literal` types for string enums where appropriate

**Async Patterns:**
- No blocking calls (`time.sleep`, sync HTTP) in async functions
- Proper `await` on all coroutines
- `asyncio.gather()` for concurrent independent operations
- No `asyncio.run()` inside async context
- `async with` for async context managers (httpx, aiosqlite)

**Error Handling:**
- `ValueError` with clear messages for validation failures
- No bare `except:` clauses
- Specific exception types caught, not `Exception`
- Error messages include context (what failed, expected vs actual)
- Re-raising with `from` to preserve stack trace

**Code Quality:**
- Google-style docstrings on public functions
- No `print()` statements (use `logger` from loguru)
- Constants in UPPER_SNAKE_CASE
- No mutable default arguments (`def foo(items=[])` is wrong)
- f-strings preferred over `.format()` or `%`

### Conditional Agent: FastAPI Routes

**Only if `amelia/server/routes/` files changed:**

Review files matching: `**/routes/*.py`, `**/server/main.py`, `**/dependencies.py`

Check for:

**Route Design:**
- `APIRouter` with proper `prefix` and `tags`
- Response models defined with `response_model=` parameter
- Proper HTTP methods (GET for reads, POST for creates, PUT/PATCH for updates, DELETE for deletes)
- Path parameters validated with `Path(...)` when constraints needed
- Query parameters with sensible defaults

**Dependency Injection:**
- Shared dependencies in `dependencies.py`
- `Depends()` for database sessions, auth, config
- No global state mutation in route handlers
- Proper cleanup with `yield` dependencies

**Error Handling:**
- `HTTPException` with appropriate status codes
- Custom exception handlers for domain exceptions
- Validation errors return 422 with details
- Not found returns 404, not 500

**Async Compliance:**
- All route handlers are `async def`
- No blocking I/O in route handlers
- Background tasks for long-running operations

**Security:**
- No secrets in response models
- Input validation on all user-provided data
- Rate limiting considerations for expensive operations

### Conditional Agent: LangGraph Orchestration

**Only if `amelia/core/` or orchestrator files changed:**

Review files matching: `**/core/orchestrator.py`, `**/core/state.py`, `**/agents/*.py`

Check for:

**State Schema:**
- State class inherits from `TypedDict` or uses Pydantic models
- Reducers defined for list fields that need append semantics
- No optional fields without defaults in state
- State fields are serializable (for checkpointing)

**Node Functions:**
- Signature: `def node_name(state: StateType) -> dict | StateType`
- Return only the fields being updated (partial state)
- No side effects that aren't idempotent (checkpointing replays)
- Clear single responsibility per node

**Graph Construction:**
- `StateGraph(StateType)` with explicit state schema
- `add_node()` before `add_edge()` referencing that node
- `add_conditional_edges()` with all possible return values mapped
- `START` and `END` from `langgraph.graph` used correctly
- `.compile()` called after all nodes/edges added

**Conditional Routing:**
- Router functions return `Literal` type with all possible values
- All return values have corresponding edge mappings
- No unreachable nodes (verify graph connectivity)

**Human-in-the-Loop:**
- `interrupt_before` or `interrupt_after` for approval points
- State includes fields for human input
- `Command(resume=...)` pattern for resuming after interrupt

**Checkpointing:**
- Checkpointer passed to `.compile(checkpointer=...)`
- `thread_id` in config for conversation continuity
- State is fully serializable (no lambdas, no open files)

**Error Recovery:**
- Nodes handle expected failures gracefully
- Retry logic where appropriate (API calls)
- Dead letter handling for unrecoverable errors

### Conditional Agent: Pydantic Models

**Only if files with Pydantic models changed:**

Review files matching: `**/models/*.py`, `**/core/types.py`, `**/core/state.py`

Check for:

**Model Design:**
- Inherit from `pydantic.BaseModel` (not dataclass for API models)
- `model_config` for settings (not `class Config`)
- Field descriptions with `Field(description="...")`
- Sensible defaults with `Field(default=...)`

**Validation:**
- `field_validator` for complex field validation
- `model_validator` for cross-field validation
- Validators return the validated value, not `None`
- `mode="before"` or `mode="after"` explicit in validators

**Serialization:**
- `model_dump()` not `.dict()` (Pydantic v2)
- `model_validate()` not `.parse_obj()` (Pydantic v2)
- Alias handling with `Field(alias="...")` when needed
- `exclude_unset=True` when partial updates needed

**Enums:**
- Use `StrEnum` for string enums (Python 3.11+)
- Enum values are lowercase with underscores
- `Literal` types for small fixed sets instead of full Enum

### Conditional Agent: Pydantic-AI Agents

**Only if agent files using pydantic-ai changed:**

Review files matching: `**/agents/*.py`

Check for:

**Agent Definition:**
- `Agent()` with explicit `model` parameter
- `system_prompt` defined (static or dynamic)
- `result_type` for structured outputs
- Dependencies properly typed with `RunContext`

**Tool Usage:**
- `@agent.tool` decorator for agent tools
- Tools have clear docstrings (used as tool descriptions)
- Tool parameters use Pydantic types
- Tools handle errors gracefully (don't crash agent)

**Structured Output:**
- Result types are Pydantic models
- Optional fields have defaults
- Complex outputs use nested models

### Conditional Agent: Test Quality

**Only if test files changed:**

Review files matching: `tests/**/*.py`

Check for:

**Async Testing:**
- No `@pytest.mark.asyncio` needed (asyncio_mode = "auto")
- `async def test_*` for async tests
- Proper `await` on async fixtures

**Fixtures:**
- Shared fixtures in `conftest.py`
- Fixture scope appropriate (function, module, session)
- `yield` fixtures clean up properly
- No fixture duplication across test files

**Mocking:**
- `unittest.mock.patch` or `pytest-mock`
- Mock at the boundary (external services, not internal functions)
- `AsyncMock` for async functions
- Mocks reset between tests

**Assertions:**
- One concept per test
- Descriptive test names (`test_create_workflow_returns_id`)
- `pytest.raises` for expected exceptions
- No `assert True` or `assert response` without checking content

**Test Independence:**
- Tests don't depend on execution order
- No shared mutable state between tests
- Database fixtures rolled back or isolated

## Step 5: Post-Fix Verification

**After fixes are applied**, run verification:

```bash
# Lint check
uv run ruff check amelia tests

# Type check
uv run mypy amelia

# Run tests
uv run pytest
```

All checks must pass before approval.

## Uncertainty Resolution

If uncertain about patterns:
- Use WebSearch for official documentation (LangGraph, FastAPI, Pydantic)
- Check existing patterns in the codebase
- Reference loaded skills from `.claude/skills/`

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

## Example Output

```
## Review Summary

Found 1 critical state schema issue and 2 major async pattern violations.

## Issues

### Critical (Blocking)

1. [amelia/core/state.py:45] Missing reducer for messages list field
   - Issue: `messages: list[AgentMessage]` has no reducer, will be overwritten not appended
   - Why: Concurrent node updates will lose messages, breaking conversation history
   - Fix: Add `messages: Annotated[list[AgentMessage], add_messages]` with reducer

### Major (Should Fix)

2. [amelia/server/routes/workflows.py:67] Blocking call in async route handler
   - Issue: `requests.get()` used instead of `httpx.AsyncClient`
   - Why: Blocks event loop, degrading server performance under load
   - Fix: Replace with `async with httpx.AsyncClient() as client: await client.get(...)`

3. [amelia/agents/architect.py:89] Bare exception clause
   - Issue: `except:` catches all exceptions including KeyboardInterrupt
   - Why: Makes debugging difficult, can mask real errors
   - Fix: Change to `except Exception as e:` and log the error

### Minor (Nice to Have)

4. [amelia/core/types.py:23] Missing field description
   - Issue: `Field()` without description on public API model
   - Why: OpenAPI docs will lack field documentation
   - Fix: Add `Field(description="...")`

## Good Patterns

- [amelia/core/orchestrator.py:34-56] Clean conditional routing with Literal types
- [amelia/server/dependencies.py:12] Proper yield dependency with cleanup

## Verdict

Ready: With fixes 1-3
Rationale: Critical state bug will cause data loss. Major async issue affects production performance.
```

## Critical Rules

**DO:**
- Detect technologies before assuming what to check
- Number every issue sequentially (1, 2, 3...)
- Include FILE:LINE for each issue
- Separate Issue/Why/Fix clearly
- Categorize by actual severity
- Load relevant skills before reviewing
- Run verification after fixes applied

**DON'T:**
- Assume Django/Flask patterns (this is FastAPI)
- Use tables (harder to parse)
- Skip numbering
- Give vague file references
- Mark style preferences as Critical
- Approve without running tests after fixes
- Ignore LangGraph-specific patterns in orchestrator code
