"""Architect agent for generating implementation plans.

This module provides the Architect agent that analyzes issues and produces
rich markdown implementation plans for agentic execution.
"""
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel, ConfigDict

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.state import ExecutionState
from amelia.core.types import Design, Profile
from amelia.drivers.base import AgenticMessageType, DriverInterface
from amelia.server.models.events import EventLevel, EventType, WorkflowEvent


if TYPE_CHECKING:
    from amelia.server.events.bus import EventBus


class PlanOutput(BaseModel):
    """Output from Architect plan generation.

    Attributes:
        markdown_content: The full markdown plan content.
        markdown_path: Path where the plan was saved.
        goal: High-level goal extracted from the plan.
        key_files: Files likely to be modified.

    """

    model_config = ConfigDict(frozen=True)

    markdown_content: str
    markdown_path: Path
    goal: str
    key_files: list[str] = []


class ArchitectOutput(BaseModel):
    """Output from Architect analysis (simplified form).

    Used when only analysis is needed, not full plan generation.

    Attributes:
        goal: Clear description of what needs to be done.
        strategy: High-level approach (not step-by-step).
        key_files: Files likely to be modified.
        risks: Potential risks to watch for.

    """

    model_config = ConfigDict(frozen=True)

    goal: str
    strategy: str
    key_files: list[str] = []
    risks: list[str] = []


class MarkdownPlanOutput(BaseModel):
    """Structured output for markdown plan generation.

    This is the schema the LLM uses to generate the plan content.

    Attributes:
        goal: High-level goal for the implementation.
        plan_markdown: The full markdown plan with phases, tasks, and steps.
        key_files: Files that will likely be modified.

    """

    goal: str
    plan_markdown: str
    key_files: list[str] = []


