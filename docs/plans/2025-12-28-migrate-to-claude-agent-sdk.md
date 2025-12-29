# Migrate to Claude Agent SDK + DeepAgents

> **For Claude:** Use superpowers:executing-plans to implement this plan task-by-task.

---

## Library API Reference

### claude-agent-sdk

```python
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import Message, AssistantMessage, ResultMessage, TextBlock

# For generate(): iterate over query() results
async for message in query(prompt=prompt, options=options):
    if isinstance(message, AssistantMessage):
        # Extract text from message.content (list of TextBlock)
        pass
    elif isinstance(message, ResultMessage):
        session_id = message.session_id
        # message.result contains final text
        # message.structured_output contains parsed JSON if schema was provided

# Options
options = ClaudeAgentOptions(
    model="sonnet",
    cwd="/path/to/dir",
    permission_mode="default",  # or "bypassPermissions"
    system_prompt="...",
    resume=session_id,  # to resume session
)
```

### deepagents

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

# Create agent
model = init_chat_model("openrouter:anthropic/claude-sonnet-4-20250514")
backend = FilesystemBackend(root_dir="/path/to/dir")
agent = create_deep_agent(model=model, system_prompt="...", backend=backend)

# For generate(): use ainvoke
result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
final_message = result["messages"][-1]  # AIMessage

# For execute_agentic(): use astream
async for chunk in agent.astream({"messages": [HumanMessage(content=prompt)]}, stream_mode="values"):
    messages = chunk.get("messages", [])
    if messages:
        yield messages[-1]  # BaseMessage
```

---

## Execution Context

### Current PR Stack (as of 2025-12-28)

This migration builds on top of an existing PR stack that implements agentic-only execution:

```
main
 └── PR #148: ka/agentic-state-model ← targets main
      └── PR #149: ka/agentic-agents
           └── PR #150: ka/agentic-orchestrator
                └── PR #151: ka/agentic-dashboard-cleanup ← current branch
                     └── ka/sdk-migration (NEW) ← this plan creates only this PR
```

**Existing PRs in stack:**
- **PR #148** (`ka/agentic-state-model`): Adds `AgenticState` model
- **PR #149** (`ka/agentic-agents`): Rewrites agents for agentic execution
- **PR #150** (`ka/agentic-orchestrator`): Simplifies graph for agentic execution
- **PR #151** (`ka/agentic-dashboard-cleanup`): Removes structured execution UI

**To close:**
- **PR #146** (`feat/deepagents-driver`): Parallel monolithic implementation—superseded by this stacked approach

### Why a New PR on Top of the Stack?

1. **Separation of concerns**: Agentic refactoring (execution model) vs SDK migration (driver implementation) are distinct changes
2. **Unblock merging**: The stack can land without waiting for SDK integration verification
3. **Lower risk**: If `claude-agent-sdk` or `deepagents` have issues, it doesn't block agentic work
4. **Easier review**: Each PR can be evaluated independently

### Execution Instructions

```bash
# 1. Ensure you're on the top of the stack
git checkout ka/agentic-dashboard-cleanup
git pull origin ka/agentic-dashboard-cleanup

# 2. Create the new branch for SDK migration
git checkout -b ka/sdk-migration

# 3. Execute the phases below task-by-task

