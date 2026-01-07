"""Configuration and shared type definitions for the Amelia orchestrator.

Contains type aliases (DriverType, TrackerType, StrategyType) and
Pydantic models (RetryConfig, Profile, Settings, Issue, Design) used throughout
the Amelia agentic coding orchestrator.
"""
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DriverType = Literal["cli:claude", "api:openrouter", "cli", "api"]
TrackerType = Literal["jira", "github", "none", "noop"]
StrategyType = Literal["single", "competitive"]


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
        driver: LLM driver type (e.g., 'api:openrouter', 'cli:claude').
        model: LLM model identifier. For cli:claude use 'sonnet', 'opus', or 'haiku'.
            For api:openrouter use 'provider:model' format (e.g., 'anthropic/claude-3.5-sonnet').
        tracker: Issue tracker type (jira, github, none, noop).
        strategy: Review strategy (single or competitive).
        working_dir: Working directory for agentic execution.
        plan_output_dir: Directory for saving implementation plans (default: docs/plans).
        plan_path_pattern: Path pattern for plan files with {date} and {issue_key} placeholders.
        retry: Retry configuration for transient failures.
        max_review_iterations: Maximum review-fix loop iterations before terminating.
        auto_approve_reviews: Skip human approval steps in review workflow.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    driver: DriverType
    model: str
    tracker: TrackerType = "none"
    strategy: StrategyType = "single"
    working_dir: str | None = None
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    validator_model: str | None = None
    """Optional model for plan validation. Uses a fast/cheap model for extraction.
    If not set, falls back to profile.model."""
    retry: RetryConfig = Field(default_factory=RetryConfig)
    max_review_iterations: int = 3
    auto_approve_reviews: bool = False

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
    """Structured design from brainstorming output.

    Attributes:
        title: Design title.
        goal: Overall goal or objective.
        architecture: Architectural approach and patterns.
        tech_stack: List of technologies to be used.
        components: List of components or modules.
        data_flow: Optional description of data flow.
        error_handling: Optional error handling strategy.
        testing_strategy: Optional testing approach.
        relevant_files: List of relevant files in the codebase.
        conventions: Optional coding conventions to follow.
        raw_content: Raw unprocessed design content.
    """
    title: str
    goal: str
    architecture: str
    tech_stack: list[str]
    components: list[str]
    data_flow: str | None = None
    error_handling: str | None = None
    testing_strategy: str | None = None
    relevant_files: list[str] = Field(default_factory=list)
    conventions: str | None = None
    raw_content: str


StageEventEmitter = Callable[[str], Awaitable[None]]
"""Type alias for async stage event emitter function.

Takes the stage name (e.g., "architect_node") and emits a STAGE_STARTED event.
This allows nodes to emit stage start events when they actually begin execution,
rather than relying on the streaming consumer to predict the next stage.
"""
