---
name: bot-create-pr
description: Create pull requests as the hey-amelia GitHub App bot. Use when opening PRs, creating pull requests programmatically, or submitting changes for review as a bot. Triggers on create PR, open PR, bot PR, hey-amelia PR.
---

# Create Pull Requests as hey-amelia

Create pull requests using the hey-amelia GitHub App.

## Quick Start

```bash
# Get current repo context
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
BRANCH=$(git branch --show-current)

# Create a PR
uv run python .claude/skills/hey-amelia/scripts/create_pr.py \
  --repo "$REPO" \
  --head "$BRANCH" \
  --base "main" \
  --title "Your PR title" \
  --body "Description of changes"
```

## Prerequisites

The hey-amelia GitHub App must be configured. See [skill.md](skill.md) for setup.

## Usage

### Step 1: Get Context

```bash
# Get repository
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

# Get current branch
BRANCH=$(git branch --show-current)

# Verify branch is pushed
git push -u origin "$BRANCH"
```

### Step 2: Compose PR Description

Format PR descriptions using GitHub Markdown:

**Standard PR:**
```markdown
## Summary

Brief description of what this PR does.

## Changes

- Change 1
- Change 2

## Testing

- How to test these changes
```

**Bug fix:**
```markdown
## Summary

Fixes #123.

## Root Cause

Description of the issue.

## Solution

How it was fixed.
```

### Step 3: Create PR

```bash
uv run python .claude/skills/hey-amelia/scripts/create_pr.py \
  --repo "{owner}/{repo}" \
  --head "{source-branch}" \
  --base "{target-branch}" \
  --title "PR title" \
  --body "PR description"
```

For multi-line descriptions, use a heredoc:

```bash
uv run python .claude/skills/hey-amelia/scripts/create_pr.py \
  --repo "$REPO" \
  --head "$BRANCH" \
  --base "main" \
  --title "Add new feature" \
  --body "$(cat <<'EOF'
## Summary

Your multi-line description here.

## Changes

- Point 1
- Point 2
EOF
)"
```

### Creating Draft PRs

Add the `--draft` flag to create a draft PR:

```bash
uv run python .claude/skills/hey-amelia/scripts/create_pr.py \
  --repo "$REPO" \
  --head "$BRANCH" \
  --base "main" \
  --title "WIP: Feature in progress" \
  --body "Work in progress" \
  --draft
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--head` | Yes | Source branch (with your changes) |
| `--base` | Yes | Target branch (to merge into) |
| `--title` | Yes | PR title |
| `--body` | Yes | PR description |
| `--draft` | No | Create as draft PR |

## Examples

**Creating a feature PR:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_pr.py \
  --repo "acme/project" \
  --head "feature/add-auth" \
  --base "main" \
  --title "Add user authentication" \
  --body "## Summary

Implements JWT-based authentication.

## Changes
- Added auth middleware
- Added login/logout endpoints
- Added user session management"
```

**Creating a hotfix PR:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_pr.py \
  --repo "acme/project" \
  --head "hotfix/fix-crash" \
  --base "main" \
  --title "Fix null pointer crash in checkout" \
  --body "Fixes #456. Adds null check before accessing user cart."
```

## Related

- [skill.md](skill.md) - Full hey-amelia configuration and authentication
- [bot-commit.md](bot-commit.md) - Commit files before creating PR
- `/amelia:bot-create-pr` - Command to create PRs
