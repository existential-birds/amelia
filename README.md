# Amelia: Agentic Orchestrator

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/existential-birds/amelia)

[Amelia](https://en.wikipedia.org/wiki/Amelia_Earhart) is multi-agent orchestration for software development with human-in-the-loop approval gates, defense-in-depth security, and end-to-end observability.

> [!WARNING]
> This project is under active development. APIs and configuration may change between releases. See the [Roadmap](https://existential-birds.github.io/amelia/reference/roadmap) for planned changes.

## Prerequisites

- **Python 3.12+**
- **uv** - Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Git**
- **LLM access** - one of:
  - OpenRouter API key (for `api` driver)
  - Claude CLI (for `claude` driver)
  - Codex CLI (for `codex` driver)

> [!NOTE]
> **Model selection matters.** The `api` driver requires models with reliable tool-calling capabilities. See [Troubleshooting](https://existential-birds.github.io/amelia/guide/troubleshooting#api-driver-agent-fails-to-create-plan-file) for details.

## Quick Start

### 1. Install Amelia

```bash
# Install uv (Linux/macOS)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install amelia
uv tool install git+https://github.com/existential-birds/amelia.git

# Set your API key
export OPENROUTER_API_KEY="sk-..."
```

> [!IMPORTANT]
> For Claude Code users: install the [Beagle plugin](https://github.com/existential-birds/beagle?tab=readme-ov-file#installation) for Amelia skills and commands.

### 2. Run Your First Task

```bash
mkdir my-app && cd my-app
git init

# Create a profile
amelia config profile create dev --driver api --model "minimax/minimax-m2" --activate

# Start the server (opens dashboard at localhost:8420)
amelia dev
```

In another terminal:

```bash
cd my-app
amelia start --task "Create a Python CLI that fetches weather for a city using wttr.in"
```

The Architect agent creates a plan. Open the dashboard at `localhost:8420` to review and approve it. Once approved, the Developer agent implements the code.

### 3. Use an Issue Tracker

To work from GitHub or Jira issues instead of ad-hoc tasks, create a profile with a tracker:

```bash
amelia config profile create github-dev --driver api --model "minimax/minimax-m2" --tracker github --activate

# Start a workflow for issue #123
amelia start 123
```

You can also configure profiles in the dashboard at `localhost:8420/settings`. See **[Configuration](https://existential-birds.github.io/amelia/guide/configuration)** for all options including Jira integration and per-agent model settings.

## Alternative Installation

### Run from Source

```bash
# Clone the repo
git clone https://github.com/existential-birds/amelia.git
cd amelia
uv sync

# Run from your project directory
cd /path/to/your/project
/path/to/amelia/uv run amelia dev
```

> [!NOTE]
> Run commands from your project root—agents can't help with code they can't see. Configuration is stored in `~/.amelia/amelia.db` and shared across all projects.

## How It Works

Amelia orchestrates three specialized agents through a LangGraph state machine:

```
Issue → Architect (plan) → Human Approval → Developer (execute) ↔ Reviewer (review) → Done
```

- **Architect** — reads the issue and produces a step-by-step implementation plan
- **Developer** — executes the plan, writing code and running commands
- **Reviewer** — reviews the Developer's changes and requests fixes if needed

You approve the Architect's plan before any code is written. The design follows [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) principles for reliable LLM-powered software.

See [Architecture](https://existential-birds.github.io/amelia/architecture/overview) and [Concepts](https://existential-birds.github.io/amelia/architecture/concepts) for details.

## CLI Commands

**Server**

| Command | Description |
|---------|-------------|
| `amelia dev` | Start server + dashboard (port 8420) |
| `amelia server` | API server only |

**Workflows** (requires server running)

| Command | Description |
|---------|-------------|
| `amelia start 123` | Start workflow for issue #123 |
| `amelia start --task "desc"` | Run ad-hoc task without issue tracker |
| `amelia start 123 --queue` | Queue workflow for later execution |
| `amelia run abc-123` | Start a queued workflow |
| `amelia status` | Show active workflows |
| `amelia approve` | Approve the generated plan |
| `amelia reject "feedback"` | Reject with feedback |
| `amelia cancel` | Cancel active workflow |

**Local** (no server required)

| Command | Description |
|---------|-------------|
| `amelia review --local` | Review uncommitted changes |

See the **[Usage Guide](https://existential-birds.github.io/amelia/guide/usage)** for the complete CLI reference.

## Configuration

Configuration is stored in SQLite (`~/.amelia/amelia.db`) and managed via CLI (`amelia config`) or the dashboard at `localhost:8420/settings`.

See [Configuration Reference](https://existential-birds.github.io/amelia/guide/configuration) for profile setup, server settings, and Jira integration.

## Documentation

For full documentation, visit **[existential-birds.github.io/amelia](https://existential-birds.github.io/amelia/)**.

## License

Amelia is licensed under the [Apache License 2.0](LICENSE), a permissive open-source license that allows free use, modification, and distribution.
