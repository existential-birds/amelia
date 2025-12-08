# Amelia: Agentic Orchestrator

[Amelia](https://en.wikipedia.org/wiki/Amelia_Earhart) is a local agentic coding system that orchestrates software development tasks through multiple AI agents with specialized roles.

See the [**Roadmap**](docs/roadmap.md) for where we're headed.

**Core Philosophy:** Amelia is built with the assumption that LLMs will continually improve. We prefer prompts over code, delegation over hardcoding, and flexible architectures—so as models get smarter, Amelia automatically improves without requiring changes.

## What is Amelia?

Amelia is an agentic coding orchestrator. Or perhaps it is not. The committee has not yet ruled on this matter, and the relevant forms remain in transit
between departments.

The Facts, Such As They Are:

- I use Amelia every day. This does not mean it works.
- It works for me. This does not mean it is safe.
- It is an experiment. This does not prevent it from being a tool.
- It is a tool. This does not prevent it from being an experiment.

The architect plans. The developer executes. The reviewer reviews. The loop continues until approval is granted or the heat death of the universe,
whichever comes first. No one recalls who wrote the original requirements.

**Official Disclaimer:**

You may use Amelia. You may not use Amelia. Both choices lead to the same corridor, which leads to another corridor. The exit sign is always visible but
somehow never closer.

If Amelia works for you, this is not a guarantee.
If Amelia fails for you, this is also not a guarantee.
The only guarantee is that there are no guarantees, and even this is subject to revision pending review.

_The trial begins tomorrow. It has always been beginning tomorrow._

## Prerequisites

- **Python 3.12+** - Required for type hints and async features
- **uv** - Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Git** - For version control operations
- **LLM access** - Either:
  - OpenAI API key (for `api:openai` driver)
  - Claude CLI installed (for `cli:claude` driver)

## Quick Start

Use Amelia in any existing Git repository to automate development tasks.

![Amelia Terminal](docs/design/terminal_screen.jpg)

![Amelia Dashboard Design Mock](docs/design/desktop_screen.jpg)

### 1. Install Prerequisites

```bash
# Install uv (Linux/macOS)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install amelia as a global tool
uv tool install git+https://github.com/anderskev/amelia.git

# Set your API key
export OPENAI_API_KEY="sk-..."
```

### 2. Configure Your Project

```bash
# Navigate to your project
cd /path/to/your/project

# Create config in your project root
cat > settings.amelia.yaml << 'EOF'
active_profile: dev
profiles:
  dev:
    name: dev
    driver: api:openai
    tracker: github
    strategy: single
EOF
```

See **[Configuration](docs/usage.md#configuration)** for all available parameters including retry settings, execution modes, and driver options.

### 3. Create or Select an Issue

Amelia works on issues from your configured tracker. Create one if needed:

```bash
# Create a new GitHub issue
gh issue create --title "Add user authentication" --body "Implement login/logout functionality"

# Or use an existing issue number
gh issue list
```

### 4. Run Amelia

```bash
# Generate a plan (dry run - no code changes)
amelia plan-only 123

# Execute the full workflow (plan → approve → develop → review)
amelia start 123

# Review uncommitted changes
amelia review --local
```

> **Tip:** Use `tracker: noop` in your config to test without a real issue tracker. This creates a mock issue from the ID you provide.

## Alternative Installation

### Run from Source

If you prefer not to install globally:

```bash
# Clone the repo
git clone https://github.com/anderskev/amelia.git
cd amelia
uv sync

# Run from your project directory
cd /path/to/your/project
/path/to/amelia/uv run amelia plan-only 123
```

Or use the `AMELIA_SETTINGS` environment variable:

```bash
cd /path/to/amelia
AMELIA_SETTINGS=/path/to/your/project/settings.amelia.yaml uv run amelia plan-only 123
```

> **Note:** Amelia reads `settings.amelia.yaml` from the current working directory (or via `AMELIA_SETTINGS`). Run commands from your project root so agents have access to your codebase context.

## How It Works

### Agent Roles

| Agent | Input | Output | Example |
|-------|-------|--------|---------|
| **Architect** | Issue description + codebase context | TaskDAG (ordered tasks with dependencies) | "Add login feature" → 5 tasks: create model, add routes, write tests... |
| **Developer** | Single task from TaskDAG | Code changes via shell/git tools | Executes `git checkout -b`, writes files, runs tests |
| **Reviewer** | Git diff of changes | Approval or rejection with feedback | "Missing input validation in login handler" |

### Why Drivers?

Enterprise environments often prohibit direct API calls to external LLMs. The driver abstraction lets you:

- **`api:openai`** - Direct API calls via pydantic-ai (fastest, requires API key)
- **`cli:claude`** - Wraps Claude CLI (works with enterprise SSO, no API key needed)

Switch drivers without code changes:

```yaml
profiles:
  work:
    driver: cli:claude  # Uses approved enterprise CLI
  home:
    driver: api:openai  # Direct API access
```

## CLI Commands

```bash
# Server commands
amelia dev                    # Start server + dashboard (port 8420)
amelia server                 # API server only

# Workflow commands (requires server running)
amelia start 123              # Start workflow for issue #123
amelia status                 # Show active workflows
amelia approve                # Approve the generated plan
amelia reject "feedback"      # Reject with feedback
amelia cancel                 # Cancel active workflow

# Local commands (no server required)
amelia plan-only 123          # Generate plan without executing
amelia review --local         # Review uncommitted changes
```

See the **[Usage Guide](docs/usage.md)** for complete CLI reference, API endpoints, and example workflows.

## Configuration

Basic `settings.amelia.yaml`:

```yaml
active_profile: home
profiles:
  home:
    name: home
    driver: api:openai
    tracker: github
    strategy: single
```

See [Configuration Reference](docs/configuration.md) for full details.

## Learn More

- **[Usage Guide](docs/usage.md)** - CLI commands, REST API reference, and example workflows
- [Configuration Reference](docs/configuration.md) - Full settings documentation
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [Concepts: Understanding Agentic AI](docs/concepts.md) - How agents, drivers, and orchestration work
- [Architecture & Data Flow](docs/architecture.md) - Technical deep dive with diagrams
- [Roadmap](docs/roadmap.md) - Detailed development phases and vision
- [Benchmarking LLM Agents](docs/benchmarking.md) - How to systematically evaluate and iterate on agents
- [12-Factor Agents Compliance](docs/analysis/12-factor-agents-compliance.md) - How Amelia aligns with the 12-Factor Agents methodology
- [Brainstorming](docs/brainstorming/) - Design explorations created using the superpowers:brainstorming skill

> **Note:** `docs/plans/` contains temporary planning documents for in-progress work. These should be deleted once their corresponding plans are executed and merged.

## Current Status

**What works:**
- Full orchestrator loop with human approval gates (CLI mode)
- CLI driver (Claude CLI wrapper) with structured outputs, streaming, and agentic execution
- Local code review with competitive strategy
- GitHub tracker integration (via `gh` CLI)
- Real tool execution in Developer agent (shell commands, file writes)
- FastAPI server with SQLite persistence and WebSocket event streaming
- Workflow state machine with event tracking

**Limitations:**

_This is an experimental project. Set expectations accordingly._

**Web Dashboard (not ready for use):**
- All pages display "Coming soon" placeholders - no actual workflow data rendered
- API client, WebSocket hooks, and data loaders are implemented but not connected to UI
- Toast notifications only log to console
- Connection status indicator is hardcoded

**API Driver (OpenAI):**
- No agentic execution support (structured mode only)
- API key validation is incomplete
- Less tested than CLI driver

**Orchestrator:**
- Failed tasks permanently block all dependent tasks (no retry or skip mechanism)
- `RetryConfig` is defined but not actually used anywhere
- Server crash recovery is a placeholder (interrupted workflows not recovered)
- Workflow detail API missing token usage and event history

**Not Implemented:**
- Checkpoint resumption after interruption
- Session continuity across runs
- Task prioritization (all ready tasks treated equally)
- Structured error categories or retry strategies
