from typing import Any
from typing import Literal

from loguru import logger
from pydantic import BaseModel

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
            # This is a very simplified execution logic.
            # A real implementation would parse the task description more intelligently
            # or rely on structured tool calls from an LLM.

            # Example: if task description implies a shell command
            if task.description.lower().startswith("run shell command:"):
                command = task.description[len("run shell command:"):].strip()
                logger.info(f"Developer executing shell command: {command}")
                # The driver's execute_tool needs to map to actual shell execution
                result = await self.driver.execute_tool("run_shell_command", command=command)
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

                result = await self.driver.execute_tool("write_file", file_path=file_path, content=content)
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
