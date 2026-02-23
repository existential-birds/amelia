"""Configuration and shared type definitions for the Amelia orchestrator.

Contains StrEnum types (DriverType, TrackerType, Severity) and
Pydantic models (RetryConfig, SandboxConfig, Profile, Settings, Issue) used throughout
the Amelia agentic coding orchestrator.
"""
import uuid
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field


# Default allowed hosts for sandbox network allowlist
DEFAULT_NETWORK_ALLOWED_HOSTS: tuple[str, ...] = (
    "api.anthropic.com",
    "openrouter.ai",
    "api.openai.com",
    "github.com",
    "registry.npmjs.org",
    "pypi.org",
    "files.pythonhosted.org",
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


class SandboxConfig(BaseModel):
    """Sandbox execution configuration for a profile.

    Attributes:
        mode: Sandbox mode ('none' = direct execution, 'container' = Docker sandbox).
        image: Docker image for sandbox container.
        network_allowlist_enabled: Whether to restrict outbound network.
        network_allowed_hosts: Hosts allowed when network allowlist is enabled.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["none", "container"] = "none"
    image: str = "amelia-sandbox:latest"
    network_allowlist_enabled: bool = False
    network_allowed_hosts: tuple[str, ...] = Field(
        default_factory=lambda: DEFAULT_NETWORK_ALLOWED_HOSTS,
    )


class AgentConfig(BaseModel):
    """Per-agent driver and model configuration.

    Attributes:
        driver: LLM driver type ('claude', 'codex', or 'api').
        model: LLM model identifier.
        options: Agent-specific options (e.g., max_iterations).
        sandbox: Sandbox execution config (injected by Profile.get_agent_config).
        profile_name: Profile name (injected by Profile.get_agent_config).
    """

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
    """Retry configuration for transient failures.

    Attributes:
        max_retries: Maximum number of retry attempts (0-10).
        base_delay: Base delay in seconds for exponential backoff (0.1-30.0).
        max_delay: Maximum delay cap in seconds (1.0-300.0).
    """

    max_retries: int = Field(
        default=3, ge=0, le=10, description="Maximum number of retry attempts"
    )
    base_delay: float = Field(
        default=1.0, ge=0.1, le=30.0, description="Base delay in seconds for exponential backoff"
    )
    max_delay: float = Field(
        default=60.0, ge=1.0, le=300.0, description="Maximum delay cap in seconds"
    )


class Profile(BaseModel):
    """Configuration profile for Amelia execution.

    This model is frozen (immutable) to support the stateless reducer pattern.
    Use model_copy(update={...}) to create modified copies.

    Attributes:
        name: Profile name (e.g., 'work', 'personal').
        tracker: Issue tracker type (jira, github, noop).
        repo_root: Root directory of the repository this profile targets.
        plan_output_dir: Directory for saving implementation plans.
        plan_path_pattern: Path pattern for plan files with {date} and {issue_key} placeholders.
        retry: Retry configuration for transient failures.
        agents: Per-agent driver and model configuration.
        sandbox: Sandbox execution configuration.
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
    """Global settings for Amelia.

    Attributes:
        active_profile: Name of the currently active profile.
        profiles: Dictionary mapping profile names to Profile objects.
    """
    active_profile: str
    profiles: dict[str, Profile]

class Issue(BaseModel):
    """Issue or ticket to be worked on.

    Attributes:
        id: Unique issue identifier (e.g., 'JIRA-123', 'GH-456').
        title: Issue title or summary.
        description: Detailed issue description.
        status: Current issue status (default: 'open').
    """
    id: str
    title: str
    description: str
    status: str = "open"


class Design(BaseModel):
    """Design document for implementation.

    Can be user-provided via import or generated by a future Brainstorming pipeline.

    Attributes:
        content: The markdown content of the design document.
        source: Where the design came from ("import", "brainstorming", "file").
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
    """Result from a code review.

    Attributes:
        reviewer_persona: The persona or role of the reviewer.
        approved: Whether the review approved the changes.
        comments: List of actionable issues to fix. Filtered at creation time
            to exclude positive observations.
        severity: Severity level of issues found (none, minor, major, critical).
    """

    model_config = ConfigDict(frozen=True)

    reviewer_persona: str
    approved: bool
    comments: list[str]
    severity: Severity


class PlanValidationResult(BaseModel):
    """Result from plan structure validation.

    Mirrors ReviewResult but for plan quality checks.

    Attributes:
        valid: Whether the plan passed all structural checks.
        issues: Human-readable descriptions of problems found.
        severity: Overall severity of issues (none if valid).
    """

    model_config = ConfigDict(frozen=True)

    valid: bool
    issues: list[str]
    severity: Severity


class OracleConsultation(BaseModel):
    """Record of an Oracle consultation for persistence and analytics.

    Attributes:
        timestamp: When the consultation occurred.
        problem: The problem statement submitted.
        advice: The Oracle's advice (None until complete).
        model: LLM model used.
        session_id: UUIDv4, generated per-consultation by Oracle.consult().
        workflow_id: Optional workflow ID for cross-referencing with orchestrator runs.
        tokens: Token counts (e.g., {"input": N, "output": M}).
        cost_usd: Estimated cost in USD.
        files_consulted: File paths included in context.
        outcome: Whether consultation succeeded or errored.
        error_message: Error details if outcome is "error".
    """

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
