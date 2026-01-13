# Per-Agent Driver Configuration

**Date:** 2026-01-12
**Status:** Draft
**Author:** Claude + ka

## Problem

Currently, all agents (Architect, Developer, Reviewer) share the same driver and model specified at the profile level. This prevents mixing CLI and API drivers across agents, which is needed for:

- **Vendor flexibility** - Use Claude CLI for some agents (compliance/audit trail) and API for others (speed/cost)
- **Model matching** - Use expensive models for planning, cheaper models for execution/review

## Solution

Inline per-agent configuration in profiles. Each agent gets its own `driver`, `model`, and agent-specific settings.

## Configuration Schema

```yaml
active_profile: work

profiles:
  work:
    name: work
    architect:
      driver: cli:claude
      model: opus
      validator_model: haiku  # optional, architect-specific
    developer:
      driver: api:openrouter
      model: claude-3-5-haiku-20241022
    reviewer:
      driver: api:openrouter
      model: z-ai/glm-4.7
      max_iterations: 3  # optional, reviewer-specific
    tracker: github
    working_dir: /path/to/repo
    plan_output_dir: docs/plans
```

## Pydantic Models

```python
class ArchitectConfig(BaseModel):
    """Architect agent configuration."""
    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str
    validator_model: str | None = None


class DeveloperConfig(BaseModel):
    """Developer agent configuration."""
    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str


class ReviewerConfig(BaseModel):
    """Reviewer agent configuration."""
    model_config = ConfigDict(frozen=True)

    driver: DriverType
    model: str
    max_iterations: int = 3


class Profile(BaseModel):
    """Profile with inline per-agent configuration."""
    model_config = ConfigDict(frozen=True)

    name: str
    architect: ArchitectConfig
    developer: DeveloperConfig
    reviewer: ReviewerConfig

    # Non-agent settings
    tracker: TrackerType = "none"
    working_dir: str | None = None
    plan_output_dir: str = "docs/plans"
    # ... other existing fields

    # Legacy fields - detect and error
    driver: DriverType | None = None
    model: str | None = None

    @model_validator(mode='after')
    def reject_legacy_config(self) -> 'Profile':
        if self.driver or self.model:
            raise ValueError(
                f"Profile '{self.name}' uses deprecated flat config. "
                f"Please update to per-agent configuration:\n\n"
                f"  {self.name}:\n"
                f"    architect:\n"
                f"      driver: {self.driver or 'cli:claude'}\n"
                f"      model: {self.model or 'opus'}\n"
                f"    developer:\n"
                f"      driver: {self.driver or 'cli:claude'}\n"
                f"      model: {self.model or 'opus'}\n"
                f"    reviewer:\n"
                f"      driver: {self.driver or 'cli:claude'}\n"
                f"      model: {self.model or 'opus'}\n"
                f"    tracker: ...\n\n"
                f"See docs/configuration.md for details."
            )
        return self
```

## Orchestrator Changes

Each node uses its agent's config:

```python
async def call_architect_node(state: ExecutionState, config: RunnableConfig):
    profile = _extract_config_params(config)[2]
    driver = DriverFactory.get_driver(
        profile.architect.driver,
        model=profile.architect.model
    )
    architect = Architect(
        driver,
        validator_model=profile.architect.validator_model,
        # ...
    )

async def call_developer_node(state: ExecutionState, config: RunnableConfig):
    profile = _extract_config_params(config)[2]
    driver = DriverFactory.get_driver(
        profile.developer.driver,
        model=profile.developer.model
    )
    developer = Developer(driver)

async def call_reviewer_node(state: ExecutionState, config: RunnableConfig):
    profile = _extract_config_params(config)[2]
    driver = DriverFactory.get_driver(
        profile.reviewer.driver,
        model=profile.reviewer.model
    )
    reviewer = Reviewer(
        driver,
        max_iterations=profile.reviewer.max_iterations,
        # ...
    )
```

## Migration

No backwards compatibility. Old configs get a helpful error message showing exactly how to convert to the new format.

## Files to Change

| File | Change |
|------|--------|
| `amelia/core/types.py` | Add `ArchitectConfig`, `DeveloperConfig`, `ReviewerConfig`; update `Profile` |
| `amelia/core/orchestrator.py` | Update node functions to use `profile.<agent>.driver` |
| `settings.amelia.yaml` | Update to new nested structure |
| `tests/conftest.py` | Update `mock_profile` fixture |
| `docs/configuration.md` | Document new config format |

## Not in Scope

- Reusable config presets (add later if repetition becomes painful)
- Per-agent custom prompts (already exists via `prompts` dict)

## Design Decisions

1. **Inline over references** - Chose simplicity over DRY. Most users have 1-2 profiles; repetition isn't a problem.
2. **Strict typing** - Each agent has its own config type with validated fields. Prevents silent failures from typos.
3. **Breaking change** - No auto-migration. Helpful error message guides users to update.
