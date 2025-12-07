# Amelia: Agentic Orchestrator

[Amelia](https://en.wikipedia.org/wiki/Amelia_Earhart) is a local agentic coding system that orchestrates software development tasks through multiple AI agents with specialized roles.

## What is Amelia?

Amelia automates development workflows (issue analysis, planning, coding, review) while respecting enterprise constraints. It uses **agentic orchestration** - multiple AI agents coordinate to accomplish complex tasks.

**Core Philosophy:** Amelia is built with the assumption that LLMs will continually improve. We prefer prompts over code, delegation over hardcoding, and flexible architectures—so as models get smarter, Amelia automatically gets better without requiring changes.

```
Issue → Architect (plan) → Human Approval → Developer (execute) ↔ Reviewer (review) → Done
```

![Amelia Terminal](docs/design/terminal_screen.jpg)

![Amelia Dashboard Design Mock](docs/design/design_mock.jpg)

## Prerequisites

- **Python 3.12+** - Required for type hints and async features
- **uv** - Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Git** - For version control operations
- **LLM access** - Either:
  - OpenAI API key (for `api:openai` driver)
  - Claude CLI installed (for `cli:claude` driver)

## Quick Start

Use Amelia in any existing Git repository to automate development tasks.

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

### `amelia start <ISSUE_ID> [--profile <NAME>]`

Runs the full orchestrator loop:
1. Fetches issue from configured tracker
2. Architect generates TaskDAG (list of tasks with dependencies)
3. Prompts for human approval
4. Developer executes tasks (can run in parallel if no dependencies)
5. Reviewer evaluates changes
6. Loops back to Developer if reviewer disapproves

```bash
amelia start PROJ-123 --profile work
```

### `amelia review --local [--profile <NAME>]`

Reviews uncommitted changes:
1. Gets uncommitted changes via `git diff`
2. Runs Reviewer agent directly
3. Supports `single` (one review) or `competitive` (parallel Security/Performance/Usability reviews, aggregated)

```bash
amelia review --local
```

### `amelia plan-only <ISSUE_ID> [--profile <NAME>] [--design <PATH>]`

Generates plan without execution:
1. Fetches issue and runs Architect
2. Optionally uses a design document from brainstorming
3. Saves TaskDAG to markdown file
4. Useful for reviewing plans before execution

```bash
amelia plan-only GH-789 --profile home
amelia plan-only GH-789 --design docs/designs/feature.md
```

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

## Troubleshooting

### "No module named 'amelia'"
Run `uv sync` to install dependencies.

### "Invalid API key"
Set `OPENAI_API_KEY` environment variable or use `cli:claude` driver.

### "Issue not found"
Check your tracker configuration. Use `tracker: noop` for testing without a real issue tracker.

### Pre-push hook failing
Run checks manually to see detailed errors:
```bash
uv run ruff check amelia tests
uv run mypy amelia
uv run pytest
```

### "Missing required dependencies: langgraph-checkpoint-sqlite" when running `amelia server`

This error indicates a dependency conflict from multiple installations:

**Causes:**
1. Multiple amelia installations (e.g., old `pip install` in pyenv AND new `uv tool install`)
2. Outdated `uv tool` installation that didn't pick up new dependencies

**Solutions:**

Check for multiple installations:
```bash
which amelia
type amelia
```

If pyenv shim is being used (`/Users/.../.pyenv/shims/amelia`), uninstall the old version:
```bash
pip uninstall amelia
pyenv rehash
```

Reinstall with uv:
```bash
uv tool install --reinstall git+https://github.com/anderskev/amelia.git
```

Verify correct version is used:
```bash
which amelia  # Should show ~/.local/bin/amelia
```

## Learn More

- [Roadmap](docs/roadmap.md) - Detailed development phases and vision
- [Concepts: Understanding Agentic AI](docs/concepts.md) - How agents, drivers, and orchestration work
- [Architecture & Data Flow](docs/architecture.md) - Technical deep dive with diagrams
- [Configuration Reference](docs/configuration.md) - Full settings documentation
- [Benchmarking LLM Agents](docs/benchmarking.md) - How to systematically evaluate and iterate on agents
- [12-Factor Agents Compliance](docs/analysis/12-factor-agents-compliance.md) - How Amelia aligns with the 12-Factor Agents methodology
- [Brainstorming](docs/brainstorming/) - Design explorations created using the superpowers:brainstorming skill

> **Note:** `docs/plans/` contains temporary planning documents for in-progress work. These should be deleted once their corresponding plans are executed and merged.

## Current Status

**What works:**
- Full orchestrator loop with human approval gates
- API driver (OpenAI via pydantic-ai) with structured outputs
- CLI driver (Claude CLI wrapper) with structured outputs
- Local code review with competitive strategy
- Jira and GitHub tracker integrations
- Real tool execution in Developer agent
- FastAPI server with SQLite persistence
- Workflow state machine with event tracking
- React dashboard foundation (Vite, shadcn/ui, React Router v7, aviation theme)

**Limitations/Coming Soon:**
- TaskDAG doesn't validate cyclic dependencies

## Roadmap

> **Vision:** Complete end-to-end workflow control without ever opening GitHub, Jira, or any tracker web UI—with agents that maintain context across sessions and verify their own work.

See [**docs/roadmap.md**](docs/roadmap.md) for the full roadmap with implementation details.

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Core Orchestration | ✅ Complete |
| 2 | Web Dashboard | 🔄 In Progress |
| 3 | Session Continuity | Planned |
| 4 | Verification Framework | Planned |
| 5 | Bidirectional Tracker Sync | Planned |
| 6 | Pull Request Lifecycle | Planned |
| 7 | Quality Gates | Planned |
| 8 | Parallel Execution | Planned |
| 9 | Chat Integration | Planned |
| 10 | Continuous Improvement | Planned |
| 11 | Spec Builder | Planned |
| 12 | Debate Mode | Planned |
| 13 | Knowledge Library | Planned |
| 14 | AWS AgentCore | Planned |
