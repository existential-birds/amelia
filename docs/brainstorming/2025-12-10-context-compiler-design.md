# Context Compiler Design

> Design document for Gap 1: Context Compiler from the [Context Engineering Gaps Analysis](../analysis/context-engineering-gaps.md).

## Problem Statement

Currently, `ExecutionState.messages` accumulates across agent transitions. Each agent receives full history rather than a minimal relevant view. This violates the principle:

> "Every LLM call should be a freshly computed projection against a durable state, not dragging the last 500 turns."

## Design Goals

1. Each agent receives only context relevant to its current task
2. Context computed fresh from durable state, not accumulated messages
3. Different compilation strategies per agent type
4. Enable inspection/debugging of what context was compiled

## Architecture

### Strategy-per-Agent Pattern

Each agent owns its context strategy. This allows agents to diverge significantly as the system grows to dozens of agents without a centralized "god class" becoming a maintenance burden.

```
┌─────────────────┐     ┌──────────────────────┐
│   Architect     │────▶│ ArchitectContext     │
│                 │     │ Strategy             │
└─────────────────┘     └──────────────────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │  CompiledContext     │
                        │  - system_prompt     │
                        │  - sections[]        │
                        │  - messages[]?       │
                        └──────────────────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │  list[AgentMessage]  │
                        └──────────────────────┘
```

### Core Types

Located in `amelia/core/context.py`:

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from amelia.core.state import ExecutionState, AgentMessage, Task


class ContextSection(BaseModel):
    """A named chunk of context for inspection and debugging.

    Attributes:
        name: Section identifier (e.g., "issue", "current_task", "file_context").
        content: The actual text content.
        source: Where this content came from (for debugging).
    """
    name: str
    content: str
    source: str | None = None


class CompiledContext(BaseModel):
    """Result of context compilation for an LLM call.

    Supports both structured sections (for inspection) and direct message
    override (for complex agents that need fine-grained control).

    Attributes:
        system_prompt: Optional system message content.
        sections: Named content sections that will be formatted into user message.
        messages: If set, overrides section-based message generation.
    """
    system_prompt: str | None = None
    sections: list[ContextSection] = []
    messages: list[AgentMessage] | None = None


class ContextStrategy(ABC):
    """Base class for agent-specific context compilation strategies.

    Each agent defines its own strategy that knows what context it needs
    from ExecutionState. Strategies pull everything from state—no additional
    parameters needed.
    """

    @abstractmethod
    def compile(self, state: ExecutionState) -> CompiledContext:
        """Compile minimal, relevant context from execution state.

        Args:
            state: Current execution state containing all durable data.

        Returns:
            Compiled context ready for conversion to messages.
        """
        ...

    def to_messages(self, context: CompiledContext) -> list[AgentMessage]:
        """Convert CompiledContext to AgentMessage list for driver.

        Default behavior:
        1. If context.messages is set, use it directly (override mode)
        2. Otherwise, build system message from system_prompt
        3. Build user message from sections with ## headers

        Args:
            context: The compiled context to convert.

        Returns:
            List of AgentMessage ready for driver.generate().
        """
        if context.messages:
            return context.messages

        messages = []

        if context.system_prompt:
            messages.append(AgentMessage(role="system", content=context.system_prompt))

        user_content = "\n\n".join(
            f"## {section.name}\n{section.content}"
            for section in context.sections
        )
        messages.append(AgentMessage(role="user", content=user_content))

        return messages

    # Shared helpers

    def get_current_task(self, state: ExecutionState) -> Task | None:
        """Get the current task from state's plan.

        Args:
            state: Current execution state.

        Returns:
            Current task if found, None otherwise.
        """
        if not state.plan or not state.current_task_id:
            return None
        for task in state.plan.tasks:
            if task.id == state.current_task_id:
                return task
        return None

    def get_issue_summary(self, state: ExecutionState) -> str | None:
        """Get a summary of the current issue.

        Args:
            state: Current execution state.

        Returns:
            Formatted issue summary or None if no issue.
        """
        if not state.issue:
            return None
        return f"{state.issue.title}\n\n{state.issue.description}"
```

### Agent Integration

Strategies are co-located with their agents. Each agent declares its strategy as a class attribute:

```python
# amelia/agents/developer.py