# 4. After completion, create PR targeting ka/agentic-dashboard-cleanup
gh pr create --base ka/agentic-dashboard-cleanup --title "refactor(drivers): migrate to Claude Agent SDK + DeepAgents"
```

### Prerequisites

Before starting:
- [ ] Verify the stack is up-to-date: `git log --oneline main..ka/agentic-dashboard-cleanup`
- [ ] Ensure all stack PRs pass CI
- [ ] Confirm `claude-agent-sdk` and `deepagents` packages are published on PyPI

---

## Goal

Replace custom driver implementations with official/production agent runtimes:
- CLI driver → Claude Agent SDK (wraps Claude Code)
- API driver → DeepAgents (LangGraph-based autonomous agent)

**Key decisions:**
- `DriverInterface` only has `generate(prompt, system_prompt, schema, **kwargs)`
- `execute_agentic()` is NOT in the protocol - each driver has its own typed method
- Agents build prompts directly (no context compilation layer)

---

## Phase 1: Dependencies

### Task 1.1: Update dependencies

**File:** `pyproject.toml`

**Changes:**
1. Remove `pydantic-ai` from dependencies
2. Add `claude-agent-sdk>=0.1.0`
3. Add `deepagents>=0.3.1`

**Verify:** `uv sync && uv run python -c "from claude_agent_sdk import query; from deepagents import create_deep_agent; print('OK')"`

**Commit:** `chore: replace pydantic-ai with claude-agent-sdk and deepagents`

---

## Phase 2: Driver Interface

### Task 2.1: Simplify DriverInterface

**File:** `amelia/drivers/base.py`

**Changes:**
1. Remove `messages` parameter from `generate()`
2. New signature: `generate(prompt: str, system_prompt: str | None, schema: type[BaseModel] | None, **kwargs) -> GenerateResult`
3. Update docstring to explain `execute_agentic` is intentionally NOT in protocol

**Commit:** `refactor(drivers): simplify DriverInterface to prompt-based API`

---

## Phase 3: CLI Driver

### Task 3.1: Rewrite ClaudeCliDriver with SDK

**File:** `amelia/drivers/cli/claude.py`

**Changes:**
1. Replace subprocess-based implementation with `claude-agent-sdk`
2. Use `query()` for `generate()` method
3. Use `ClaudeSDKClient` for `execute_agentic()` method
4. `execute_agentic()` yields `claude_agent_sdk.types.Message`

**Verify:** `uv run ruff check amelia/drivers/cli/claude.py && uv run mypy amelia/drivers/cli/claude.py`

**Commit:** `refactor(drivers): replace ClaudeCliDriver with SDK implementation`

### Task 3.2: Clean up CLI driver module

**Files:** `amelia/drivers/cli/`

**Changes:**
1. Delete `base.py` if unused (check with `grep -r "from amelia.drivers.cli.base" amelia/`)
2. Update `__init__.py` to only export `ClaudeCliDriver`

**Commit:** `refactor(drivers): clean up obsolete CLI driver code`

---

## Phase 4: API Driver

### Task 4.1: Replace ApiDriver with DeepAgents

**Files:** `amelia/drivers/api/`

**Changes:**
1. Delete `openai.py`, `events.py`, `tools.py`
2. Create `deepagents.py` with new `ApiDriver` class
3. Use `create_deep_agent()` with `FilesystemBackend`
4. `execute_agentic()` yields `langchain_core.messages.BaseMessage`
5. Update `__init__.py` to export from `deepagents.py`

**Verify:** `uv run ruff check amelia/drivers/api/ && uv run mypy amelia/drivers/api/`

**Commit:** `refactor(drivers): replace pydantic-ai ApiDriver with DeepAgents`

---

## Phase 5: Update Agents

### Task 5.1: Update Architect

**File:** `amelia/agents/architect.py`

**Changes:**
1. Delete `ArchitectContextStrategy` class
2. Remove imports from `amelia/core/context`
3. Move `SYSTEM_PROMPT` to class constant
4. Add `_build_prompt(state, profile) -> str` method
5. Update `plan()` to use new driver interface

**Commit:** `refactor(agents): update Architect to build prompts directly`

### Task 5.2: Update Developer

**File:** `amelia/agents/developer.py`

**Changes:**
1. Remove context strategy usage
2. Add `_build_prompt(state, profile) -> str` method
3. Use `isinstance()` to check driver type before calling `execute_agentic()`
4. Handle `claude_agent_sdk.types.Message` for CLI driver
5. Handle `langchain_core.messages.BaseMessage` for API driver

**Commit:** `refactor(agents): update Developer to use simplified driver interface`

### Task 5.3: Update Reviewer

**File:** `amelia/agents/reviewer.py`

**Changes:**
1. Delete `ReviewerContextStrategy` class
2. Remove imports from `amelia/core/context`
3. Move `SYSTEM_PROMPT` to class constant
4. Add `_build_prompt(state, profile) -> str` method
5. Update `review()` to use new driver interface

**Commit:** `refactor(agents): update Reviewer to build prompts directly`

---

## Phase 6: Delete Obsolete Code

### Task 6.1: Remove AgentMessage

**File:** `amelia/core/state.py`

**Changes:**
1. Check usage: `grep -r "AgentMessage" amelia/`
2. If unused, delete `AgentMessage` class

**Commit:** `refactor(core): remove unused AgentMessage class`

### Task 6.2: Delete context compilation layer

**File:** `amelia/core/context.py`

**Changes:**
1. Delete entire file
2. Update `amelia/core/__init__.py` to remove exports
3. Verify: `grep -r "from amelia.core.context" amelia/` returns nothing

**Commit:** `refactor(core): delete context compilation layer`

---

## Phase 7: Update Tests

### Task 7.1: Update CLI driver tests

**File:** `tests/unit/test_claude_driver.py`

**Changes:**
1. Mock `claude_agent_sdk.query` and `ClaudeSDKClient`
2. Expect SDK message types in assertions

**Commit:** `test(drivers): update CLI driver tests for SDK implementation`

### Task 7.2: Update API driver tests

**Files:** `tests/unit/test_api_driver_*.py`

**Changes:**
1. Mock `deepagents.create_deep_agent`
2. Expect LangChain message types in assertions

**Commit:** `test(drivers): update API driver tests for DeepAgents implementation`

### Task 7.3: Delete context tests, update agent tests

**Changes:**
1. Delete `tests/unit/agents/test_architect_context.py`
2. Delete `tests/unit/agents/test_reviewer_context.py`
3. Update `tests/unit/core/test_developer_node.py` for new interface

**Commit:** `test(agents): delete context tests, update for simplified interface`

### Task 7.4: Remove obsolete test files

**Changes:**
1. Delete `tests/unit/drivers/cli/test_claude_convert.py`
2. Delete `tests/unit/test_api_tools.py`
3. Clean `tests/conftest.py` - remove unused fixtures

**Commit:** `test: remove obsolete tests and fixtures`

---

## Phase 8: Final Verification

### Task 8.1: Run all checks

```bash
uv run ruff check amelia tests
uv run mypy amelia
uv run pytest
uv run python scripts/check_boundaries.py
```

**Commit (if fixes needed):** `fix: address issues from driver migration`

---

## Summary

| Phase | What |
|-------|------|
| 1 | Replace pydantic-ai with claude-agent-sdk + deepagents |
| 2 | Simplify DriverInterface to `generate(prompt, system_prompt, ...)` |
| 3 | CLI driver → Claude Agent SDK |
| 4 | API driver → DeepAgents |
| 5 | Agents build prompts directly (delete context strategies) |
| 6 | Delete AgentMessage, context.py |
| 7 | Update tests |
| 8 | Final verification |

**Deleted:**
- `amelia/core/context.py`
- `amelia/drivers/api/openai.py`, `events.py`, `tools.py`
- `amelia/drivers/cli/base.py`
- `ArchitectContextStrategy`, `ReviewerContextStrategy`
- `AgentMessage`, `ContextSection`, `CompiledContext`, `ContextStrategy`

---

## Post-Execution

### After SDK Migration PR is Created

1. **Close PR #146** (`feat/deepagents-driver`): The stacked approach supersedes the monolithic PR
   ```bash
   gh pr close 146 --comment "Superseded by stacked PRs: #148 → #149 → #150 → #151 → ka/sdk-migration"
   ```

2. **Update PR descriptions**: Each stacked PR should reference the overall migration goal

3. **Merge order**: Land existing stacked PRs in order, then the new SDK migration PR:
   - PR #148 (`ka/agentic-state-model`) → merge to `main`
   - PR #149 (`ka/agentic-agents`) → merge to `main`
   - PR #150 (`ka/agentic-orchestrator`) → merge to `main`
   - PR #151 (`ka/agentic-dashboard-cleanup`) → merge to `main`
   - SDK migration PR (`ka/sdk-migration`) → merge to `main` ← **this plan adds only this PR**

### Delete Plan File After Merge

Once the SDK migration PR is merged, delete this plan file:
```bash
git rm docs/plans/2025-12-28-migrate-to-claude-agent-sdk.md
git commit -m "docs: remove completed migration plan"
```
