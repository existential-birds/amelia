# Amelia: Agentic Orchestrator

![Amelia Terminal](docs/design/terminal_screen.jpg)

[Amelia](https://en.wikipedia.org/wiki/Amelia_Earhart) is a local agentic coding system that orchestrates software development through Architect, Developer, and Reviewer agents. They argue about your code so you don't have to.

See the [**Roadmap**](https://existential-birds.github.io/amelia/reference/roadmap) for where we're headed.

## Current Status

> [!WARNING]
> This is an experimental project. It will occasionally do something baffling. So will you. You'll figure it out together.

- Full orchestrator loop with human approval gates (CLI and web dashboard)
- CLI driver (Claude CLI wrapper) with structured outputs, streaming, and agentic execution
- Local code review with competitive strategy
- GitHub tracker integration (via `gh` CLI)
- Real tool execution in Developer agent (shell commands, file writes)
- FastAPI server with SQLite persistence and WebSocket event streaming
- Web dashboard with workflow visualization, real-time activity log, and approval controls

## Features

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

### Details View

Inspect individual agent runs, tool calls, and outputs.

![Details View](docs/design/hugo_details_opus.png)

### Helpful Metrics

Compare model performance and track token usage across runs.

![Metrics](docs/design/hugo_opus_vs_gemini.jpeg)

## Prerequisites

- **Python 3.12+** - Required for type hints and async features
- **uv** - Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Git** - For version control operations
- **Beagle plugin** - Claude Code plugin with Amelia skills ([install guide](https://github.com/existential-birds/beagle?tab=readme-ov-file#installation))
- **LLM access** - Either:
  - OpenRouter API key (for `api:openrouter` driver)
  - Claude CLI installed (for `cli:claude` driver)

## Quick Start

### 1. Install Prerequisites

> [!IMPORTANT]
> You must install the [Beagle plugin](https://github.com/existential-birds/beagle?tab=readme-ov-file#installation) for Claude Code before using Amelia. It provides the skills and commands needed to work with Amelia workflows.

```bash
# Install uv (Linux/macOS)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install amelia as a global tool
uv tool install git+https://github.com/existential-birds/amelia.git

# Or install from a local path
uv tool install /path/to/amelia

# Set your API key
export OPENROUTER_API_KEY="sk-..."
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
    driver: api:openrouter
    model: "anthropic/claude-3.5-sonnet"
    tracker: github
    strategy: single
EOF
```

See **[Configuration](https://existential-birds.github.io/amelia/guide/configuration)** for all available parameters including retry settings and driver options.

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
# Start the server (opens dashboard at localhost:8420)
amelia dev

# In another terminal, start a workflow for an issue
amelia start 123

# Review uncommitted changes
amelia review --local
```

> [!TIP]
> Use `tracker: noop` to test without a real issue tracker. Amelia will pretend the issue exists. It's very committed to the bit.

## Alternative Installation

### Run from Source

If you prefer not to install globally:

```bash
# Clone the repo
git clone https://github.com/existential-birds/amelia.git
cd amelia
uv sync

# Run from your project directory
cd /path/to/your/project
/path/to/amelia/uv run amelia dev
```

Or use the `AMELIA_SETTINGS` environment variable:

```bash
cd /path/to/amelia
AMELIA_SETTINGS=/path/to/your/project/settings.amelia.yaml uv run amelia dev
```

> [!NOTE]
> Amelia reads `settings.amelia.yaml` from the current working directory (or via `AMELIA_SETTINGS`). Run commands from your project root—agents can't help with code they can't see.

## How It Works

Amelia orchestrates configurable AI agents through a workflow graph. See [Architecture](https://existential-birds.github.io/amelia/architecture/overview) for data flow and [Concepts](https://existential-birds.github.io/amelia/architecture/concepts) for how agents and drivers work.

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
amelia review --local         # Review uncommitted changes
```

See the **[Usage Guide](https://existential-birds.github.io/amelia/guide/usage)** for complete CLI reference, API endpoints, and example workflows.

## Configuration

Basic `settings.amelia.yaml`:

```yaml
active_profile: home
profiles:
  home:
    name: home
    driver: api:openrouter
    model: "anthropic/claude-3.5-sonnet"
    tracker: github
    strategy: single
```

See [Configuration Reference](https://existential-birds.github.io/amelia/guide/configuration) for full details.

## Documentation

For full documentation, visit **[existential-birds.github.io/amelia](https://existential-birds.github.io/amelia/)**.

## License

Amelia Core is licensed under the [Elastic License 2.0](LICENSE).

### Commercial Licensing

A commercial license is required only for restricted uses: reselling, repackaging, hosting as a service, or embedding Amelia in paid products. Internal use at your company does not require a commercial license.

See [LICENSING.md](docs/legal/LICENSING.md) for details and examples.
