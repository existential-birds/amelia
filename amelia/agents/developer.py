from typing import Any
from typing import Literal

from loguru import logger
from pydantic import BaseModel

from amelia.core.constants import ToolName
from amelia.core.state import AgentMessage
from amelia.core.state import Task
from amelia.drivers.base import DriverInterface


DeveloperStatus = Literal["completed", "failed", "in_progress"]


class DeveloperResponse(BaseModel):
    """Schema for Developer agent's task execution output."""
    status: DeveloperStatus
    output: str
    error: str | None = None


class Developer:
    def __init__(self, driver: DriverInterface):
        self.driver = driver

    async def execute_task(self, task: Task) -> dict[str, Any]:
        """
        Executes a single development task with error handling.
        """
        try:
            # If the task has defined steps (TDD pattern), execute them sequentially
            if task.steps:
                logger.info(f"Developer executing {len(task.steps)} steps for task {task.id}")
                results = []
                for i, step in enumerate(task.steps, 1):
                    logger.info(f"Executing step {i}: {step.description}")
                    step_output = ""
                    
                    # 1. Write code if provided
                    if step.code:
                        # Identify file path from task.files or infer? 
                        # For now, we look for a matching file operation in task.files
                        # This is a simplification; ideally the step knows which file it touches.
                        # If task has files, use the first one for now or try to find context.
                        # But task.files has 'path'.
                        
                        # Heuristic: if we have code, we need a file to write to.
                        # If the task has explicit file operations, use the first one that matches 'create' or 'modify'.
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
                            # If no file specified, maybe it's a test file?
                            logger.warning("Step has code but no target file could be determined from task.files.")

                    # 2. Run command if provided
                    if step.command:
                        logger.info(f"Running command: {step.command}")
                        cmd_result = await self.driver.execute_tool(ToolName.RUN_SHELL_COMMAND, command=step.command)
                        step_output += f"Command output: {cmd_result}"

                    results.append(f"Step {i}: {step_output}")

                return {"status": "completed", "output": "\n".join(results)}

            # Fallback: Existing logic for simple tasks
            # Example: if task description implies a shell command
            if task.description.lower().startswith("run shell command:"):
                command = task.description[len("run shell command:"):].strip()
                logger.info(f"Developer executing shell command: {command}")
                # The driver's execute_tool needs to map to actual shell execution
                result = await self.driver.execute_tool(ToolName.RUN_SHELL_COMMAND, command=command)
                return {"status": "completed", "output": result}

            # Example: if task description implies writing a file
            elif task.description.lower().startswith("write file:"):
                # This would need more structure in the task for file_path and content
                logger.info(f"Developer executing write file task: {task.description}")

                # Basic parsing for the test: "write file: <path> with <content>"
                # This is fragile but sufficient for the current string-based protocol without LLM function calling
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

            # Fallback: if no specific tool is identified, use LLM to generate response
            else:
                logger.info(f"Developer generating response for task: {task.description}")
                messages = [
                    AgentMessage(role="system", content="You are a skilled software developer. Execute the given task."),
                    AgentMessage(role="user", content=f"Task to execute: {task.description}")
                ]
                llm_response = await self.driver.generate(messages=messages)
                return {"status": "completed", "output": llm_response}

        except Exception as e:
            logger.error(f"Developer task execution failed: {e}")
            return {"status": "failed", "output": str(e), "error": str(e)}
