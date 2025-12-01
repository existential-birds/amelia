from typing import Literal

from pydantic import BaseModel, Field, model_validator


DriverType = Literal["cli:claude", "cli:claude:agentic", "api:openai", "cli", "api"]
TrackerType = Literal["jira", "github", "none", "noop"]
StrategyType = Literal["single", "competitive"]

class Profile(BaseModel):
    """Configuration profile for Amelia execution.

    Attributes:
        name: Profile name (e.g., 'work', 'personal').
        driver: LLM driver type (e.g., 'api:openai', 'cli:claude').
        tracker: Issue tracker type (jira, github, none, noop).
        strategy: Review strategy (single or competitive).
        plan_output_dir: Directory for storing generated plans.
    """
    name: str
    driver: DriverType
    tracker: TrackerType = "none"
    strategy: StrategyType = "single"
    plan_output_dir: str = "docs/plans"

    @model_validator(mode="after")
    def validate_work_profile_constraints(self) -> "Profile":
        """Enterprise constraint: 'work' profiles cannot use API drivers.

        Returns:
            The validated profile.

        Raises:
            ValueError: If 'work' profile attempts to use an API driver.
        """
        if self.name.lower() == "work" and self.driver.startswith("api"):
            raise ValueError(f"Profile 'work' cannot use API drivers (got '{self.driver}'). Use CLI drivers for enterprise compliance.")
        return self

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
