# Configuration Reference

Complete reference for Amelia's configuration system.

## File Location

Amelia looks for `settings.amelia.yaml` in the current working directory.

## Full Example

```yaml
# Which profile to use when --profile is not specified
active_profile: home

profiles:
  # Enterprise profile - uses CLI tools for compliance
  work:
    name: work
    driver: cli:claude        # LLM via claude CLI
    tracker: jira             # Issues from Jira
    strategy: competitive     # Multiple parallel reviewers
    execution_mode: structured
    plan_output_dir: "docs/plans"
    retry:
      max_retries: 5          # More retries for enterprise API limits
      base_delay: 2.0
      max_delay: 120.0

  # Personal profile - direct API access
  home:
    name: home
    driver: api:openai        # LLM via OpenAI API
    tracker: github           # Issues from GitHub
    strategy: single          # Single reviewer
    execution_mode: structured
    plan_output_dir: "docs/plans"

  # Testing profile
  test:
    name: test
    driver: api:openai
    tracker: noop             # No real tracker
    strategy: single
```

## Profile Structure

### `active_profile` (required)

The default profile to use when `--profile` is not specified.

```yaml
active_profile: home
```

### `profiles.<name>.name` (required)

Human-readable name for the profile. Should match the key.

```yaml
profiles:
  home:
    name: home
```

### `profiles.<name>.driver` (required)

How Amelia communicates with LLMs.

| Value | Description | Requirements | Notes |
|-------|-------------|--------------|-------|
| `api:openai` | Direct OpenAI API calls | `OPENAI_API_KEY` env var | Full functionality, structured outputs |
| `api` | Alias for `api:openai` | Same as above | Shorthand |
| `cli:claude` | Wraps claude CLI tool | `claude` CLI installed & authenticated | LLM generation is stub, tool execution works |
| `cli` | Alias for `cli:claude` | Same as above | Shorthand |

### `profiles.<name>.tracker` (optional)

Where Amelia fetches issue details from.

Default: `"none"`

| Value | Description | Requirements |
|-------|-------------|--------------|
| `jira` | Jira issues | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars |
| `github` | GitHub issues | `gh` CLI authenticated (`gh auth login`) |
| `none` | No tracker | None |
| `noop` | Alias for `none` | None |

### `profiles.<name>.strategy` (optional)

How code review is performed.

Default: `"single"`

| Value | Description | Behavior |
|-------|-------------|----------|
| `single` | One reviewer pass | General review from single LLM call |
| `competitive` | Multiple parallel reviews | Security, Performance, Usability reviews run concurrently, results aggregated |

### `profiles.<name>.execution_mode` (optional)

How the Developer agent executes tasks.

Default: `"structured"`

| Value | Description | Behavior |
|-------|-------------|----------|
| `structured` | Task-based execution | Developer executes tasks from the Architect's plan sequentially |
| `agentic` | Autonomous execution | Developer has more freedom to determine how to accomplish goals |

### `profiles.<name>.plan_output_dir` (optional)

Directory for storing generated plans.

Default: `"docs/plans"`

```yaml
plan_output_dir: "plans"
```

### `profiles.<name>.working_dir` (optional)

Working directory for agentic execution. When set, the Developer agent operates from this directory.

Default: `null` (uses current working directory)

```yaml
working_dir: "/path/to/project"
```

### `profiles.<name>.retry` (optional)

Retry configuration for transient failures (e.g., API rate limits, network errors).

Default values shown below:

```yaml
retry:
  max_retries: 3      # Maximum retry attempts (0-10)
  base_delay: 1.0     # Base delay in seconds for exponential backoff (0.1-30.0)
  max_delay: 60.0     # Maximum delay cap in seconds (1.0-300.0)
```

Retries use exponential backoff: delay = min(base_delay * 2^attempt, max_delay)

## Server Configuration

