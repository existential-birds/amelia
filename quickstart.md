# Quickstart: Amelia

## Prerequisites

- Python 3.12+
- `uv` (recommended) or `pip`
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
# OR
pip install -e .
```

## Configuration

Create a `settings.yaml` in the root directory:

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
amelia start
```

### 2. Run a Specific Phase
Execute only the planning phase for an issue:
```bash
amelia plan --issue PROJ-123
```

### 3. Local Review
Review uncommitted changes using the "Reviewer" agent:
```bash
amelia review --local
```
