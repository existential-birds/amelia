"""Configuration and shared type definitions for the Amelia orchestrator.

Contains StrEnum types (DriverType, TrackerType, Severity) and
Pydantic models (RetryConfig, SandboxConfig, Profile, Settings, Issue) used throughout
the Amelia agentic coding orchestrator.
"""
import uuid
from datetime import datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


# Default allowed hosts for sandbox network allowlist
DEFAULT_NETWORK_ALLOWED_HOSTS: tuple[str, ...] = (
    "api.anthropic.com",
    "openrouter.ai",
    "api.openai.com",
    "github.com",
    "registry.npmjs.org",
    "pypi.org",
    "files.pythonhosted.org",
    "app.daytona.io",
)


class DriverType(StrEnum):
    """LLM driver type for agent configuration."""

    CLAUDE = "claude"
    CODEX = "codex"
    API = "api"


class TrackerType(StrEnum):
    """Issue tracker type for profile configuration."""

    JIRA = "jira"
    GITHUB = "github"
    NOOP = "noop"


class SandboxMode(StrEnum):
    """Sandbox execution mode."""

    NONE = "none"
    CONTAINER = "container"
    DAYTONA = "daytona"


class DaytonaResources(BaseModel):
    """Resource configuration for Daytona sandbox instances.

    Attributes:
        cpu: Number of CPU cores.
        memory: Memory in GB.
        disk: Disk space in GB.
    """

    model_config = ConfigDict(frozen=True)

    cpu: int = Field(default=2, gt=0)
    memory: int = Field(default=4, gt=0)
    disk: int = Field(default=10, gt=0)


class SandboxConfig(BaseModel):
    """Sandbox execution configuration for a profile.

    Attributes:
        mode: Sandbox mode ('none' = direct execution, 'container' = Docker sandbox,
            'daytona' = Daytona cloud sandbox).
        image: Docker image for sandbox container.
        network_allowlist_enabled: Whether to restrict outbound network.
        network_allowed_hosts: Hosts allowed when network allowlist is enabled.
        repo_url: Git remote URL to clone into the sandbox.
        daytona_api_url: Daytona API endpoint URL.
        daytona_target: Daytona target region.
        daytona_resources: Optional CPU/memory/disk resource configuration.
    """

    model_config = ConfigDict(frozen=True)

    mode: SandboxMode = SandboxMode.NONE
    image: str = "amelia-sandbox:latest"
    network_allowlist_enabled: bool = False
    network_allowed_hosts: tuple[str, ...] = Field(
        default_factory=lambda: DEFAULT_NETWORK_ALLOWED_HOSTS,
    )

    # Remote sandbox fields (Daytona)
    repo_url: str | None = None
    daytona_api_url: str = "https://app.daytona.io/api"
    daytona_target: str = "us"
    daytona_resources: DaytonaResources | None = None
    daytona_image: str = "python:3.12-slim"
    daytona_snapshot: str | None = None
    daytona_timeout: float = Field(default=120.0, gt=0)

    @model_validator(mode="after")
    def _validate_daytona(self) -> "SandboxConfig":
        if self.mode == SandboxMode.DAYTONA:
            if not self.repo_url:
                raise ValueError("repo_url is required when mode='daytona'")
            if self.network_allowlist_enabled:
                raise ValueError(
                    "Network allowlist is not supported with Daytona sandboxes"
                )
        return self


class AgentConfig(BaseModel):
    """Per-agent driver and model configuration."""

    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str
    options: dict[str, Any] = Field(default_factory=dict)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    profile_name: str = "default"


REQUIRED_AGENTS: frozenset[str] = frozenset({
    "architect", "developer", "reviewer", "task_reviewer",
    "evaluator", "brainstormer", "plan_validator",
})


class RetryConfig(BaseModel):
    """Retry configuration for transient failures."""

    max_retries: int = Field(
        default=3, ge=0, le=10, description="Maximum number of retry attempts"
    )
    base_delay: float = Field(
        default=1.0, ge=0.1, le=30.0, description="Base delay in seconds for exponential backoff"
    )
    max_delay: float = Field(
        default=60.0, ge=1.0, le=300.0, description="Maximum delay cap in seconds"
    )


