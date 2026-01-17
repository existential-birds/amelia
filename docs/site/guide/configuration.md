# Configuration Reference

Complete reference for Amelia's configuration system.

## File Location

Amelia looks for `settings.amelia.yaml` in the current working directory.

## Full Example

```yaml
# Which profile to use when --profile is not specified
active_profile: api_minimax

profiles:
  # CLI profile - uses Claude CLI
  cli_opus:
    name: cli_opus
    driver: cli:claude        # LLM via claude CLI
    model: "opus"
    tracker: jira             # Issues from Jira
    plan_output_dir: "docs/plans"
    max_review_iterations: 5  # More iterations for complex reviews
    retry:
      max_retries: 5          # More retries for rate limits
      base_delay: 2.0
      max_delay: 120.0

  # API profile - direct OpenRouter API access
  api_minimax:
    name: api_minimax
    driver: api:openrouter    # LLM via OpenRouter API
    model: "minimax/minimax-m2"  # Required for API drivers
    tracker: github           # Issues from GitHub
    plan_output_dir: "docs/plans"

  # Testing profile
  api_minimax_test:
    name: api_minimax_test
    driver: api:openrouter
    model: "minimax/minimax-m2"
    tracker: noop             # No real tracker
```

## Profile Structure

### `active_profile` (required)

The default profile to use when `--profile` is not specified.

```yaml
active_profile: api_minimax
```

### `profiles.<name>.name` (required)

Human-readable name for the profile. Should match the key.

```yaml
profiles:
  api_minimax:
    name: api_minimax
```

### `profiles.<name>.driver` (required)

How Amelia communicates with LLMs.

| Value | Description | Requirements | Notes |
|-------|-------------|--------------|-------|
| `api:openrouter` | Direct OpenRouter API calls | `OPENROUTER_API_KEY` env var, `model` field | Full functionality, structured outputs |
| `api` | Alias for `api:openrouter` | Same as above | Shorthand |
| `cli:claude` | Wraps claude CLI tool | `claude` CLI installed & authenticated | Agentic execution via CLI |
| `cli` | Alias for `cli:claude` | Same as above | Shorthand |

### `profiles.<name>.model` (required for API drivers)

The LLM model identifier to use. Required when using `api:openrouter` or `api` drivers.

```yaml
model: "minimax/minimax-m2"
```

Common models:
- `anthropic/claude-sonnet-4.5` - Claude Sonnet 4.5 (recommended)
- `google/gemini-2.5-flash` - Gemini 2.5 Flash (cost-effective)
- `openai/gpt-4o` - GPT-4o

For CLI drivers, specifying the model is optional but recommended for clarity.

### `profiles.<name>.tracker` (optional)

Where Amelia fetches issue details from.

Default: `"none"`

| Value | Description | Requirements |
|-------|-------------|--------------|
| `jira` | Jira issues | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars |
| `github` | GitHub issues | `gh` CLI authenticated (`gh auth login`) |
| `none` | No tracker | None |
| `noop` | Alias for `none` | None |

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

### `profiles.<name>.max_review_iterations` (optional)

Maximum number of review-fix iterations before the workflow terminates. Prevents infinite loops when the Developer and Reviewer can't reach agreement.

Default: `3`

```yaml
max_review_iterations: 5
```

### `profiles.<name>.max_task_review_iterations` (optional)

Maximum review-fix iterations per task in task-based execution mode. When plans contain multiple tasks, each task has its own review cycle with this limit.

Default: `5`

```yaml
max_task_review_iterations: 3
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

### OpenRouter API Driver

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | Your OpenRouter API key |

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
- Driver values must be one of: `api`, `api:openrouter`, `cli`, `cli:claude`
- Tracker values must be one of: `jira`, `github`, `none`, `noop`
- API drivers require the `model` field
- Retry values must be within allowed ranges

Invalid configuration results in exit code 1 with descriptive error message.

## Example Configurations

### Minimal

Only `name` and `driver` are required. All other fields use sensible defaults:

```yaml
active_profile: cli_opus
profiles:
  cli_opus:
    name: cli_opus
    driver: cli:claude  # CLI driver doesn't require model field
```

For API drivers, you must also specify the model:

```yaml
active_profile: api_minimax
profiles:
  api_minimax:
    name: api_minimax
    driver: api:openrouter
    model: "minimax/minimax-m2"
```

This uses: `tracker: none`, default retry settings.

### CLI with Jira

CLI driver with Jira issue tracking:

```yaml
active_profile: cli_opus
profiles:
  cli_opus:
    name: cli_opus
    driver: cli:claude
    model: "opus"
    tracker: jira
    max_review_iterations: 5
```

### Multi-Profile Setup

For developers working across different contexts:

```yaml
active_profile: api_minimax

profiles:
  cli_opus:
    name: cli_opus
    driver: cli:claude
    model: "opus"
    tracker: jira

  api_minimax:
    name: api_minimax
    driver: api:openrouter
    model: "minimax/minimax-m2"
    tracker: github

  api_minimax_test:
    name: api_minimax_test
    driver: api:openrouter
    model: "minimax/minimax-m2"
    tracker: noop
```

Usage:

```bash
amelia start PROJ-123              # Uses active_profile: api_minimax
amelia start PROJ-123 -p cli_opus  # Uses cli_opus profile
amelia review --local -p api_minimax_test  # Uses api_minimax_test profile
```

## Troubleshooting

### "Profile not found"

Ensure the profile name matches exactly (case-sensitive) in both `active_profile` and `profiles` keys.

### "Driver not recognized"

Valid driver values are: `api`, `api:openrouter`, `cli`, `cli:claude`

### "Missing model field"

API drivers (`api:openrouter`, `api`) require the `model` field:

```yaml
driver: api:openrouter
model: "minimax/minimax-m2"
```

### "Missing OPENROUTER_API_KEY"

Set the environment variable:

```bash
export OPENROUTER_API_KEY="sk-..."
```

### "Jira authentication failed"

Verify all three Jira environment variables are set correctly:

```bash
export JIRA_BASE_URL="https://your-company.atlassian.net"
export JIRA_EMAIL="your.email@company.com"
export JIRA_API_TOKEN="your-api-token"
```

Generate an API token at: https://id.atlassian.com/manage-profile/security/api-tokens
