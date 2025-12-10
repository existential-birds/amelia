# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from amelia.core.types import Issue, Profile


TaskStatus = Literal["pending", "in_progress", "completed", "failed"]
Severity = Literal["low", "medium", "high", "critical"]


class TaskStep(BaseModel):
    """A single step within a task (2-5 minutes of work).

    Attributes:
        description: Description of what this step accomplishes.
        code: Optional code snippet to execute.
        command: Optional command to run.
        expected_output: Optional description of the expected output.
    """
    description: str
    code: str | None = None
    command: str | None = None
    expected_output: str | None = None


class FileOperation(BaseModel):
    """A file to be created, modified, or tested.

    Attributes:
        operation: Type of operation (create, modify, or test).
        path: File path relative to project root.
        line_range: Optional line range for modifications (e.g., "10-20").
    """
    operation: Literal["create", "modify", "test"]
    path: str
    line_range: str | None = None


class Task(BaseModel):
    """Task with TDD structure.

    Attributes:
        id: Unique task identifier.
        description: Human-readable task description.
        status: Current task status (pending, in_progress, completed, failed).
        dependencies: List of task IDs that must complete before this task.
        files: List of file operations involved in this task.
        steps: List of steps to execute for this task.
        commit_message: Optional git commit message for this task.
    """
    id: str
    description: str
    status: TaskStatus = "pending"
    dependencies: list[str] = Field(default_factory=list)
    files: list[FileOperation] = Field(default_factory=list)
    steps: list[TaskStep] = Field(default_factory=list)
    commit_message: str | None = None

class TaskDAG(BaseModel):
    """Directed Acyclic Graph of tasks with dependency management.

    Attributes:
        tasks: List of all tasks in the plan.
        original_issue: The original issue description that generated this plan.
    """
    tasks: list[Task]
    original_issue: str

    @field_validator("tasks")
    @classmethod
    def validate_task_graph(cls, tasks: list[Task]) -> list[Task]:
        """Validate task graph: check dependencies exist and no cycles.

        Args:
            tasks: List of tasks to validate.

        Returns:
            The validated list of tasks.

        Raises:
            ValueError: If a dependency doesn't exist or a cycle is detected.
        """
        task_ids = {t.id for t in tasks}

        # Check all dependencies exist BEFORE checking for cycles
        for task in tasks:
            for dep in task.dependencies:
                if dep not in task_ids:
                    raise ValueError(f"Task '{dep}' not found")

        # Check for cycles using DFS
        adjacency = {t.id: t.dependencies for t in tasks}
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in task_ids}

        def dfs(node: str) -> bool:
            """Depth-first search to detect cycles.

            Args:
                node: Current task ID being visited.

            Returns:
                True if a cycle is detected, False otherwise.
            """
            color[node] = GRAY
            for neighbor in adjacency.get(node, []):
                if color[neighbor] == GRAY:
                    return True  # Back edge = cycle
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for tid in task_ids:
            if color[tid] == WHITE and dfs(tid):
                raise ValueError("Cyclic dependency detected")

        return tasks

    def get_ready_tasks(self) -> list[Task]:
        """Return tasks that are pending and have all dependencies completed.

        Returns:
            List of tasks that are ready to be executed.
        """
        completed_ids = {t.id for t in self.tasks if t.status == "completed"}
        ready = []
        for task in self.tasks:
            if task.status == "pending" and all(dep in completed_ids for dep in task.dependencies):
                ready.append(task)
        return ready

class ReviewResult(BaseModel):
    """Result from a code review.

    Attributes:
        reviewer_persona: The persona or role of the reviewer.
        approved: Whether the review approved the changes.
        comments: List of review comments or feedback.
        severity: Severity level of issues found (low, medium, high, critical).
    """
    reviewer_persona: str
    approved: bool
    comments: list[str]
    severity: Severity

class AgentMessage(BaseModel):
    """Message from an agent in the orchestrator conversation.

    Attributes:
        role: Role of the message sender (system, assistant, user).
        content: The message content.
        tool_calls: Optional list of tool calls made by the agent.
    """
    role: str
    content: str
    tool_calls: list[Any] | None = None

class ExecutionState(BaseModel):
    """State for the LangGraph orchestrator execution.

    Attributes:
        profile: Active profile configuration.
        issue: The issue being worked on.
        plan: The task execution plan (DAG).
        current_task_id: ID of the currently executing task.
        human_approved: Whether human approval was granted for the plan.
        last_review: Most recent review result (only latest matters for decisions).
        code_changes_for_review: Staged code changes for review.
        driver_session_id: Session ID for CLI driver session continuity (works with any driver).
        workflow_status: Status of the workflow (running, completed, failed).
    """
    profile: Profile
    issue: Issue | None = None
    plan: TaskDAG | None = None
    current_task_id: str | None = None
    human_approved: bool | None = None # Field to store human approval status
    last_review: ReviewResult | None = None
    code_changes_for_review: str | None = None # For local review or specific review contexts
    driver_session_id: str | None = None
    workflow_status: Literal["running", "completed", "failed"] = "running"