class AggressivenessLevel(IntEnum):
    """Aggressiveness level for PR auto-fix comment classification.

    Ordered for threshold comparisons: ``if level >= AggressivenessLevel.STANDARD``.

    - CRITICAL (1): Only fix clear bugs, security issues, build failures
    - STANDARD (2): Fix style issues, common patterns, and critical items
    - THOROUGH (3): Fix all actionable comments including suggestions and nitpicks
    """

    CRITICAL = 1
    STANDARD = 2
    THOROUGH = 3


class PRSummary(BaseModel):
    """Summary of a GitHub pull request.

    Attributes:
        number: PR number.
        title: PR title.
        head_branch: Head branch name.
        author: PR author login.
        updated_at: Last update timestamp.
    """

    model_config = ConfigDict(frozen=True)

    number: int = Field(description="PR number")
    title: str = Field(description="PR title")
    head_branch: str = Field(description="Head branch name")
    author: str = Field(description="PR author login")
    updated_at: datetime = Field(description="Last update timestamp")


class PRReviewComment(BaseModel):
    """A review comment on a GitHub pull request.

    Handles both inline (file-specific) and general review comments.
    For general comments, path/line/diff_hunk are None.

    Attributes:
        id: GitHub comment ID.
        body: Comment body text.
        author: Comment author login.
        created_at: Comment creation timestamp.
        path: File path for inline comments (None for general).
        line: Line number for inline comments (None for general).
        diff_hunk: Diff context for inline comments (None for general).
        in_reply_to_id: Parent comment ID for threaded replies.
        thread_id: Review thread ID from GraphQL.
        node_id: GraphQL node ID for thread resolution.
        pr_number: PR number this comment belongs to.
    """

    model_config = ConfigDict(frozen=True)

    id: int = Field(description="GitHub comment ID")
    body: str = Field(description="Comment body text")
    author: str = Field(description="Comment author login")
    created_at: datetime = Field(description="Comment creation timestamp")
    path: str | None = Field(default=None, description="File path for inline comments")
    line: int | None = Field(default=None, description="Line number for inline comments")
    diff_hunk: str | None = Field(default=None, description="Diff context for inline comments")
    in_reply_to_id: int | None = Field(default=None, description="Parent comment ID for threaded replies")
    thread_id: str | None = Field(default=None, description="Review thread ID from GraphQL")
    node_id: str | None = Field(default=None, description="GraphQL node ID for thread resolution")
    pr_number: int | None = Field(default=None, description="PR number this comment belongs to")


class PRAutoFixConfig(BaseModel):
    """Configuration for PR auto-fix behavior.

    Frozen to support the stateless reducer pattern.
    Use ``model_copy(update={...})`` for per-PR overrides.

    Attributes:
        aggressiveness: Which comment severity levels to auto-fix.
        poll_interval: Polling interval in seconds (10--3600).
        auto_resolve: Whether to auto-resolve review threads after fix.
        max_iterations: Maximum fix attempts per review thread (1--10).
        commit_prefix: Prefix for auto-fix commit messages.
        ignore_authors: Comment authors to ignore (exact username match).
    """

    model_config = ConfigDict(frozen=True)

    aggressiveness: AggressivenessLevel = AggressivenessLevel.STANDARD
    poll_interval: int = Field(default=60, ge=10, le=3600, description="Polling interval in seconds")
    auto_resolve: bool = Field(default=True, description="Auto-resolve threads after fix")
    max_iterations: int = Field(default=3, ge=1, le=10, description="Max fix attempts per thread")
    commit_prefix: str = Field(default="fix(review):", description="Commit message prefix")
    ignore_authors: list[str] = Field(
        default_factory=list,
        description="Comment authors to ignore (exact username match)",
    )
    resolve_no_changes: bool = Field(
        default=True,
        description="Resolve threads for no-changes comments",
    )
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to act on a classification",
    )

    @field_validator("aggressiveness", mode="before")
    @classmethod
    def _parse_aggressiveness(cls, v: int | str | AggressivenessLevel) -> AggressivenessLevel:
        if isinstance(v, str):
            return AggressivenessLevel[v.upper()]
        return AggressivenessLevel(v)

    @field_serializer("aggressiveness")
    @classmethod
    def _serialize_aggressiveness(cls, v: AggressivenessLevel) -> str:
        return v.name.lower()


