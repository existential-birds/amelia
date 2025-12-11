---
description: post a comment to the current PR as hey-amelia bot
---
Post a comment to the current pull request as the hey-amelia GitHub App.

## Prerequisites

The hey-amelia GitHub App must be configured. See `.claude/skills/hey-amelia/skill.md` for setup instructions.

## Steps

1. **Get PR context**:
   ```bash
   gh repo view --json nameWithOwner --jq '.nameWithOwner'
   gh pr view --json number --jq '.number'
   ```

2. **Determine comment content**:
   - If arguments were provided: use them as the comment body or topic
   - If no arguments: ask the user what they want to post

3. **Compose the comment**:
   - Use GitHub Markdown formatting
   - Add headers for structure if the comment is longer than a few lines
   - Keep it concise and actionable

4. **Post the comment**:
   ```bash
   uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
     --repo "{owner}/{repo}" \
     --pr {number} \
     --body "Your comment here"
   ```

   For multi-line comments:
   ```bash
   uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
     --repo "$REPO" \
     --pr "$PR" \
     --body "$(cat <<'EOF'
   ## Header

   Your multi-line comment here.
   EOF
   )"
   ```

5. **Confirm**: Report the posted comment URL to the user.

## Comment Guidelines

- Keep comments concise and actionable
- Use headers (##) for structure in longer comments
- Reference commits when mentioning changes: `Fixed in abc1234`
- Use code blocks for code references
- No performative phrases ("Great work!", "Thanks!")

## Example Usage

```
/amelia:bot-comment-pr Ready for review, all CI checks passing
/amelia:bot-comment-pr Post a summary of the changes in this PR
/amelia:bot-comment-pr
```
