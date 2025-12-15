# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import asyncio
import os
from typing import Any, Literal

import typer
from loguru import logger
from pydantic import BaseModel

from amelia.core.constants import ToolName
from amelia.core.context import CompiledContext, ContextSection, ContextStrategy
from amelia.core.exceptions import AgenticExecutionError
from amelia.core.state import AgentMessage, ExecutionState, Task
from amelia.core.types import StreamEmitter
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.claude import convert_to_stream_event


DeveloperStatus = Literal["completed", "failed", "in_progress"]
ExecutionMode = Literal["structured", "agentic"]


class DeveloperResponse(BaseModel):
    """Schema for Developer agent's task execution output.

    Attributes:
        status: Execution status (completed, failed, or in_progress).
        output: Human-readable description of what was accomplished.
        error: Error message if status is failed, None otherwise.
    """

    status: DeveloperStatus
    output: str
    error: str | None = None


class DeveloperContextStrategy(ContextStrategy):
    """Context compilation strategy for the Developer agent.

    Compiles minimal context for task execution, focusing only on the current task
    from the TaskDAG without issue context or other agents' history.
    """

    SYSTEM_PROMPT = """You are a senior developer executing tasks following TDD principles.
Run tests after each change. Follow the task steps exactly."""

    ALLOWED_SECTIONS = {"task", "files", "steps"}

    def compile(self, state: ExecutionState) -> CompiledContext:
        """Compile ExecutionState into minimal task execution context.

        Args:
            state: The current execution state.

        Returns:
            CompiledContext with task-specific sections.

        Raises:
            ValueError: If no current task is found.
        """
        task = self.get_current_task(state)
        if task is None:
            raise ValueError("No current task found in execution state")

        sections: list[ContextSection] = []

        # Task section (required)
        sections.append(
            ContextSection(
                name="task",
                content=task.description,
                source=f"task:{task.id}",
            )
        )

        # Files section (optional, when task has files)
        if task.files:
            files_lines = [f"- {file_op.operation}: `{file_op.path}`" for file_op in task.files]
            sections.append(
                ContextSection(
                    name="files",
                    content="\n".join(files_lines),
                    source=f"task:{task.id}:files",
                )
            )

        # Steps section (optional)
        if task.steps:
            steps_lines = []
            for i, step in enumerate(task.steps, 1):
                steps_lines.append(f"### Step {i}: {step.description}")
                if step.code:
                    steps_lines.append(f"```\n{step.code}\n```")
                if step.command:
                    steps_lines.append(f"Run: `{step.command}`")
                if step.expected_output:
                    steps_lines.append(f"Expected: {step.expected_output}")
                steps_lines.append("")  # Blank line between steps

            sections.append(
                ContextSection(
                    name="steps",
                    content="\n".join(steps_lines).rstrip(),
                    source=f"task:{task.id}:steps",
                )
            )

        # Validate sections before returning
        self.validate_sections(sections)

        return CompiledContext(
            system_prompt=self.SYSTEM_PROMPT,
            sections=sections,
        )