class Profile(BaseModel):
    """Configuration profile for Amelia execution.

    This model is frozen (immutable) to support the stateless reducer pattern.
    Use model_copy(update={...}) to create modified copies.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    tracker: TrackerType = TrackerType.NOOP
    repo_root: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    retry: RetryConfig = Field(default_factory=RetryConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    pr_autofix: PRAutoFixConfig | None = None

    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get config for an agent with profile-level sandbox and name injected.

        Args:
            agent_name: Name of the agent (e.g., 'architect', 'developer').

        Returns:
            AgentConfig with sandbox and profile_name from this profile.

        Raises:
            ValueError: If agent not configured in this profile.
        """
        if agent_name not in self.agents:
            logger.warning(
                "Agent not configured in profile",
                agent=agent_name,
                profile=self.name,
                available_agents=sorted(self.agents.keys()),
            )
            raise ValueError(f"Agent '{agent_name}' not configured in profile '{self.name}'")
        return self.agents[agent_name].model_copy(
            update={"sandbox": self.sandbox, "profile_name": self.name}
        )


class Settings(BaseModel):
    """Global settings for Amelia."""
    active_profile: str
    profiles: dict[str, Profile]

class Issue(BaseModel):
    """Issue or ticket to be worked on."""
    id: str
    title: str
    description: str
    status: str = "open"


class Design(BaseModel):
    """Design document for implementation.

    Can be user-provided via import or generated by a future Brainstorming pipeline.
    """

    content: str
    source: str = "import"

    @classmethod
    def from_file(cls, path: Path | str) -> "Design":
        """Load design from markdown file."""
        content = Path(path).read_text(encoding="utf-8")
        return cls(content=content, source="file")


class Severity(StrEnum):
    """Severity level for review results.

    Uses standard code review terminology:
    - CRITICAL: Blocking issues that must be fixed
    - MAJOR: Should fix before merging
    - MINOR: Nice to have, suggestions
    - NONE: No issues found
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NONE = "none"


class ReviewResult(BaseModel):
    """Result from a code review."""

    model_config = ConfigDict(frozen=True)

    reviewer_persona: str
    approved: bool
    comments: list[str]
    severity: Severity


def collect_rejected_comments(reviews: list[ReviewResult]) -> list[str]:
    """Aggregate comments from all non-approved reviews.

    Args:
        reviews: List of review results to aggregate.

    Returns:
        Flat list of comment strings from rejected reviews.
    """
    comments: list[str] = []
    for review in reviews:
        if not review.approved:
            comments.extend(review.comments)
    return comments


def collect_all_comments(reviews: list[ReviewResult]) -> list[str]:
    """Aggregate comments from all reviews regardless of approval status.

    Args:
        reviews: List of review results to aggregate.

    Returns:
        Flat list of all comment strings.
    """
    comments: list[str] = []
    for review in reviews:
        comments.extend(review.comments)
    return comments


class PlanValidationResult(BaseModel):
    """Result from plan structure validation.

    Mirrors ReviewResult but for plan quality checks.
    """

    model_config = ConfigDict(frozen=True)

    valid: bool
    issues: list[str]
    severity: Severity


class OracleConsultation(BaseModel):
    """Record of an Oracle consultation for persistence and analytics."""

    timestamp: datetime
    problem: str
    advice: str | None = None
    model: str
    session_id: uuid.UUID
    workflow_id: uuid.UUID | None = None
    tokens: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = None
    files_consulted: list[str] = Field(default_factory=list)
    outcome: Literal["success", "error"] = "success"
    error_message: str | None = None


class AskUserOption(BaseModel):
    """A single selectable option in an ask-user question."""

    label: str
    description: str | None = None


class AskUserQuestionItem(BaseModel):
    """A single question with optional header and selectable options."""

    question: str
    header: str | None = None
    options: list[AskUserOption] = Field(default_factory=list)
    multi_select: bool = False


class AskUserQuestionPayload(BaseModel):
    """Structured payload for interactive ask-user questions."""

    questions: list[AskUserQuestionItem]