class Architect:
    """Agent responsible for creating implementation plans from issues.

    Generates rich markdown plans that the Developer agent can follow
    agentically, or provides simplified analysis when full plans aren't needed.

    Attributes:
        driver: LLM driver interface for plan generation.

    """

    SYSTEM_PROMPT = """You are a senior software architect creating implementation plans.
Your role is to analyze issues and produce detailed markdown implementation plans."""

    SYSTEM_PROMPT_PLAN = """You are a senior software architect creating implementation plans.

## Your Role
Write comprehensive implementation plans assuming the executor has ZERO context for the codebase and questionable taste. Document everything they need: which files to touch, complete code, exact commands, how to test it. Give the whole plan as bite-sized tasks.

You have read-only access to explore the codebase before planning.

## Principles
- DRY, YAGNI, TDD, frequent commits
- Assume executor is skilled but knows nothing about this toolset or problem domain
- Assume executor doesn't know good test design very well

## Exploration Goals
Before planning, discover:
- Existing patterns for similar features
- File structure and naming conventions
- Test patterns and coverage approach
- Dependencies and integration points

## Constraints
- DO NOT modify any files - exploration only
- DO NOT run tests, builds, or commands
- Focus on understanding before planning"""

    def __init__(
        self,
        driver: DriverInterface,
        event_bus: "EventBus | None" = None,
        prompts: dict[str, str] | None = None,
    ):
        """Initialize the Architect agent.

        Args:
            driver: LLM driver interface for plan generation.
            event_bus: Optional EventBus for emitting workflow events.
            prompts: Optional dict mapping prompt IDs to custom content.
                Supports keys: "architect.system", "architect.plan".

        """
        self.driver = driver
        self._event_bus = event_bus
        self._prompts = prompts or {}

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for analysis.

        Returns custom prompt if injected, otherwise class default.
        """
        return self._prompts.get("architect.system", self.SYSTEM_PROMPT)

    @property
    def plan_prompt(self) -> str:
        """Get the system prompt for plan generation.

        Returns custom prompt if injected, otherwise class default.
        """
        return self._prompts.get("architect.plan", self.SYSTEM_PROMPT_PLAN)

    def _build_prompt(self, state: ExecutionState, profile: Profile) -> str:
        """Build user prompt from execution state and profile.

        Combines issue information and optional design context into a single
        prompt string. Codebase structure is not included; the agent explores
        via tools instead.

        Args:
            state: The current execution state.
            profile: The profile containing working directory settings.

        Returns:
            Formatted prompt string with all context sections.

        Raises:
            ValueError: If no issue is present in the state.

        """
        if not state.issue:
            raise ValueError("Issue context is required for planning")

        parts: list[str] = []

        # Issue section (required)
        issue_parts = []
        if state.issue.title:
            issue_parts.append(f"**{state.issue.title}**")
        if state.issue.description:
            issue_parts.append(state.issue.description)
        issue_summary = "\n\n".join(issue_parts) if issue_parts else ""
        parts.append(f"## Issue\n\n{issue_summary}")

        # Design section (optional)
        if state.design:
            design_content = self._format_design_section(state.design)
            parts.append(f"## Design\n\n{design_content}")

        return "\n\n".join(parts)

    def _format_design_section(self, design: Design) -> str:
        """Format Design into structured markdown for context.

        Args:
            design: The design to format.

        Returns:
            Formatted markdown string with design fields.

        """
        parts = []

        parts.append(f"### Goal\n\n{design.goal}")
        parts.append(f"### Architecture\n\n{design.architecture}")

        if design.tech_stack:
            tech_list = "\n".join(f"- {tech}" for tech in design.tech_stack)
            parts.append(f"### Tech Stack\n\n{tech_list}")

        if design.components:
            comp_list = "\n".join(f"- {comp}" for comp in design.components)
            parts.append(f"### Components\n\n{comp_list}")

        if design.data_flow:
            parts.append(f"### Data Flow\n\n{design.data_flow}")

        if design.error_handling:
            parts.append(f"### Error Handling\n\n{design.error_handling}")

        if design.testing_strategy:
            parts.append(f"### Testing Strategy\n\n{design.testing_strategy}")

        if design.conventions:
            parts.append(f"### Conventions\n\n{design.conventions}")

        if design.relevant_files:
            files_list = "\n".join(f"- `{f}`" for f in design.relevant_files)
            parts.append(f"### Relevant Files\n\n{files_list}")

        return "\n\n".join(parts)

    async def plan(
        self,
        state: ExecutionState,
        profile: Profile,
        *,
        workflow_id: str,
    ) -> AsyncIterator[tuple[ExecutionState, WorkflowEvent]]:
        """Generate a markdown implementation plan from an issue using agentic execution.

        Creates a rich markdown plan by exploring the codebase with read-only tools,
        then producing a reference-based plan. Claude writes the plan to a file via
        the Write tool. Yields state/event tuples as execution progresses.

        Args:
            state: The execution state containing the issue and optional design.
            profile: The profile containing working directory settings.
            workflow_id: Workflow ID for stream events (required).

        Yields:
            Tuples of (updated ExecutionState, WorkflowEvent) as exploration and
            planning progresses.

        Raises:
            ValueError: If no issue is present in the state.

        """
        if not state.issue:
            raise ValueError("Cannot generate plan: no issue in ExecutionState")

        # Build user prompt from state (simplified - no codebase scan)
        user_prompt = self._build_agentic_prompt(state, profile)

        cwd = profile.working_dir or "."
        plan_path = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
        tool_calls: list[ToolCall] = list(state.tool_calls)
        tool_results: list[ToolResult] = list(state.tool_results)
        raw_output = ""
        current_state = state

        logger.info(
            "Architect starting agentic execution",
            cwd=cwd,
            plan_path=plan_path,
        )

        async for message in self.driver.execute_agentic(
            prompt=user_prompt,
            cwd=cwd,
            instructions=self.plan_prompt,
            required_tool="write_file",
            required_file_path=plan_path,
        ):
            event: WorkflowEvent | None = None

            if message.type == AgenticMessageType.THINKING:
                event = message.to_workflow_event(workflow_id=workflow_id, agent="architect")

            elif message.type == AgenticMessageType.TOOL_CALL:
                call = ToolCall(
                    id=message.tool_call_id or f"call-{len(tool_calls)}",
                    tool_name=message.tool_name or "unknown",
                    tool_input=message.tool_input or {},
                )
                tool_calls.append(call)
                # Log tool call details with explicit tool name in message
                input_keys = list(message.tool_input.keys()) if message.tool_input else []
                logger.debug(
                    f"TOOL_CALL: name={message.tool_name!r} keys={input_keys}"
                )
                event = message.to_workflow_event(workflow_id=workflow_id, agent="architect")

            elif message.type == AgenticMessageType.TOOL_RESULT:
                result = ToolResult(
                    call_id=message.tool_call_id or f"call-{len(tool_results)}",
                    tool_name=message.tool_name or "unknown",
                    output=message.tool_output or "",
                    success=not message.is_error,
                )
                tool_results.append(result)
                logger.debug(
                    "Architect tool result recorded",
                    call_id=result.call_id,
                )
                event = message.to_workflow_event(workflow_id=workflow_id, agent="architect")

            elif message.type == AgenticMessageType.RESULT:
                raw_output = message.content or ""
                event = message.to_workflow_event(workflow_id=workflow_id, agent="architect")

                # In agentic mode, Claude writes the plan via Write tool.
                # The orchestrator extracts the plan from tool_calls.
                # No need to save the summary response to a file.

                logger.info(
                    "Architect plan generated",
                    agent="architect",
                    raw_output_length=len(raw_output),
                    tool_calls_count=len(tool_calls),
                )

                # DEBUG: Log all tool calls at completion
                logger.debug(
                    "DEBUG: Architect completed - all tool calls",
                    tool_calls_summary=[
                        {"name": tc.tool_name, "input_keys": list(tc.tool_input.keys())}
                        for tc in tool_calls
                    ],
                    raw_output_preview=raw_output[:300] if raw_output else "EMPTY",
                )

                # Extract plan_path from Write tool calls
                # Note: CLI driver normalizes "Write" to "write_file" (ToolName.WRITE_FILE)
                extracted_plan_path: Path | None = None
                for tc in tool_calls:
                    if tc.tool_name == ToolName.WRITE_FILE and "file_path" in tc.tool_input:
                        extracted_plan_path = Path(tc.tool_input["file_path"])
                        break  # Use first Write call (should be the plan)

                # Yield final state with all updates
                current_state = state.model_copy(update={
                    "tool_calls": tool_calls,
                    "tool_results": tool_results,
                    "raw_architect_output": raw_output,
                    "plan_markdown": raw_output,  # Backward compat until #199
                    "plan_path": extracted_plan_path,
                })
                yield current_state, event
                continue  # Result is the final message - let loop drain naturally

            if event:
                current_state = state.model_copy(update={
                    "tool_calls": tool_calls,
                    "tool_results": tool_results,
                })
                yield current_state, event

    def _build_agentic_prompt(self, state: ExecutionState, profile: Profile) -> str:
        """Build user prompt for agentic plan generation.

        Simplified prompt that doesn't include codebase scan - the agent
        will explore using tools.

        Args:
            state: The current execution state.
            profile: The profile containing plan path pattern.

        Returns:
            Formatted prompt string with issue and design context.

        Raises:
            ValueError: If no issue is present in the state.

        """
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

        # Add output instruction with resolved plan path
        # IMPORTANT: Explicitly require writing to file - without this,
        # the LLM may just output the plan as text instead of writing to the file.
        plan_path = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
        parts.append("\n## Output (CRITICAL)")
        parts.append(
            f"**CRITICAL REQUIREMENT**: Create a markdown file at `{plan_path}` containing your implementation plan. "
            "This is NOT optional.\n\n"
            "Steps:\n"
            "1. Explore the codebase to understand patterns\n"
            "2. Create your implementation plan\n"
            f"3. Create the markdown file `{plan_path}` with the plan content\n"
            "4. Confirm the file was created\n\n"
            "Do NOT just output the plan as text - you MUST create the file. "
            "The workflow will fail if you don't create the plan file."
        )

        # Task-specific formatting templates
        parts.append("""
