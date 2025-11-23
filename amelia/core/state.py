from typing import List, Optional, Literal, Any
from pydantic import BaseModel, Field
from amelia.core.types import Profile, Issue

TaskStatus = Literal["pending", "in_progress", "completed", "failed"]
Severity = Literal["low", "medium", "high", "critical"]

class Task(BaseModel):
    id: str
    description: str
    status: TaskStatus = "pending"
    dependencies: List[str] = Field(default_factory=list)
    files_changed: List[str] = Field(default_factory=list)

class TaskDAG(BaseModel):
    tasks: List[Task]
    original_issue: str

class ReviewResult(BaseModel):
    reviewer_persona: str
    approved: bool
    comments: List[str]
    severity: Severity

class AgentMessage(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[Any]] = None

class ExecutionState(BaseModel):
    profile: Profile
    issue: Optional[Issue] = None
    plan: Optional[TaskDAG] = None
    current_task_id: Optional[str] = None
    human_approved: Optional[bool] = None # Field to store human approval status
    review_results: List[ReviewResult] = Field(default_factory=list)
    messages: List[AgentMessage] = Field(default_factory=list)
    code_changes_for_review: Optional[str] = None # For local review or specific review contexts
