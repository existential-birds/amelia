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
from amelia.core.exceptions import AgenticExecutionError
from amelia.core.state import AgentMessage, Task
from amelia.drivers.base import DriverInterface


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


class Developer:
    """Agent responsible for executing development tasks following TDD principles.

    Attributes:
        driver: LLM driver interface for task execution and tool access.
        execution_mode: Execution mode (structured or agentic).
    """

    def __init__(self, driver: DriverInterface, execution_mode: ExecutionMode = "structured"):
        """Initialize the Developer agent.

        Args:
            driver: LLM driver interface for task execution and tool access.
            execution_mode: Execution mode. Defaults to "structured".
        """
        self.driver = driver
        self.execution_mode = execution_mode

    async def execute_task(self, task: Task, cwd: str | None = None) -> dict[str, Any]:
        """Execute a single development task.

        Args:
            task: The task to execute.
            cwd: Working directory for agentic execution.

        Returns:
            Dict with status and output.

        Raises:
            AgenticExecutionError: If agentic execution fails.
        """
        if self.execution_mode == "agentic":
            return await self._execute_agentic(task, cwd or os.getcwd())
        else:
            return await self._execute_structured(task)

    async def _execute_agentic(self, task: Task, cwd: str) -> dict[str, Any]:
        """Execute task autonomously with full Claude tool access.

        Args:
            task: The task to execute.
            cwd: Working directory for execution.

        Returns:
            Dict with status and output.

        Raises:
            AgenticExecutionError: If execution fails.
        """
        prompt = self._build_task_prompt(task)
        logger.info(f"Starting agentic execution for task {task.id}")

        async for event in self.driver.execute_agentic(prompt, cwd):
            self._handle_stream_event(event)

            if event.type == "error":
                raise AgenticExecutionError(event.content or "Unknown error")

        return {"status": "completed", "task_id": task.id, "output": "Agentic execution completed"}

    def _build_task_prompt(self, task: Task) -> str:
        """Convert task to a prompt for agentic execution.

        Args:
            task: The task to convert.

        Returns:
            Formatted prompt string.
        """
        sections = [f"# Task: {task.description}", "", "## Files"]

        for file_op in task.files:
            sections.append(f"- {file_op.operation}: `{file_op.path}`")

        if task.steps:
            sections.append("")
            sections.append("## Steps")
            for i, step in enumerate(task.steps, 1):
                sections.append(f"### Step {i}: {step.description}")
                if step.code:
                    sections.append(f"```\n{step.code}\n```")
                if step.command:
                    sections.append(f"Run: `{step.command}`")
                if step.expected_output:
                    sections.append(f"Expected: {step.expected_output}")

        sections.append("")
        sections.append("Execute this task following TDD principles. Run tests after each change.")

        return "\n".join(sections)

    def _handle_stream_event(self, event: Any) -> None:
        """Display streaming event to terminal.

        Args:
            event: Stream event to display.
        """
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

    async def _execute_structured(self, task: Task) -> dict[str, Any]:
        """Execute task using structured step-by-step approach.

        Args:
            task: The task to execute.

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
                messages = [
                    AgentMessage(role="system", content="You are a skilled software developer. Execute the given task."),
                    AgentMessage(role="user", content=f"Task to execute: {task.description}")
                ]
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