class Developer:
    """Agent responsible for executing development tasks following TDD principles.

    Attributes:
        driver: LLM driver interface for task execution and tool access.
        execution_mode: Execution mode (structured or agentic).
        context_strategy: Context compilation strategy class.
    """

    context_strategy: type[ContextStrategy] = DeveloperContextStrategy

    def __init__(
        self,
        driver: DriverInterface,
        execution_mode: ExecutionMode = "structured",
        stream_emitter: StreamEmitter | None = None,
    ):
        """Initialize the Developer agent.

        Args:
            driver: LLM driver interface for task execution and tool access.
            execution_mode: Execution mode. Defaults to "structured".
            stream_emitter: Optional callback for streaming events.
        """
        self.driver = driver
        self.execution_mode = execution_mode
        self._stream_emitter = stream_emitter

    async def execute_current_task(
        self,
        state: ExecutionState,
        *,
        workflow_id: str,
    ) -> dict[str, Any]:
        """Execute the current task from execution state.

        Args:
            state: Full execution state containing profile, plan, and current_task_id.
            workflow_id: Workflow ID for stream events (required).

        Returns:
            Dict with status, task_id, and output.

        Raises:
            ValueError: If current_task_id not found in plan.
            AgenticExecutionError: If agentic execution fails.
        """
        if not state.plan or not state.current_task_id:
            raise ValueError("State must have plan and current_task_id")

        task = state.plan.get_task(state.current_task_id)
        if not task:
            raise ValueError(f"Task not found: {state.current_task_id}")

        cwd = state.profile.working_dir or os.getcwd()

        if self.execution_mode == "agentic":
            return await self._execute_agentic(task, cwd, state, workflow_id=workflow_id)
        else:
            result = await self._execute_structured(task, state)
            # Ensure task_id is included for consistency with agentic path
            result["task_id"] = task.id
            return result

    async def _execute_agentic(
        self,
        task: Task,
        cwd: str,
        state: ExecutionState,
        *,
        workflow_id: str,
    ) -> dict[str, Any]:
        """Execute task autonomously with full Claude tool access.

        Args:
            task: The task to execute.
            cwd: Working directory for execution.
            state: Full execution state for context compilation.
            workflow_id: Workflow ID for stream events (required).

        Returns:
            Dict with status and output.

        Raises:
            AgenticExecutionError: If execution fails.
        """
        # Use context strategy with full state (no longer creating fake state)
        strategy = self.context_strategy()
        context = strategy.compile(state)

        logger.debug(
            "Compiled context",
            agent="developer",
            sections=[s.name for s in context.sections],
            system_prompt_length=len(context.system_prompt) if context.system_prompt else 0
        )

        messages = strategy.to_messages(context)

        logger.info(f"Starting agentic execution for task {task.id}")

        async for event in self.driver.execute_agentic(messages, cwd, system_prompt=context.system_prompt):
            self._handle_stream_event(event, workflow_id)

            if event.type == "error":
                raise AgenticExecutionError(event.content or "Unknown error")

        return {"status": "completed", "task_id": task.id, "output": "Agentic execution completed"}

    def _handle_stream_event(self, event: Any, workflow_id: str) -> None:
        """Display streaming event to terminal and emit via callback.

        Args:
            event: Stream event to display.
            workflow_id: Current workflow ID.
        """
        # Terminal display (existing logic)
        if event.type == "tool_use":
            typer.secho(f"  -> {event.tool_name}", fg=typer.colors.CYAN)
            if event.tool_input:
                preview = str(event.tool_input)[:100]
                suffix = "..." if len(str(event.tool_input)) > 100 else ""
                typer.echo(f"    {preview}{suffix}")

        elif event.type == "result":
            typer.secho("  Done", fg=typer.colors.GREEN)

        elif event.type == "assistant" and event.content:
            typer.echo(f"  {event.content[:200]}")

        elif event.type == "error":
            typer.secho(f"  Error: {event.content}", fg=typer.colors.RED)

        # Emit via callback if configured
        if self._stream_emitter is not None:
            stream_event = convert_to_stream_event(event, "developer", workflow_id)
            if stream_event is not None:
                # Fire-and-forget: emit stream event without blocking
                emit_task: asyncio.Task[None] = asyncio.create_task(self._stream_emitter(stream_event))  # type: ignore[arg-type]
                emit_task.add_done_callback(
                    lambda t: logger.exception("Stream emitter failed", exc_info=t.exception())
                    if t.exception()
                    else None
                )

    async def _execute_structured(self, task: Task, state: ExecutionState) -> dict[str, Any]:
        """Execute task using structured step-by-step approach.

        Args:
            task: The task to execute.
            state: Full execution state (for future context usage).

        Returns:
            Dict with status and output.
        """
        try:
            if task.steps:
                logger.info(f"Developer executing {len(task.steps)} steps for task {task.id}")
                results = []
                for i, step in enumerate(task.steps, 1):
                    logger.info(f"Executing step {i}: {step.description}")
                    step_output = ""

                    if step.code:
                        target_file = None
                        if task.files:
                            for f in task.files:
                                if f.operation in ("create", "modify"):
                                    target_file = f.path
                                    break

                        if target_file:
                            logger.info(f"Writing code to {target_file}")
                            await self.driver.execute_tool(ToolName.WRITE_FILE, file_path=target_file, content=step.code)
                            step_output += f"Wrote to {target_file}. "
                        else:
                            logger.warning("Step has code but no target file could be determined from task.files.")

                    if step.command:
                        logger.info(f"Running command: {step.command}")
                        cmd_result = await self.driver.execute_tool(ToolName.RUN_SHELL_COMMAND, command=step.command)
                        step_output += f"Command output: {cmd_result}"

                    results.append(f"Step {i}: {step_output}")

                return {"status": "completed", "output": "\n".join(results)}

            task_desc_lower = task.description.lower().strip()

            if task_desc_lower.startswith("run shell command:"):
                prefix_len = len("run shell command:")
                command = task.description[prefix_len:].strip()
                logger.info(f"Developer executing shell command: {command}")
                result = await self.driver.execute_tool(ToolName.RUN_SHELL_COMMAND, command=command)
                return {"status": "completed", "output": result}

            elif task_desc_lower.startswith("write file:"):
                logger.info(f"Developer executing write file task: {task.description}")

                # Using original description for content extraction
                if " with " in task.description:
                    parts = task.description.split(" with ", 1)
                    path_part = parts[0]
                    content = parts[1]
                else:
                    path_part = task.description
                    content = ""
                
                file_path = path_part[len("write file:"):].strip()

                result = await self.driver.execute_tool(ToolName.WRITE_FILE, file_path=file_path, content=content)
                return {"status": "completed", "output": result}

            else:
                logger.info(f"Developer generating response for task: {task.description}")
                # Use context strategy for consistent message compilation
                strategy = self.context_strategy()
                context = strategy.compile(state)
                # Build messages: prepend system prompt if present, then user messages
                messages: list[AgentMessage] = []
                if context.system_prompt:
                    messages.append(AgentMessage(role="system", content=context.system_prompt))
                messages.extend(strategy.to_messages(context))
                llm_response = await self.driver.generate(messages=messages)
                return {"status": "completed", "output": llm_response}

        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            raise
        except Exception as e:
            logger.exception(
                "Developer task execution failed",
                error_type=type(e).__name__,
            )
            return {"status": "failed", "output": str(e), "error": str(e)}
