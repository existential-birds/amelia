---
name: bot-create-branch
description: Create Git branches as the hey-amelia GitHub App bot. Use when creating branches, setting up feature branches, or branching from specific commits. Triggers on create branch, new branch, bot branch, hey-amelia branch.
---

# Create Branches as hey-amelia

Create Git branches using the hey-amelia GitHub App.

## Quick Start

```bash
# Get current repo context
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

# Create a branch from default branch
uv run python .claude/skills/hey-amelia/scripts/create_branch.py \
  --repo "$REPO" \
  --branch "feature/new-feature"
```

## Prerequisites

The hey-amelia GitHub App must be configured with **Contents: Write** permission. See [skill.md](skill.md) for setup.

## Usage

### Step 1: Get Repository Context

```bash
# Get repository
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

# Check existing branches
git branch -r
```

### Step 2: Create Branch

**From default branch (main/master):**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_branch.py \
  --repo "$REPO" \
  --branch "feature/my-feature"
```

**From specific base branch:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_branch.py \
  --repo "$REPO" \
  --branch "feature/my-feature" \
  --base "develop"
```

**From specific commit SHA:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_branch.py \
  --repo "$REPO" \
  --branch "hotfix/urgent-fix" \
  --sha "abc1234567890"
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--branch` | Yes | New branch name to create |
| `--base` | No | Base branch to create from (default: repo's default branch) |
| `--sha` | No | Specific commit SHA (overrides --base) |

## Branch Naming Conventions

Common patterns:
- `feature/description` - New features
- `bugfix/description` - Bug fixes
- `hotfix/description` - Urgent production fixes
- `release/version` - Release branches
- `chore/description` - Maintenance tasks

## Examples

**Creating a feature branch:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_branch.py \
  --repo "acme/project" \
  --branch "feature/add-dark-mode"
```

**Creating a release branch from develop:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_branch.py \
  --repo "acme/project" \
  --branch "release/v2.0.0" \
  --base "develop"
```

**Creating a hotfix from a specific commit:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_branch.py \
  --repo "acme/project" \
  --branch "hotfix/security-patch" \
  --sha "abc1234"
```

## Workflow: Branch then Commit then PR

Typical workflow for making changes:

```bash
# 1. Create a feature branch
uv run python .claude/skills/hey-amelia/scripts/create_branch.py \
  --repo "$REPO" \
  --branch "feature/my-feature"

# 2. Commit files to the branch
uv run python .claude/skills/hey-amelia/scripts/commit_files.py \
  --repo "$REPO" \
  --branch "feature/my-feature" \
  --message "Add my feature" \
  --files "src/feature.py"

# 3. Create PR
uv run python .claude/skills/hey-amelia/scripts/create_pr.py \
  --repo "$REPO" \
  --head "feature/my-feature" \
  --base "main" \
  --title "Add my feature" \
  --body "Description of changes"
```

## Related

- [skill.md](skill.md) - Full hey-amelia configuration and authentication
- [bot-commit.md](bot-commit.md) - Commit files after creating branch
- [bot-create-pr.md](bot-create-pr.md) - Create PRs after committing
- `/amelia:bot-create-branch` - Command to create branches
