---
name: bot-comment-issue
description: Post comments and replies to GitHub issues as the hey-amelia GitHub App bot. Use when posting issue comments, responding to issues, or commenting on GitHub issues as a bot. Triggers on issue comment, post to issue, add issue comment, hey-amelia issue.
---

# Post Issue Comments as hey-amelia

Post comments to GitHub issues using the hey-amelia GitHub App.

## Quick Start

```bash
# Get current repo context
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

# Post a comment to issue #30
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "$REPO" \
  --issue 30 \
  --body "Your comment here"
```

## Prerequisites

The hey-amelia GitHub App must be configured. See [skill.md](skill.md) for setup.

## Usage

### Step 1: Get Issue Context

```bash
# Get repository
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

# Get issue number (if working with a specific issue)
gh issue view 30 --json number,title --jq '"\(.number): \(.title)"'

# List recent issues
gh issue list --limit 5
```

### Step 2: Compose Comment

Format comments using GitHub Markdown. Common patterns:

**Status update:**
```markdown
## Status Update

Investigation complete. Key findings:
- Finding 1
- Finding 2
```

**Answer/response:**
```markdown
## Response

To address your question:

The solution is to...
```

**Progress report:**
```markdown
## Progress Update

Work completed:
- [x] Task 1
- [x] Task 2
- [ ] Task 3 (in progress)
```

### Step 3: Post Comment

```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "{owner}/{repo}" \
  --issue {number} \
  --body "Your formatted comment"
```

For multi-line comments, use a heredoc:

```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "$REPO" \
  --issue 30 \
  --body "$(cat <<'EOF'
## Summary

Your multi-line comment here.

- Point 1
- Point 2
EOF
)"
```

## Comment Guidelines

- Keep comments concise and actionable
- Use headers for structure in longer comments
- Reference commits when mentioning changes: `Fixed in abc1234`
- Reference PRs when relevant: `See #42`
- Use code blocks for code references
- No performative phrases ("Great work!", "Thanks!")

## Examples

**Posting a status update:**
```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "acme/project" \
  --issue 30 \
  --body "## Status Update

Investigation complete. Root cause identified:
- Database connection timeout under load
- Fix implemented in PR #45"
```

**Posting a response:**
```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "acme/project" \
  --issue 30 \
  --body "## Response

The configuration change can be made in \`settings.yaml\`:

\`\`\`yaml
timeout: 30
retry_count: 3
\`\`\`"
```

**Closing with resolution:**
```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "acme/project" \
  --issue 30 \
  --body "## Resolved

Fixed in PR #45 (merged). The issue was caused by improper connection pooling.

Closing this issue."
```

## Related

- [skill.md](skill.md) - Full hey-amelia configuration and authentication
- [bot-comment-pr.md](bot-comment-pr.md) - Post comments to pull requests
- `/amelia:bot-comment-issue` - Command to post issue comments
