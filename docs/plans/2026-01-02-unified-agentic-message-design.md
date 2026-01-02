# Unified AgenticMessage Abstraction

**Issue:** #198
**Date:** 2026-01-02
**Status:** Approved

## Problem

`execute_agentic()` is not part of `DriverInterface` because each driver yields different types:

- `ClaudeCliDriver` → `claude_agent_sdk.types.Message`
- `ApiDriver` → `langchain_core.messages.BaseMessage`

This forces agents to use `isinstance()` checks and maintain separate execution paths with duplicated logic (~150 lines each in Developer).

## Solution

Introduce `AgenticMessage`, a unified message type that both drivers yield. This allows `execute_agentic()` to join `DriverInterface`.

### Layered Architecture

```
Dashboard ←── StreamEvent ←── Agents ←── AgenticMessage ←── Drivers ←── Native SDK types
```

- **AgenticMessage**: Driver→Agent boundary. ACP-inspired, semantic clarity.
- **StreamEvent**: Agent→Dashboard boundary. SSE-optimized with `workflow_id`, `id`, `agent`.

### AgenticMessage Definition

```python
# amelia/drivers/base.py

class AgenticMessageType(StrEnum):
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RESULT = "result"

class AgenticMessage(BaseModel):
    type: AgenticMessageType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: str | None = None
    session_id: str | None = None  # For CLI driver sessions, future API support
    is_error: bool = False

    def to_stream_event(self, agent: str, workflow_id: str) -> StreamEvent:
        """Convert to StreamEvent for dashboard consumption."""
        type_mapping = {
            AgenticMessageType.THINKING: StreamEventType.CLAUDE_THINKING,
            AgenticMessageType.TOOL_CALL: StreamEventType.CLAUDE_TOOL_CALL,
            AgenticMessageType.TOOL_RESULT: StreamEventType.CLAUDE_TOOL_RESULT,
            AgenticMessageType.RESULT: StreamEventType.AGENT_OUTPUT,
        }
        return StreamEvent(
            type=type_mapping[self.type],
            content=self.content or self.tool_output,
            timestamp=datetime.now(UTC),
            agent=agent,
            workflow_id=workflow_id,
            tool_name=self.tool_name,
            tool_input=self.tool_input,
            is_error=self.is_error,
        )
```

### StreamEvent Change

Add `is_error: bool = False` to `StreamEvent` for UI differentiation of error results.

### DriverInterface Addition

```python
class DriverInterface(Protocol):
    async def generate(...) -> GenerateResult: ...

    def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
    ) -> AsyncIterator[AgenticMessage]: ...
```

## Implementation Steps

1. Define `AgenticMessage` and `AgenticMessageType` in `amelia/drivers/base.py`
2. Add `is_error: bool = False` to `StreamEvent` in `amelia/core/types.py`
3. Update `ClaudeCliDriver.execute_agentic()` to yield `AgenticMessage`
4. Update `ApiDriver.execute_agentic()` to yield `AgenticMessage`
5. Add `execute_agentic()` to `DriverInterface` protocol
6. Refactor `Developer` to use single execution path
7. Refactor `Reviewer` to use single execution path
8. Remove driver-specific type imports from agents

## Acceptance Criteria

- [ ] `DriverInterface` protocol includes `execute_agentic()` method
- [ ] Both drivers yield `AgenticMessage` from `execute_agentic()`
- [ ] Developer and Reviewer use unified execution path (no `isinstance` checks)
- [ ] All existing tests pass
- [ ] `to_stream_event()` method works for agent→dashboard conversion
