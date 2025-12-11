---
name: bot-comment-pr
description: Post comments to pull requests as the hey-amelia GitHub App bot. Use when posting PR comments, adding summaries to PRs, or commenting on pull requests as a bot. Triggers on PR comment, post to PR, add PR comment, hey-amelia comment.
---

# Post PR Comments as hey-amelia

Post general comments to pull requests using the hey-amelia GitHub App.

## Quick Start

```bash
# Get current PR context
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
PR=$(gh pr view --json number --jq '.number')

# Post a comment
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "$REPO" \
  --pr "$PR" \
  --body "Your comment here"
```

## Prerequisites

The hey-amelia GitHub App must be configured. See [skill.md](skill.md) for setup.

## Usage

### Step 1: Get PR Context

```bash
# Get repository and PR number
gh repo view --json nameWithOwner --jq '.nameWithOwner'
gh pr view --json number --jq '.number'
```

### Step 2: Compose Comment

Format comments using GitHub Markdown. Common patterns:

**Status update:**
```markdown
## Status Update

Changes are ready for review. Key modifications:
- Item 1
- Item 2
```

**Summary:**
```markdown
## Summary

This PR implements [feature].

### Changes
- Change 1
- Change 2

### Testing
- Test coverage added for X
```

**Response to feedback:**
```markdown
## Addressed Feedback

All review comments have been addressed:
- Fixed null check (commit abc1234)
- Added error handling (commit def5678)
```

### Step 3: Post Comment

```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "{owner}/{repo}" \
  --pr {number} \
  --body "Your formatted comment"
```

For multi-line comments, use a heredoc:

```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "$REPO" \
  --pr "$PR" \
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
- Use code blocks for code references
- No performative phrases ("Great work!", "Thanks!")

## Examples

**Posting a status update:**
```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "acme/project" \
  --pr 42 \
  --body "## Ready for Review

All CI checks passing. Changes include:
- Refactored auth module
- Added unit tests (95% coverage)
- Updated API documentation"
```

**Posting test results:**
```bash
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "acme/project" \
  --pr 42 \
  --body "## Test Results

Manual testing completed:
- [x] Login flow verified
- [x] Error handling tested
- [x] Edge cases covered"
```

## Related

- [skill.md](skill.md) - Full hey-amelia configuration and authentication
- `/amelia:bot-respond` - Respond to code review bot comments (reply to specific comments)
