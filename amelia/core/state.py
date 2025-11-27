from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field

from amelia.core.types import Issue
from amelia.core.types import Profile


TaskStatus = Literal["pending", "in_progress", "completed", "failed"]
Severity = Literal["low", "medium", "high", "critical"]


class TaskStep(BaseModel):
    """A single step within a task (2-5 minutes of work)."""
    description: str
    code: str | None = None
    command: str | None = None
    expected_output: str | None = None


class FileOperation(BaseModel):
    """A file to be created, modified, or tested."""
    operation: Literal["create", "modify", "test"]
    path: str
    line_range: str | None = None


class Task(BaseModel):
    id: str
    description: str
    status: TaskStatus = "pending"
    dependencies: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)

class TaskDAG(BaseModel):
    tasks: list[Task]
    original_issue: str

class ReviewResult(BaseModel):
    reviewer_persona: str
    approved: bool
    comments: list[str]
    severity: Severity

class AgentMessage(BaseModel):
    role: str
    content: str
    tool_calls: list[Any] | None = None

class ExecutionState(BaseModel):
    profile: Profile
    issue: Issue | None = None
    plan: TaskDAG | None = None
    current_task_id: str | None = None
    human_approved: bool | None = None # Field to store human approval status
    review_results: list[ReviewResult] = Field(default_factory=list)
    messages: list[AgentMessage] = Field(default_factory=list)
    code_changes_for_review: str | None = None # For local review or specific review contexts
