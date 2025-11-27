
from pydantic import BaseModel
from pydantic import Field

from amelia.core.state import AgentMessage
from amelia.core.state import Task
from amelia.core.state import TaskDAG
from amelia.core.types import Issue
from amelia.drivers.base import DriverInterface


class TaskListResponse(BaseModel):
    """Schema for LLM-generated list of tasks."""
    tasks: list[Task] = Field(description="A list of actionable development tasks.")

class Architect:
    def __init__(self, driver: DriverInterface):
        self.driver = driver

    async def plan(self, issue: Issue) -> TaskDAG:
        """
        Generates a development plan (TaskDAG) from a given issue.
        """
        # System message for the LLM
        system_prompt = (
            "You are an expert software architect. "
            "Your role is to break down a user story into a sequence of actionable development tasks, "
            "identifying clear dependencies between them. "
            "The output MUST be a JSON object conforming to the TaskListResponse schema, "
            "containing a list of Task objects. "
            "Each Task must have a unique 'id', a 'description', and a list of 'dependencies' (task IDs). "
            "Ensure task descriptions are clear and concise."
        )

        # User message with the issue details
        user_prompt = (
            f"Given the following user story:\n\n"
            f"Title: {issue.title}\n"
            f"Description: {issue.description}\n\n"
            f"Provide a detailed plan as a JSON list of tasks with dependencies. "
            f"Ensure to output valid JSON that can be parsed directly into the TaskListResponse schema."
        )
        
        prompt_messages = [
            AgentMessage(role="system", content=system_prompt),
            AgentMessage(role="user", content=user_prompt)
        ]

        # Use the driver to generate a response, enforcing the TaskListResponse schema
        response = await self.driver.generate(messages=prompt_messages, schema=TaskListResponse)
        
        return TaskDAG(tasks=response.tasks, original_issue=issue.id)
