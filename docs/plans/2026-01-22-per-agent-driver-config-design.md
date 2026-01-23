# Per-Agent Driver Configuration Design

**Issue:** #279
**Date:** 2026-01-22
**Status:** Draft

## Problem

All agents share the same driver and model. This prevents:
- Using different models for different agents (expensive for planning, cheap for validation)
- Mixing CLI and API drivers across agents
- Configuring agent-specific options in a unified way

## Solution

Replace profile-level `driver`/`model` with per-agent configuration via `agents: dict[str, AgentConfig]`.

## Schema

### AgentConfig

```python
class AgentConfig(BaseModel):
    """Per-agent driver and model configuration."""
    driver: DriverType
    model: str
    options: dict[str, Any] = Field(default_factory=dict)
```

### Updated Profile

```python
class Profile(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    tracker: TrackerType = "none"
    working_dir: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    retry: RetryConfig = Field(default_factory=RetryConfig)
    auto_approve_reviews: bool = False

    agents: dict[str, AgentConfig] = Field(default_factory=dict)

    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get config for an agent. Raises if not configured."""
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not configured in profile '{self.name}'")
        return self.agents[agent_name]
```

**Removed fields:**
- `driver` (moved to per-agent)
- `model` (moved to per-agent)
- `validator_model` (now `agents["plan_validator"].model`)
- `max_review_iterations` (now `agents["reviewer"].options["max_iterations"]`)
- `max_task_review_iterations` (now `agents["task_reviewer"].options["max_iterations"]`)

## Database Schema

```sql
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    tracker TEXT NOT NULL,
    working_dir TEXT NOT NULL,
    plan_output_dir TEXT DEFAULT 'docs/plans',
    plan_path_pattern TEXT DEFAULT 'docs/plans/{date}-{issue_key}.md',
    auto_approve_reviews INTEGER DEFAULT 0,
    agents TEXT NOT NULL,  -- JSON blob
    is_active INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
```

## Agent Initialization

Agents receive `AgentConfig` and create their own driver:

```python
class Architect:
    def __init__(self, config: AgentConfig, event_bus=None, prompts=None):
        self.driver = get_driver(config.driver, model=config.model)
        self.options = config.options
        self._event_bus = event_bus
        self._prompts = prompts or {}

class Developer:
    def __init__(self, config: AgentConfig):
        self.driver = get_driver(config.driver, model=config.model)
        self.options = config.options
```

Pipeline nodes pass config to agents:

```python
config = profile.get_agent_config("architect")
architect = Architect(config, event_bus, prompts)
```

## Standard Agent Names

- `brainstormer`
- `architect`
- `plan_validator`
- `developer`
- `task_reviewer`
- `reviewer`

User-defined agents use any name and are configured the same way.

## Testing

Tests mock `get_driver` rather than injecting mock drivers:

```python
with patch("amelia.agents.architect.get_driver") as mock_get_driver:
    mock_get_driver.return_value = mock_driver
    architect = Architect(config)
```

## Files to Change

| File | Change |
|------|--------|
| `amelia/core/types.py` | Add `AgentConfig`; update `Profile` |
| `amelia/agents/architect.py` | Accept `AgentConfig` instead of `DriverInterface` |
| `amelia/agents/developer.py` | Accept `AgentConfig` instead of `DriverInterface` |
| `amelia/agents/reviewer.py` | Accept `AgentConfig` instead of `DriverInterface` |
| `amelia/agents/evaluator.py` | Accept `AgentConfig` (if applicable) |
| `amelia/server/database/profile_repository.py` | Update `ProfileRecord`, JSON serialization |
| `amelia/server/database/connection.py` | Update `CREATE TABLE profiles` |
| `amelia/pipelines/nodes.py` | Use `profile.get_agent_config()`, pass config to agents |
| `amelia/pipelines/implementation/nodes.py` | Same |
| `amelia/pipelines/review/nodes.py` | Same |
| `amelia/server/routes/brainstorm.py` | Use `profile.get_agent_config("brainstormer")` |
| `tests/conftest.py` | Update fixtures, mock `get_driver` |
| `dashboard/` | Update profile editing UI |

## Migration

Breaking change. Delete existing database - no migration needed.

## Design Decisions

1. **No profile-level defaults** - Every agent must be explicitly configured. Fail fast if agent not found.
2. **Agents create own drivers** - Cleaner encapsulation. Agents receive config, not pre-built drivers.
3. **Options dict for agent-specific settings** - Flexible for user-defined agents with custom options.
4. **JSON blob for agents in database** - Simple storage for flexible dict structure.
