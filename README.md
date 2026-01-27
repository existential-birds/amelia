# Amelia: Agentic Orchestrator

![Amelia Terminal](docs/design/terminal_screen.jpg)

![Active Workflow](docs/design/amelia_active_workflow.png)

[Amelia](https://en.wikipedia.org/wiki/Amelia_Earhart) is multi-agent orchestration for software development with human-in-the-loop approval gates, defense-in-depth security, and end-to-end observability.

> [!WARNING]
> This project is under active development. APIs and configuration may change between releases.

See the [**Roadmap**](https://existential-birds.github.io/amelia/reference/roadmap) for where we're headed.

## Prerequisites

- **Python 3.12+** - Required for type hints and async features
- **uv** - Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Git** - For version control operations
- **Beagle plugin** - Claude Code plugin with Amelia skills ([install guide](https://github.com/existential-birds/beagle?tab=readme-ov-file#installation))
- **LLM access** - Either:
  - OpenRouter API key (for `api` driver)
  - Claude CLI installed (for `cli` driver)

> [!NOTE]
> **Model selection matters.** The API driver requires models with reliable tool-calling capabilities. Models that don't consistently follow tool-calling instructions may fail to complete tasks. See [Troubleshooting](https://existential-birds.github.io/amelia/guide/troubleshooting#api-driver-agent-fails-to-create-plan-file) for details.

## Quick Start

### 1. Install

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

### 2. Try It Out

Create a new folder and run a task directly—no issue tracker needed:

```bash
mkdir my-app && cd my-app
git init

# Create a profile (first run will prompt interactively, or use flags)
amelia config profile create dev --driver api --model "minimax/minimax-m2" --activate

# Start the server (opens dashboard at localhost:8420)
amelia dev
```

In another terminal, run your first task:

```bash
cd my-app

# Run a task directly with --task
amelia start --task "Create a Python CLI that fetches weather for a city using wttr.in"
```

Watch the Architect plan, approve it in the dashboard, then watch the Developer build it.

### 3. Working with Issues

For real projects, connect to GitHub issues:

```bash
# Create a profile with GitHub tracker (or edit existing via dashboard)
amelia config profile create github-dev --driver api --model "minimax/minimax-m2" --tracker github --activate

# Start a workflow for issue #123
amelia start 123
```

See **[Configuration](https://existential-birds.github.io/amelia/guide/configuration)** for all options including Jira integration and per-agent model settings.

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

Amelia orchestrates specialized agents through a LangGraph state machine:

```
Issue → Architect (plan) → Human Approval → Developer (execute) ↔ Reviewer (review) → Done
```

Architecture is aligned with [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) for reliable LLM-powered software. See [Architecture](https://existential-birds.github.io/amelia/architecture/overview) for data flow and [Concepts](https://existential-birds.github.io/amelia/architecture/concepts) for how agents and drivers work.

## Features

### Quick Shot

Start ad-hoc tasks directly from the sidebar without navigating away from your current workflow.

![Quick Shot](docs/design/quick_shot_feature.png)

### Spec Builder

Brainstorm and refine feature specifications through an interactive chat interface before implementation.

![Spec Builder](docs/design/spec-builder-chat.png)

### Plan View

Review and approve generated implementation plans before execution.

![Plan View](docs/design/hugo_plan.png)

### Prompt Editor

Customize agent prompts directly in the dashboard to tune behavior for your workflow.

![Prompt Editor](docs/design/amelia_prompt_editor.png)

### Streaming Tool Calls and Thinking Tokens

Watch agents work in real-time with streaming tool execution and visible reasoning.

![Streaming Tool Calls](docs/design/hugo_logs_mixed.png)

### Multi-Round Code Review

Iterative review cycles between Developer and Reviewer agents until changes are approved.

![Code Review](docs/design/hugo_logs_filter_agent.png)

### Run Details

Inspect individual agent runs, tool calls, and outputs.

![Details View](docs/design/hugo_details_opus.png)

### Model Comparison

Compare model performance and track token usage across runs.

![Metrics](docs/design/hugo_opus_vs_gemini.jpeg)

### Cost Tracking

Track token usage, costs, and workflow trajectories across all agent runs.

![Costs Overview](docs/design/costs_view.png)

## CLI Commands

```bash
# Server commands
amelia dev                    # Start server + dashboard (port 8420)
amelia server                 # API server only

# Workflow commands (requires server running)
amelia start 123              # Start workflow for issue #123
amelia start --task "desc"    # Run ad-hoc task without issue tracker
amelia start 123 --queue      # Queue workflow for later execution
amelia run abc-123            # Start a queued workflow
amelia status                 # Show active workflows
amelia approve                # Approve the generated plan
amelia reject "feedback"      # Reject with feedback
amelia cancel                 # Cancel active workflow

# Local commands (no server required)
amelia review --local         # Review uncommitted changes
```

See the **[Usage Guide](https://existential-birds.github.io/amelia/guide/usage)** for complete CLI reference, API endpoints, and example workflows.

## Configuration

Configuration is stored in SQLite (`~/.amelia/amelia.db`) and managed via CLI or dashboard:

```bash
# Profile management
amelia config profile list                # List all profiles
amelia config profile create <name>       # Create new profile (interactive)
amelia config profile show <name>         # Show profile details
amelia config profile activate <name>     # Set active profile

# Server settings
amelia config server show                 # Show server settings
amelia config server set <key> <value>    # Update a setting
```

Or use the dashboard at `localhost:8420/settings` to manage profiles and server settings visually.

See [Configuration Reference](https://existential-birds.github.io/amelia/guide/configuration) for full details.

## Documentation

For full documentation, visit **[existential-birds.github.io/amelia](https://existential-birds.github.io/amelia/)**.

## License

Amelia is licensed under the [Apache License 2.0](LICENSE), a permissive open-source license that allows free use, modification, and distribution.
