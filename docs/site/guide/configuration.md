---
title: Configuration Reference
description: Configure Amelia's agent orchestration profiles, LLM drivers, issue trackers, and server settings for your development environment.
---

# Configuration Reference

Complete reference for Amelia's configuration system.

## Overview

Amelia stores all configuration in a SQLite database (`~/.amelia/amelia.db`). Configuration is managed through:

- **CLI**: `amelia config profile` and `amelia config server` commands
- **Dashboard**: Settings page at `/settings` with Profiles and Server tabs

## Profile Management

Profiles define how Amelia connects to LLMs and issue trackers for different projects or environments.

### List Profiles

```bash
amelia config profile list
```

Shows all profiles with their driver, model, tracker, and agent count.

### Show Profile Details

```bash
amelia config profile show <name>
```

Displays full profile configuration including per-agent settings.

### Create Profile

```bash
# Interactive mode (prompts for all options)
amelia config profile create my-profile

# With flags (non-interactive)
amelia config profile create my-profile \
  --driver api \
  --model "minimax/minimax-m2" \
  --tracker github \
  --repo-root /path/to/project \
  --activate
```

| Flag | Short | Description |
|------|-------|-------------|
| `--driver` | `-d` | LLM driver (`claude`, `codex`, or `api`) |
| `--model` | `-m` | Model name (required for API drivers) |
| `--tracker` | `-t` | Issue tracker (`none`, `github`, `jira`) |
| `--repo-root` | `-w` | Repository root path for agent execution |
| `--activate` | `-a` | Set as active profile after creation |

### Activate Profile

```bash
amelia config profile activate <name>
```

Sets the default profile used when `--profile` is not specified.

### Delete Profile

```bash
amelia config profile delete <name>
```

Removes a profile from the database.

## Profile Fields

### Driver (required)

How Amelia communicates with LLMs.

| Value | Description | Requirements |
|-------|-------------|--------------|
| `api` | Direct OpenRouter API calls | `OPENROUTER_API_KEY` env var, `model` field |
| `claude` | Claude CLI wrapper | `claude` CLI installed and authenticated |
| `codex` | OpenAI Codex CLI wrapper | `codex` CLI installed and authenticated |

### Model (required for API drivers)

The LLM model identifier. Required when using `api` driver.

Common models:
- `anthropic/claude-sonnet-4.5` - Claude Sonnet 4.5 (recommended)
- `google/gemini-2.5-flash` - Gemini 2.5 Flash (cost-effective)
- `minimax/minimax-m2` - MiniMax M2

For `claude` and `codex` drivers, model is optional but helps with clarity.

### Tracker

Where Amelia fetches issue details from.

| Value | Description | Requirements |
|-------|-------------|--------------|
| `github` | GitHub issues | `gh` CLI authenticated (`gh auth login`) |
| `jira` | Jira issues | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars |
| `none` | No tracker | None (use `--task` for ad-hoc tasks) |

### Repository Root

The root directory of the repository this profile targets. When set, the Developer agent operates from this path.

Default: Current working directory where commands are run.

### Plan Output Directory

Directory for storing generated plans.

Default: `docs/plans`

### Auto Approve Reviews

When enabled, automatically approves passing reviews without human intervention.

Default: `false`

### Sandbox Configuration

