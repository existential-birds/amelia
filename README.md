# Amelia: Agentic Orchestrator

Amelia is a local agentic coding system that orchestrates software development tasks through multiple AI agents with specialized roles.

## What is Amelia?

Amelia automates development workflows (issue analysis, planning, coding, review) while respecting enterprise constraints. It uses **agentic orchestration** - multiple AI agents coordinate to accomplish complex tasks:

- **Architect** analyzes issues and creates plans
- **Developer** writes code and executes commands
- **Reviewer** evaluates changes and provides feedback
- **Project Manager** fetches and manages issues

## Key Concepts

```mermaid
flowchart LR
    subgraph Input
        T[Issue Tracker<br/>Jira/GitHub]
    end

    subgraph Orchestrator
        A[Architect] --> H[Human Approval]
        H --> D[Developer]
        D --> R[Reviewer]
        R -->|needs fixes| D
    end

    subgraph LLM
        DR[Driver<br/>API/CLI]
    end

    T --> A
    A & D & R <--> DR
```

| Concept | Description |
|---------|-------------|
| **Agents** | Specialized AI roles - Architect (plans), Developer (writes code), Reviewer (reviews), Project Manager (coordinates). See [Concepts](docs/concepts.md). |
| **Orchestrator** | LangGraph-based state machine that coordinates agents through workflow using ExecutionState to track progress. |
| **Drivers** | Abstraction for LLM communication - `api:openai` (direct API) or `cli:claude` (wraps CLI tools). |
| **Trackers** | Abstraction for issue sources - `jira`, `github`, or `noop`. |
| **Profiles** | Bundled configurations in `settings.amelia.yaml`. |

## Quick Start

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Create settings.amelia.yaml
cat > settings.amelia.yaml << 'EOF'
active_profile: dev
profiles:
  dev:
    name: dev
    driver: api:openai
    tracker: noop
    strategy: single
EOF

# Run first command
uv run amelia plan-only ISSUE-123
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

### `amelia plan-only <ISSUE_ID> [--profile <NAME>]`

Generates plan without execution:
1. Fetches issue and runs Architect
2. Saves TaskDAG to markdown file
3. Useful for reviewing plans before execution

```bash
amelia plan-only GH-789 --profile home
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

## Learn More

- [Concepts: Understanding Agentic AI](docs/concepts.md) - How agents, drivers, and orchestration work
- [Architecture & Data Flow](docs/architecture.md) - Technical deep dive with diagrams
- [Configuration Reference](docs/configuration.md) - Full settings documentation

## Current Status

**What works:**
- Full orchestrator loop with human approval gates
- API driver (OpenAI via pydantic-ai) with structured outputs
- Local code review with competitive strategy
- Jira and GitHub tracker integrations
- Real tool execution in Developer agent

**Limitations/Coming Soon:**
- CLI driver (`cli:claude`) is currently a stub for LLM interactions (tool execution works)
- TaskDAG doesn't validate cyclic dependencies

## Roadmap

### Phase 1: Core Orchestration (Current)
- Full agent orchestration with human approval gates
- Multi-driver support (API and CLI)
- Issue tracker integrations (Jira, GitHub)

### Phase 2: Web UI
- **Observability dashboard** using [AI Elements](https://github.com/ai-elements) library for real-time agent activity monitoring, task progress, and execution logs
- **Full control interface** to approve/reject plans, intervene in agent workflows, and manage configurations through the browser

### Phase 3: Local RAG Integration
- Spin up local RAG infrastructure for agents to query codebase context
- Enable agents to use extended thinking (ultrathink) for complex reasoning
- Interactive clarification flow where agents can ask targeted questions before proceeding