## Plan Document Header

Every plan MUST start with this header:

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Bite-Sized Task Granularity

Each step is ONE action (2-5 minutes):
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Task Structure

```markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
```

## What to Include
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant patterns with file:line syntax
- Test criteria and edge cases
- Task dependencies and ordering""")

        return "\n".join(parts)

    async def analyze(
        self,
        state: ExecutionState,
        profile: Profile,
        *,
        workflow_id: str,
    ) -> ArchitectOutput:
        """Analyze an issue and generate goal/strategy (simplified form).

        Creates an ArchitectOutput with high-level goal and strategy
        for quick analysis without full plan generation.

        Args:
            state: The execution state containing the issue and optional design.
            profile: The profile containing working directory settings.
            workflow_id: Workflow ID for stream events (required).

        Returns:
            ArchitectOutput containing goal, strategy, key files, and risks.

        Raises:
            ValueError: If no issue is present in the state.

        """
        if not state.issue:
            raise ValueError("Cannot analyze: no issue in ExecutionState")

        # Build prompt from state
        context_prompt = self._build_prompt(state, profile)

        # Build user prompt for analysis
        user_prompt = f"""{context_prompt}

---

Analyze this issue and provide:
1. A clear goal statement describing what needs to be accomplished
2. A high-level strategy for how to approach the implementation
3. Key files that will likely need to be modified
4. Any potential risks or considerations

Respond with a structured ArchitectOutput."""

        # Call driver with ArchitectOutput schema
        raw_response, _ = await self.driver.generate(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            schema=ArchitectOutput,
            cwd=profile.working_dir,
        )
        response = ArchitectOutput.model_validate(raw_response)

        logger.info(
            "Architect analysis complete",
            agent="architect",
            goal=response.goal[:100] + "..." if len(response.goal) > 100 else response.goal,
            key_files_count=len(response.key_files),
            risks_count=len(response.risks),
        )

        # Emit completion event
        if self._event_bus is not None:
            event = WorkflowEvent(
                id=str(uuid4()),
                workflow_id=workflow_id,
                sequence=0,
                timestamp=datetime.now(UTC),
                agent="architect",
                event_type=EventType.AGENT_OUTPUT,
                level=EventLevel.TRACE,
                message=f"Analysis complete: {response.goal[:100]}...",
            )
            self._event_bus.emit(event)

        return response
