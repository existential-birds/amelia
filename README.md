# Amelia: Agentic Orchestrator

[Amelia](https://en.wikipedia.org/wiki/Amelia_Earhart) is a local agentic coding system that orchestrates software development tasks through multiple AI agents with specialized roles.

## What is Amelia?

Amelia automates development workflows (issue analysis, planning, coding, review) while respecting enterprise constraints. It uses **agentic orchestration** - multiple AI agents coordinate to accomplish complex tasks:

```
Issue → Architect (plan) → Human Approval → Developer (execute) ↔ Reviewer (review) → Done
```

![Amelia Dashboard Design Mock](docs/plans/design_mock.jpg)

## Prerequisites

- **Python 3.12+** - Required for type hints and async features
- **uv** - Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Git** - For version control operations
- **LLM access** - Either:
  - OpenAI API key (for `api:openai` driver)
  - Claude CLI installed (for `cli:claude` driver)

## Quick Start

```bash
# Install uv (Linux/macOS)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/anderskev/amelia.git
cd amelia
uv sync

# Set your API key (for api:openai driver)
export OPENAI_API_KEY="sk-..."

# Create minimal config
cat > settings.amelia.yaml << 'EOF'
active_profile: dev
profiles:
  dev:
    name: dev
    driver: api:openai
    tracker: noop
    strategy: single
EOF

# Test with a dry run
uv run amelia plan-only TEST-001
```

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

## Learn More

- [Concepts: Understanding Agentic AI](docs/concepts.md) - How agents, drivers, and orchestration work
- [Architecture & Data Flow](docs/architecture.md) - Technical deep dive with diagrams
- [Configuration Reference](docs/configuration.md) - Full settings documentation
- [Benchmarking LLM Agents](docs/benchmarking.md) - How to systematically evaluate and iterate on agents

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

**Limitations/Coming Soon:**
- TaskDAG doesn't validate cyclic dependencies

## Roadmap

### Phase 1: Core Orchestration ✅ Complete
- Full agent orchestration with human approval gates
- Multi-driver support (API and CLI)
- Issue tracker integrations (Jira, GitHub)
- [Reviewer agent benchmark framework](https://github.com/anderskev/amelia/issues/8) for data-driven prompt iteration

### Phase 2: Web Dashboard (In Progress)
- **Server foundation** - FastAPI backend with SQLite persistence ✅
- **Workflow models** - State machine for tracking execution status ✅
- **REST API** - Endpoints for workflows, tasks, and events
- **WebSocket events** - Real-time updates to dashboard
- **React dashboard** - Observability UI with Zustand state management

### Phase 3: Local RAG Integration
- Local RAG infrastructure for agents to query codebase context
- Extended thinking (ultrathink) for complex reasoning
- Interactive clarification flow where agents can ask targeted questions before proceeding
