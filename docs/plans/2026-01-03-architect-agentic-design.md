# Architect Agentic Execution Design

**Goal:** Switch the Architect agent from `driver.generate()` to `execute_agentic()`, enabling real-time streaming and codebase exploration.

**Architecture:** The Architect becomes an async generator like the Developer, yielding `(state, StreamEvent)` tuples during execution. It explores the codebase with read-only tools before producing a reference-based implementation plan.

**Key Files:**
- `amelia/core/state.py` - Add `raw_architect_output` field
- `amelia/agents/architect.py` - Convert to async generator, new system prompt
- `amelia/core/orchestrator.py` - Update node to consume generator

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Codebase context | Pure exploration (remove `_scan_codebase()`) | Agent discovers relevant files via tools |
| Read-only enforcement | System prompt guidance | Simple, no driver changes needed |
| Output format | Raw markdown, validator in #199 | Clean separation of concerns |
| Plan persistence | Save after execution completes | Maintains current behavior |
| Streaming pattern | Async generator like Developer | Consistent agent handling |
| System prompt style | Goal-oriented exploration guidance | Adaptable to issue complexity |
| Plan content | References over code examples | Optimized for Claude Code executor (beagle#8) |

---

## State Changes

```python
# amelia/core/state.py
class ExecutionState(BaseModel):
    # ... existing fields ...
    raw_architect_output: str | None = None  # NEW
```

Existing fields (`goal`, `plan_markdown`, `plan_path`) remain for backward compatibility. Temporary extraction in #200, proper parsing in #199.

---

## Architect Agent Changes

### Method Signature

```python
async def plan(
    self,
    state: ExecutionState,
    profile: Profile,
    output_dir: str | None = None,
    *,
    workflow_id: str,
) -> AsyncIterator[tuple[ExecutionState, StreamEvent]]:
```

### Core Execution Loop

```python
raw_output = ""
tool_calls: list[ToolCall] = []
tool_results: list[ToolResult] = []

async for message in self.driver.execute_agentic(
    prompt=user_prompt,
    cwd=profile.working_dir,
    instructions=self.plan_prompt,
):
    event = message.to_stream_event(agent="architect", workflow_id=workflow_id)

    if message.type == AgenticMessageType.TOOL_CALL:
        tool_calls.append(ToolCall(...))
    elif message.type == AgenticMessageType.TOOL_RESULT:
        tool_results.append(ToolResult(...))
    elif message.type == AgenticMessageType.RESULT:
        raw_output = message.content or ""

    current_state = state.model_copy(update={
        "tool_calls": tool_calls,
        "tool_results": tool_results,
    })
    yield current_state, event

# After loop: save markdown and yield final state
```

### Removals

- `_scan_codebase()` method
- `MarkdownPlanOutput` schema parameter (raw output instead)

---

## System Prompt

```
You are a senior software architect creating implementation plans.

## Your Role
Create implementation plans optimized for Claude Code execution. The executor:
- Has full codebase access and can read any file
- Generates code dynamically from understanding
- Doesn't copy-paste from plans

You have read-only access to explore the codebase before planning.

## Exploration Goals
Before planning, discover:
- Existing patterns for similar features
- File structure and naming conventions
- Test patterns and coverage approach
- Dependencies and integration points

## Plan Structure

# [Feature] Implementation Plan

**Goal:** [One sentence]
**Architecture:** [2-3 sentences on approach]
**Key Files:** [Files to create/modify with brief description]

### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py` (the `function_name` function)
- Test: `tests/path/to/test.py`

**Intent:** [What this accomplishes]

**Approach:**
- Follow pattern in `src/similar/feature.py:45-60`
- Interface: `async def function(arg: Type) -> ReturnType`
- Must handle: [edge cases]
- Must NOT: [constraints]

**Test Criteria:**
- Verify [behavior]

## What to Include
- Intent and constraints (what to build, what to avoid)
- File references: "Follow pattern in `file.py:L45-60`"
- Interface signatures (types, function signatures)
- Test criteria and edge cases
- Task dependencies and ordering

## What NOT to Include
- Full code implementations (executor generates these)
- Duplicated file contents (use references)
- Code examples the executor will regenerate anyway

## Constraints
- DO NOT modify any files - exploration only
- DO NOT run tests, builds, or commands
- Focus on understanding before planning
```

---

## Orchestrator Node Changes

```python
async def call_architect_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    stream_emitter, workflow_id, profile, repository, prompts = (
        _extract_config_params(config)
    )

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    architect = Architect(driver, prompts=prompts)

    final_state = state
    async for new_state, event in architect.plan(
        state, profile, workflow_id=workflow_id
    ):
        final_state = new_state
        if stream_emitter:
            await stream_emitter(event)

    await _save_token_usage(driver, workflow_id, "architect", repository)

    # Temporary until #199 validator
    goal = _extract_goal_from_markdown(final_state.raw_architect_output)

    return {
        "raw_architect_output": final_state.raw_architect_output,
        "goal": goal,
        "plan_markdown": final_state.raw_architect_output,
        "plan_path": final_state.plan_path,
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
    }

def _extract_goal_from_markdown(markdown: str | None) -> str | None:
    """Temporary: Extract goal from plan markdown. Remove in #199."""
    if not markdown:
        return None
    for line in markdown.split("\n"):
        if line.strip().startswith("**Goal:**"):
            return line.replace("**Goal:**", "").strip()
    return None
```

---

## Prompt Building

```python
def _build_prompt(self, state: ExecutionState) -> str:
    if state.issue is None:
        raise ValueError("ExecutionState must have an issue")

    parts = []
    parts.append("## Issue")
    parts.append(f"**Title:** {state.issue.title}")
    parts.append(f"**Description:**\n{state.issue.description}")

    if state.design:
        parts.append("\n## Design Context")
        parts.append(state.design.raw_content)

    parts.append("\n## Your Task")
    parts.append(
        "Explore the codebase to understand relevant patterns and architecture, "
        "then create a detailed implementation plan for this issue."
    )

    return "\n".join(parts)
```

---

## Testing Approach

**Unit Tests:**
- Test async generator yields correct event types
- Test tool call/result accumulation in state
- Test plan persistence to disk
- Test goal extraction from markdown

**Integration Tests:**
- Test with real driver (mock at HTTP/SDK boundary)
- Verify message translation from driver to StreamEvent
- Verify state updates flow correctly

---

## Implementation Tasks

### Task 1: State Changes
**Files:** `amelia/core/state.py`
**Intent:** Add `raw_architect_output` field to ExecutionState

### Task 2: Architect Async Generator
**Files:** `amelia/agents/architect.py`
**Intent:** Convert `plan()` to async generator, remove `_scan_codebase()`

### Task 3: System Prompt Update
**Files:** `amelia/agents/architect.py`
**Intent:** Replace system prompt with exploration-focused, reference-based version

### Task 4: Orchestrator Integration
**Files:** `amelia/core/orchestrator.py`
**Intent:** Update `call_architect_node()` to consume async generator

### Task 5: Unit Tests
**Files:** `tests/unit/agents/test_architect.py`, `tests/unit/core/test_orchestrator.py`
**Intent:** Update tests for new async generator pattern

### Task 6: Integration Tests
**Files:** `tests/integration/test_agentic_workflow.py`
**Intent:** Add architect agentic execution tests

---

## Dependencies

- **Requires:** #198 (unified AgenticMessage) - merged ✓
- **Enables:** #199 (validator node) - will consume `raw_architect_output`

## Cleanup Deferred to #199

- Remove `_extract_goal_from_markdown()` temporary helper
- Remove goal extraction logic from `call_architect_node()`
