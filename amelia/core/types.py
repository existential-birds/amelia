from typing import Literal

from pydantic import BaseModel


DriverType = Literal["cli:claude", "api:openai", "cli", "api"]
TrackerType = Literal["jira", "github", "none", "noop"]
StrategyType = Literal["single", "competitive"]

class Profile(BaseModel):
    name: str
    driver: DriverType
    tracker: TrackerType = "none"
    strategy: StrategyType = "single"
    plan_output_template: str = "docs/plans/issue-{issue_id}.md"

class Settings(BaseModel):
    active_profile: str
    profiles: dict[str, Profile]

class Issue(BaseModel):
    id: str
    title: str
    description: str
    status: str = "open"