Sandbox settings control how agents execute code. Configuration is set at the profile level and inherited by all agents. Per-agent sandbox overrides are also supported (see [Per-Agent Configuration](#per-agent-configuration)).

::: warning Driver Restriction
Only the `api` driver works inside sandboxes. The `claude` and `codex` drivers are CLI-based and cannot be used with `container` or `daytona` sandbox modes.
:::

#### Sandbox Mode

| Value | Description |
|-------|-------------|
| `none` | Direct execution on the host (default) |
| `container` | Local Docker sandbox |
| `daytona` | Daytona cloud sandbox |

#### Container Mode Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `image` | string | `amelia-sandbox:latest` | Docker image for the sandbox container |
| `network_allowlist_enabled` | bool | `true` | Enable iptables-based outbound network filtering |
| `network_allowed_hosts` | list | See below | Hosts allowed when network filtering is enabled |

Default allowed hosts when `network_allowlist_enabled` is `true`:

- `api.anthropic.com`
- `openrouter.ai`
- `api.openai.com`
- `github.com`
- `registry.npmjs.org`
- `pypi.org`
- `files.pythonhosted.org`
- `app.daytona.io`

::: info Proxy Security
The LLM proxy enforces a 10 MB request body size limit and sanitizes upstream error messages to prevent information leakage. When sandbox containers are provisioned, each receives a unique authentication token (`AMELIA_PROXY_TOKEN`) that must be included in proxy requests via the `X-Amelia-Proxy-Token` header. This is handled automatically by the sandbox worker.
:::

#### Daytona Mode Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `repo_url` | string | — | Git remote URL to clone into the sandbox (**required**) |
| `daytona_api_url` | string | `https://app.daytona.io/api` | Daytona API endpoint |
| `daytona_target` | string | `us` | Daytona target region (`us` or `eu`) |
| `daytona_resources` | object | See below | CPU, memory, and disk allocation |
| `daytona_image` | string | `python:3.12-slim` | Base Docker image for Daytona workspace |
| `daytona_snapshot` | string | — | Pre-built Daytona snapshot name for faster startup |
| `daytona_timeout` | float | `120` | Sandbox creation timeout in seconds |

Default `daytona_resources`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cpu` | int | `2` | Number of CPU cores |
| `memory` | int | `4` | Memory in GB |
| `disk` | int | `10` | Disk space in GB |

::: info
`network_allowlist_enabled` is not supported with Daytona sandboxes. Daytona manages its own network isolation.
:::

## Per-Agent Configuration

Each profile can configure individual agents with different drivers and models. This allows mixing `claude`, `codex`, and `api` drivers within a single profile, or using different models for different agents.

View agent configurations:

```bash
amelia config profile show <name>
```

Example output:

```text
Agent Configurations
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Agent          ┃ Driver         ┃ Model                  ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ architect      │ claude        │ opus                   │
│ developer      │ api           │ qwen/qwen3-coder-flash │
│ reviewer       │ claude        │ opus                   │
└────────────────┴────────────────┴────────────────────────┘
```

Per-agent configuration can be edited via the dashboard at `/settings/profiles`. Each agent can also override the profile-level sandbox configuration with its own `sandbox` settings.

## Server Settings

Server settings control runtime behavior and are separate from profile configuration.

### Show Settings

```bash
amelia config server show
```

### Set a Value

```bash
amelia config server set <key> <value>
```

### Available Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `log_retention_days` | int | `30` | Days to retain event logs |
| `log_retention_max_events` | int | `100000` | Max events per workflow |
| `trace_retention_days` | int | `7` | Days to retain trace-level events |
| `checkpoint_retention_days` | int | `0` | Days to retain LangGraph checkpoints |
| `checkpoint_path` | path | `~/.amelia/checkpoints.db` | Checkpoint database location |
| `websocket_idle_timeout_seconds` | float | `300.0` | WebSocket idle timeout |
| `workflow_start_timeout_seconds` | float | `60.0` | Workflow start timeout |
| `max_concurrent` | int | `5` | Max concurrent workflows |

Example:

```bash
# Allow more concurrent workflows
amelia config server set max_concurrent 10

```

## Environment Variable Overrides

Server settings can also be overridden via environment variables with the `AMELIA_` prefix:

| Variable | Description |
|----------|-------------|
| `AMELIA_HOST` | Server bind address (default: `127.0.0.1`) |
| `AMELIA_PORT` | Server port (default: `8420`) |
| `AMELIA_DATABASE_PATH` | SQLite database location |
| `AMELIA_LOG_RETENTION_DAYS` | Days to retain logs |
| `AMELIA_MAX_CONCURRENT` | Max concurrent workflows |

Environment variables take precedence over database settings.

## Required Environment Variables

### OpenRouter API Driver

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | Your OpenRouter API key |

### Jira Tracker

| Variable | Description |
|----------|-------------|
| `JIRA_BASE_URL` | Jira instance URL (e.g., `https://company.atlassian.net`) |
| `JIRA_EMAIL` | Your Jira email |
| `JIRA_API_TOKEN` | Jira API token |

### GitHub Tracker

The GitHub tracker requires the `gh` CLI to be installed and authenticated:

```bash
gh auth login
```

### Daytona Cloud Sandbox

| Variable | Description |
|----------|-------------|
| `DAYTONA_API_KEY` | API key for Daytona cloud sandbox authentication |
| `AMELIA_GITHUB_TOKEN` or `GITHUB_TOKEN` | Token for cloning private repos into Daytona sandboxes |

### Provider Error Detection

| Variable | Description |
|----------|-------------|
| `AMELIA_PROVIDER_ERROR_PATTERNS` | Comma-separated list of custom error patterns for provider error detection (lowercase). Overrides built-in defaults. |

## Dashboard Configuration

The dashboard provides a visual interface for managing configuration at `/settings`:

### Profiles Tab

- View all profiles as cards showing driver, agents, and repository root
- Filter profiles by driver type (`claude`, `codex`, or `api`)
- Create new profiles with the "+ Create Profile" button
- Click a profile card to edit its settings
- Set active profile

### Server Tab

- Adjust retention policies (log, trace)
- Set execution limits (max concurrent workflows)
- Toggle debugging options

## Example

```bash
# Create a profile for your project
amelia config profile create myproject \
  --driver api \
  --model "minimax/minimax-m2" \
  --tracker github \
  --repo-root /path/to/myproject \
  --activate

# Verify the profile
amelia config profile show myproject
```

For a full walkthrough including server startup and workflow execution, see the [Usage Guide](/guide/usage).

## Troubleshooting

For configuration-related errors ("Profile not found", "Driver not recognized", "Missing model field", "Missing API key"), see [Troubleshooting — Configuration Issues](/guide/troubleshooting#configuration-issues).
