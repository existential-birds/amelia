"""Configuration and shared type definitions for the Amelia orchestrator.

Contains type aliases (DriverType, TrackerType, StrategyType, ExecutionMode) and
Pydantic models (RetryConfig, Profile, Settings, Issue, Design) used throughout
the Amelia agentic coding orchestrator.
"""
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

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


class StreamEventType(StrEnum):
    """Types of streaming events from Claude Code.

    Attributes:
        CLAUDE_THINKING: Claude is analyzing and planning.
        CLAUDE_TOOL_CALL: Claude is calling a tool.
        CLAUDE_TOOL_RESULT: Tool execution result.
        AGENT_OUTPUT: Agent has produced output.
    """
    CLAUDE_THINKING = "claude_thinking"
    CLAUDE_TOOL_CALL = "claude_tool_call"
    CLAUDE_TOOL_RESULT = "claude_tool_result"
    AGENT_OUTPUT = "agent_output"


class StreamEvent(BaseModel, frozen=True):
    """Real-time streaming event from agent execution.

    Attributes:
        id: Unique identifier for this event.
        type: Type of streaming event.
        content: Event content (optional).
        timestamp: When the event occurred.
        agent: Agent name (architect, developer, reviewer).
        workflow_id: Unique workflow identifier.
        tool_name: Name of tool being called/returning (optional).
        tool_input: Input parameters for tool call (optional).
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: StreamEventType
    content: str | None = None
    timestamp: datetime
    agent: str
    workflow_id: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None


StreamEmitter = Callable[[StreamEvent], Awaitable[None]]
"""Type alias for async streaming event emitter function."""