The Amelia server (API + WebSocket) can be configured via environment variables with the `AMELIA_` prefix.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AMELIA_HOST` | string | `127.0.0.1` | Server bind address |
| `AMELIA_PORT` | int | `8420` | Server port (1-65535) |
| `AMELIA_DATABASE_PATH` | path | `~/.amelia/amelia.db` | SQLite database location |
| `AMELIA_LOG_RETENTION_DAYS` | int | `30` | Days to retain event logs (minimum 1) |
| `AMELIA_LOG_RETENTION_MAX_EVENTS` | int | `100000` | Max events per workflow (minimum 1000) |
| `AMELIA_WEBSOCKET_IDLE_TIMEOUT_SECONDS` | float | `300.0` | WebSocket idle timeout in seconds |
| `AMELIA_WORKFLOW_START_TIMEOUT_SECONDS` | float | `60.0` | Workflow start timeout in seconds |
| `AMELIA_MAX_CONCURRENT` | int | `5` | Max concurrent workflows (minimum 1) |

Example:

```bash
# Run server on a different port
export AMELIA_PORT=9000
amelia server

# Use custom database location
export AMELIA_DATABASE_PATH=/var/lib/amelia/db.sqlite
amelia server

# Allow more concurrent workflows
export AMELIA_MAX_CONCURRENT=10
amelia server
```

## Environment Variables

### General

| Variable | Required | Description |
|----------|----------|-------------|
| `AMELIA_SETTINGS` | No | Custom path to settings.amelia.yaml (default: `./settings.amelia.yaml`) |

### OpenAI API Driver

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |

### Jira Tracker

| Variable | Required | Description |
|----------|----------|-------------|
| `JIRA_BASE_URL` | Yes | Jira instance URL (e.g., `https://company.atlassian.net`) |
| `JIRA_EMAIL` | Yes | Your Jira email |
| `JIRA_API_TOKEN` | Yes | Jira API token |

### GitHub Tracker

The GitHub tracker requires the `gh` CLI to be installed and authenticated:

```bash
gh auth login
```

## Validation

Amelia validates profiles on startup:

- Required fields (`name`, `driver`) must be present
- Driver values must be one of: `api`, `api:openai`, `cli`, `cli:claude`
- Tracker values must be one of: `jira`, `github`, `none`, `noop`
- Strategy must be `single` or `competitive`
- Execution mode must be `structured` or `agentic`
- Retry values must be within allowed ranges

Invalid configuration results in exit code 1 with descriptive error message.

## Example Configurations

### Minimal

Only `name` and `driver` are required. All other fields use sensible defaults:

```yaml
active_profile: dev
profiles:
  dev:
    name: dev
    driver: api:openai
```

This uses: `tracker: none`, `strategy: single`, `execution_mode: structured`, default retry settings.

### Enterprise (CLI + Jira)

For corporate environments with existing tool approvals:

```yaml
active_profile: work
profiles:
  work:
    name: work
    driver: cli:claude
    tracker: jira
    strategy: competitive
```

### Multi-Profile Setup

For developers working across different contexts:

```yaml
active_profile: home

profiles:
  work:
    name: work
    driver: cli:claude
    tracker: jira
    strategy: competitive

  home:
    name: home
    driver: api:openai
    tracker: github
    strategy: single

  test:
    name: test
    driver: api:openai
    tracker: noop
    strategy: single
```

Usage:

```bash
amelia start PROJ-123              # Uses active_profile (home)
amelia start PROJ-123 -p work      # Uses work profile
amelia review --local -p test      # Uses test profile
```

## Troubleshooting

### "Profile not found"

Ensure the profile name matches exactly (case-sensitive) in both `active_profile` and `profiles` keys.

### "Driver not recognized"

Valid driver values are: `api`, `api:openai`, `cli`, `cli:claude`

### "Missing OPENAI_API_KEY"

Set the environment variable:

```bash
export OPENAI_API_KEY="sk-..."
```

### "Jira authentication failed"

Verify all three Jira environment variables are set correctly:

```bash
export JIRA_BASE_URL="https://your-company.atlassian.net"
export JIRA_EMAIL="your.email@company.com"
export JIRA_API_TOKEN="your-api-token"
```

Generate an API token at: https://id.atlassian.com/manage-profile/security/api-tokens
