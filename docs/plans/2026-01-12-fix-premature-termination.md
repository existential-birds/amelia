# Fix DeepAgents Premature Termination

## Problem Statement

The API driver's architect agent terminates prematurely without writing the plan file. Evidence:
- Agent does exploration (read_file, ls, glob)
- Calls `write_todos` with in_progress tasks
- Stops without calling `write_file`
- Warnings show: "Agent terminated with in_progress tasks"

## Root Cause (from research)

**PRIMARY**: `recursion_limit` is not configured - defaults to 1000 steps in DeepAgents/LangGraph. When the agent does extensive exploration, it exceeds this limit silently.

**SECONDARY**: System prompt lacks explicit continuation guidance for weaker models like GLM-4.

## Implementation Plan

### Task 1: Add recursion_limit configuration to ApiDriver

**Files:**
- Modify: `amelia/drivers/api/deepagents.py`

**Step 1: Add recursion_limit parameter to execute_agentic**

```python
async def execute_agentic(
    self,
    prompt: str,
    cwd: str,
    instructions: str | None = None,
    *,
    recursion_limit: int = 5000,  # Add parameter, default 5000
) -> AsyncIterator[AgenticMessage]:
```

**Step 2: Pass recursion_limit to agent.astream config**

```python
async for chunk in agent.astream(
    {"messages": [HumanMessage(content=prompt)]},
    config={"recursion_limit": recursion_limit},  # Add this
    stream_mode="values",
):
```

**Step 3: Add step counter for debugging**

```python
step_count = 0
async for chunk in agent.astream(...):
    step_count += 1
    if step_count % 100 == 0:
        logger.debug("Agent execution progress", step=step_count)
```

---

### Task 2: Add checkpointing for auto-resumption

**Files:**
- Modify: `amelia/drivers/api/deepagents.py`

**Step 1: Add checkpointer to create_deep_agent**

```python
from langgraph.checkpoint.memory import MemorySaver

# In execute_agentic:
checkpointer = MemorySaver()  # In-memory for now
agent = create_deep_agent(
    model=chat_model,
    system_prompt=instructions or "",
    backend=backend,
    checkpointer=checkpointer,  # Add this
)
```

**Step 2: Generate thread_id for resumption**

```python
import uuid
thread_id = str(uuid.uuid4())
config = {
    "recursion_limit": recursion_limit,
    "configurable": {"thread_id": thread_id},
}
```

**Step 3: Detect incomplete execution and auto-resume**

```python
# After main loop completes
state = agent.get_state(config)
if state.next and self._is_incomplete(state):
    logger.warning("Agent incomplete, auto-resuming...")
    async for chunk in agent.astream(
        {"messages": []},  # Empty = resume
        config=config,
        stream_mode="values",
    ):
        # yield messages as before
```

**Step 4: Add incompleteness detection helper**

```python
def _is_incomplete(self, state) -> bool:
    """Check if agent stopped mid-execution."""
    if not state.values.get("messages"):
        return False
    last_msg = state.values["messages"][-1]
    # Incomplete if last message isn't a final AI response
    return getattr(last_msg, "type", None) != "ai" or hasattr(last_msg, "tool_calls")
```

---

### Task 3: Enhance system prompt for continuation

**Files:**
- Modify: `amelia/agents/architect.py`

**Step 1: Add continuation guidance to SYSTEM_PROMPT_PLAN**

```python
SYSTEM_PROMPT_PLAN = """You are a senior software architect creating implementation plans.

## Your Role
Write comprehensive implementation plans assuming the executor has ZERO context...

## CRITICAL: Task Completion
- You MUST complete ALL tasks before stopping
- If you create todos with write_todos, execute EVERY task
- If a task is in_progress, continue working on it immediately
- Before stopping, verify: Have I created the plan file?
- NEVER stop with incomplete work

## Exploration Goals
...
"""
```

---

### Task 4: Add max_retries for resumption

**Files:**
- Modify: `amelia/drivers/api/deepagents.py`

**Step 1: Add retry loop with limit**

```python
async def execute_agentic(
    self,
    prompt: str,
    cwd: str,
    instructions: str | None = None,
    *,
    recursion_limit: int = 5000,
    max_resume_retries: int = 3,  # Add parameter
) -> AsyncIterator[AgenticMessage]:
    # ... setup ...

    resume_count = 0
    while True:
        async for chunk in agent.astream(...):
            # yield messages

        # Check if complete
        state = agent.get_state(config)
        if not self._is_incomplete(state):
            break  # Done

        resume_count += 1
        if resume_count >= max_resume_retries:
            logger.error("Max resume retries exceeded", retries=resume_count)
            break

        logger.warning("Auto-resuming agent", attempt=resume_count)
        # Loop continues with empty messages to resume
```

---

### Task 5: Update Profile to allow recursion_limit config

**Files:**
- Modify: `amelia/core/types.py`

**Step 1: Add recursion_limit to Profile**

```python
class Profile(BaseModel):
    # ... existing fields ...
    recursion_limit: int = Field(default=5000, description="Max agent execution steps")
```

**Step 2: Pass to driver in orchestrator**

```python
# In call_architect_node:
async for state, event in architect.plan(
    state,
    profile,
    workflow_id=workflow_id,
    recursion_limit=profile.recursion_limit,  # Pass through
):
```

---

### Task 6: Add tests

**Files:**
- Create: `tests/unit/drivers/test_api_driver_resumption.py`

**Tests to add:**
1. `test_execute_agentic_passes_recursion_limit`
2. `test_auto_resume_on_incomplete_execution`
3. `test_max_resume_retries_respected`
4. `test_complete_execution_no_resume`

---

## Execution Order

1. **Task 1** - Add recursion_limit (quick win, immediate improvement)
2. **Task 3** - Enhance system prompt (no code risk)
3. **Task 2** - Add checkpointing (enables resumption)
4. **Task 4** - Add retry loop (uses checkpointing)
5. **Task 5** - Make configurable (polish)
6. **Task 6** - Add tests (verification)

## Expected Outcome

After implementation:
- Agent will have 5000 steps (5x current) before hitting limit
- If agent stops with incomplete tasks, it auto-resumes up to 3 times
- System prompt explicitly tells agent to complete all work
- Logs will show step progress and resume attempts

## Risks

- **MemorySaver is ephemeral** - If process crashes, state is lost. Can upgrade to SQLite later.
- **Retry loop could hang** - Max retries prevents infinite loops.
- **Increased latency** - Resumption adds overhead, but correctness > speed.
