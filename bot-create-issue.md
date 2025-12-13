---
name: bot-create-issue
description: Create GitHub issues as the hey-amelia GitHub App bot. Use when opening issues, creating bug reports, or filing feature requests as a bot. Triggers on create issue, open issue, bot issue, hey-amelia issue, file bug.
---

# Create Issues as hey-amelia

Create GitHub issues using the hey-amelia GitHub App.

## Quick Start

```bash
# Get current repo context
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

# Create an issue
uv run python .claude/skills/hey-amelia/scripts/create_issue.py \
  --repo "$REPO" \
  --title "Issue title" \
  --body "Issue description"
```

## Prerequisites

The hey-amelia GitHub App must be configured. See [skill.md](skill.md) for setup.

## Usage

### Step 1: Get Repository Context

```bash
# Get repository
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

# List existing labels (optional)
gh label list

# List milestones (optional)
gh api repos/{owner}/{repo}/milestones --jq '.[].title'
```

### Step 2: Compose Issue

Format issues using GitHub Markdown:

**Bug report:**
```markdown
## Description

Clear description of the bug.

## Steps to Reproduce

1. Step one
2. Step two
3. Step three

## Expected Behavior

What should happen.

## Actual Behavior

What actually happens.

## Environment

- OS: macOS 14.0
- Version: 1.2.3
```

**Feature request:**
```markdown
## Summary

Brief description of the feature.

## Motivation

Why this feature is needed.

## Proposed Solution

How it could be implemented.
```

### Step 3: Create Issue

```bash
uv run python .claude/skills/hey-amelia/scripts/create_issue.py \
  --repo "{owner}/{repo}" \
  --title "Issue title" \
  --body "Issue description"
```

With labels and assignees:

```bash
uv run python .claude/skills/hey-amelia/scripts/create_issue.py \
  --repo "$REPO" \
  --title "Bug: Login fails silently" \
  --body "Description here" \
  --labels "bug,high-priority" \
  --assignees "developer1,developer2"
```

With milestone:

```bash
uv run python .claude/skills/hey-amelia/scripts/create_issue.py \
  --repo "$REPO" \
  --title "Add dark mode support" \
  --body "Feature request for dark mode" \
  --labels "enhancement" \
  --milestone 3
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--title` | Yes | Issue title |
| `--body` | Yes | Issue description |
| `--labels` | No | Comma-separated label names |
| `--assignees` | No | Comma-separated GitHub usernames |
| `--milestone` | No | Milestone number |

## Examples

**Creating a bug report:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_issue.py \
  --repo "acme/project" \
  --title "Bug: API returns 500 on empty input" \
  --body "## Description

The /api/process endpoint returns HTTP 500 when the input is empty.

## Steps to Reproduce

1. Send POST to /api/process with empty body
2. Observe 500 response

## Expected Behavior

Should return 400 Bad Request with validation error." \
  --labels "bug"
```

**Creating a follow-up from code review:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_issue.py \
  --repo "acme/project" \
  --title "Tech debt: Refactor auth module" \
  --body "Identified during PR #42 review.

The auth module has grown complex and should be split into:
- TokenService
- SessionManager
- AuthMiddleware

See discussion: #42 (comment)" \
  --labels "tech-debt,refactor"
```

**Creating a feature request with milestone:**
```bash
uv run python .claude/skills/hey-amelia/scripts/create_issue.py \
  --repo "acme/project" \
  --title "Add export to CSV functionality" \
  --body "## Summary

Users need to export their data to CSV format.

## Requirements

- Export all visible columns
- Include headers
- Handle special characters properly" \
  --labels "enhancement" \
  --milestone 5
```

## Related

- [skill.md](skill.md) - Full hey-amelia configuration and authentication
- [bot-comment-issue.md](bot-comment-issue.md) - Comment on existing issues
- `/amelia:bot-create-issue` - Command to create issues
