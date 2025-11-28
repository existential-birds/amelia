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
    strategy: single          # Single reviewer
    plan_output_template: "plans/{issue_id}.md"  # Where to save plans

  # Personal profile - direct API access
  home:
    name: home
    driver: api:openai        # LLM via OpenAI API
    tracker: github           # Issues from GitHub
    strategy: competitive     # Multiple parallel reviewers
    plan_output_template: "plans/{issue_id}.md"

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

### `profiles.<name>.tracker` (required)

Where Amelia fetches issue details from.

| Value | Description | Requirements |
|-------|-------------|--------------|
| `jira` | Jira issues | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars |
| `github` | GitHub issues | `gh` CLI authenticated or `GITHUB_TOKEN` |
| `noop` | No tracker (manual input) | None |

### `profiles.<name>.strategy` (required)

How code review is performed.

| Value | Description | Behavior |
|-------|-------------|----------|
| `single` | One reviewer pass | General review from single LLM call |
| `competitive` | Multiple parallel reviews | Security, Performance, Usability reviews run concurrently, results aggregated |

### `profiles.<name>.plan_output_template` (optional)

Template for where to save generated plans. Supports `{issue_id}` placeholder.

Default: `"plans/{issue_id}.md"`

```yaml
plan_output_template: "docs/plans/{issue_id}-plan.md"
```

## Environment Variables

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

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | No | GitHub token (alternative to `gh` CLI auth) |

## Validation

Amelia validates profiles on startup:

- All required fields must be present
- Driver and tracker values must be recognized
- Strategy must be `single` or `competitive`

Invalid configuration results in exit code 1 with descriptive error message.

## Example Configurations

### Minimal (API + No Tracker)

For local development and testing without external integrations:

```yaml
active_profile: dev
profiles:
  dev:
    name: dev
    driver: api:openai
    tracker: noop
    strategy: single
```

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