class DeveloperContextStrategy(ContextStrategy):
    """Context strategy for the Developer agent.

    Compiles: current task, file operations, steps to execute.
    """

    def compile(self, state: ExecutionState) -> CompiledContext:
        task = self.get_current_task(state)
        if not task:
            raise ValueError("No current task set in state")

        sections = [
            ContextSection(
                name="Task",
                content=task.description,
                source="state.plan.tasks[current_task_id]"
            ),
        ]

        # Add file operations
        if task.files:
            file_list = "\n".join(f"- {f.operation}: `{f.path}`" for f in task.files)
            sections.append(ContextSection(
                name="Files",
                content=file_list,
                source="task.files"
            ))

        # Add steps if present
        if task.steps:
            steps_content = []
            for i, step in enumerate(task.steps, 1):
                step_text = f"### Step {i}: {step.description}"
                if step.code:
                    step_text += f"\n```\n{step.code}\n```"
                if step.command:
                    step_text += f"\nRun: `{step.command}`"
                steps_content.append(step_text)
            sections.append(ContextSection(
                name="Steps",
                content="\n\n".join(steps_content),
                source="task.steps"
            ))

        return CompiledContext(
            system_prompt="You are a senior developer executing tasks following TDD principles.",
            sections=sections
        )


class Developer:
    context_strategy: type[ContextStrategy] = DeveloperContextStrategy

    def __init__(self, driver: DriverInterface):
        self.driver = driver

    async def execute_task(self, state: ExecutionState) -> DeveloperResponse:
        # Compile context
        strategy = self.context_strategy()
        context = strategy.compile(state)
        messages = strategy.to_messages(context)

        # Log for debugging
        logger.debug(
            "Compiled developer context",
            sections=[s.name for s in context.sections]
        )

        # Execute via driver
        response = await self.driver.generate(messages=messages, schema=DeveloperResponse)
        return response
```

### Per-Agent Context Requirements

| Agent | Minimal Context | Source |
|-------|-----------------|--------|
| **Architect** | Issue title/description, design doc (if any) | `state.issue`, design parameter |
| **Developer** | Current task, file operations, steps | `state.plan.tasks[current_task_id]` |
| **Reviewer** | Code diff, task description, acceptance criteria | `state.code_changes_for_review`, task |

## File Organization

```
amelia/
├── core/
│   ├── context.py          # ContextSection, CompiledContext, ContextStrategy ABC
│   └── state.py            # ExecutionState, AgentMessage (existing)
└── agents/
    ├── architect.py        # Architect + ArchitectContextStrategy
    ├── developer.py        # Developer + DeveloperContextStrategy
    └── reviewer.py         # Reviewer + ReviewerContextStrategy
```

## Inspection & Debugging

Context compilation is logged via loguru at debug level:

```python
logger.debug(
    "Compiled context",
    agent="developer",
    sections=[s.name for s in context.sections],
    system_prompt_length=len(context.system_prompt) if context.system_prompt else 0
)
```

For Phase 10 (Continuous Improvement), lightweight metadata can be added to the event system without storing full context content.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Strategy-per-Agent | Agents will diverge significantly; avoids god class |
| Output type | Hybrid `CompiledContext` | Structured sections for inspection + override for complex cases |
| Strategy registration | Agent class attribute | Agent owns its context needs |
| Method signature | `compile(state: ExecutionState)` | State contains everything; no parameter coordination |
| Compilation location | Agent calls its own strategy | Keeps agents self-contained |
| Interface | ABC with helpers | Shared utilities reduce duplication |
| Message formatting | `## {name}` headers | Clear section delineation in prompts |
| Inspection | Logging via loguru | Simple; upgrade path to events when needed |
| Naming | `{Agent}ContextStrategy` | Explicit, avoids confusion with output types |

## Migration Path

1. Add `amelia/core/context.py` with core types
2. Implement `ArchitectContextStrategy` in `architect.py`
3. Implement `DeveloperContextStrategy` in `developer.py`
4. Implement `ReviewerContextStrategy` in `reviewer.py`
5. Update each agent to use its strategy
6. Remove ad-hoc context building methods (`_build_context`, `_build_task_prompt`, etc.)

## Future Considerations

- **Prompt Prefix Stability (Gap 3)**: System prompts in strategies should be designed for cache reuse
- **Agent Scope Isolation (Gap 5)**: Strategies enforce minimal context by design
- **Phase 10 Integration**: Add context metadata to events for A/B testing correlation

## References

- [Context Engineering Gaps Analysis](../analysis/context-engineering-gaps.md)
- [Amelia Roadmap - Phase 2](../roadmap.md#phase-2-web-dashboard-in-progress)
- [12-Factor Agents - F3: Own Your Context Window](https://github.com/humanlayer/12-factor-agents)
