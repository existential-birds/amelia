# Quickstart: Amelia

## Prerequisites

- Python 3.12+
- `uv` ([install](https://docs.astral.sh/uv/getting-started/installation/))
- `git`
- **CLI Tools** (for Work Profile):
    - `claude` (Anthropic CLI): `npm install -g @anthropic-ai/claude-code`
    - `acli` (Atlassian CLI)

## Installation

```bash
# Clone the repository
git clone https://github.com/amelia/amelia.git
cd amelia

# Install dependencies
uv sync
```

## Configuration

Create a `settings.amelia.yaml` in the root directory:

```yaml
active_profile: work

profiles:
  work:
    driver: cli
    tracker: jira
    strategy: single
  
  home:
    driver: api
    tracker: github
    strategy: competitive
```

## Usage

### 1. Start the Orchestrator
Run the interactive loop:
```bash
uv run amelia start
```

### 2. Run a Specific Phase
Execute only the planning phase for an issue:
```bash
uv run amelia plan --issue PROJ-123
```

### 3. Local Review
Review uncommitted changes using the "Reviewer" agent:
```bash
uv run amelia review --local
```
