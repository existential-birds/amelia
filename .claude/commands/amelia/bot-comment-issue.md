---
description: post a comment to a GitHub issue as hey-amelia bot
---
Post a comment to a GitHub issue as the hey-amelia GitHub App.

## Prerequisites

The hey-amelia GitHub App must be configured. See `.claude/skills/hey-amelia/skill.md` for setup instructions.

## Steps

1. **Get repo context**:
   ```bash
   gh repo view --json nameWithOwner --jq '.nameWithOwner'
   ```

2. **Determine issue number**:
   - If an issue number was provided in arguments: use it
   - If no issue number: ask the user which issue to comment on

3. **Determine comment content**:
   - If comment content was provided in arguments: use it as the comment body or topic
   - If no content: ask the user what they want to post

4. **Compose the comment**:
   - Use GitHub Markdown formatting
   - Add headers for structure if the comment is longer than a few lines
   - Keep it concise and actionable

5. **Post the comment**:
   ```bash
   uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
     --repo "{owner}/{repo}" \
     --issue {number} \
     --body "Your comment here"
   ```

   For multi-line comments:
   ```bash
   uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
     --repo "$REPO" \
     --issue "$ISSUE" \
     --body "$(cat <<'EOF'
   ## Header

   Your multi-line comment here.
   EOF
   )"
   ```

6. **Confirm**: Report the posted comment URL to the user.

## Comment Guidelines

- Keep comments concise and actionable
- Use headers (##) for structure in longer comments
- Reference commits when mentioning changes: `Fixed in abc1234`
- Reference PRs when relevant: `See #42`
- Use code blocks for code references
- No performative phrases ("Great work!", "Thanks!")

## Example Usage

```
/amelia:bot-comment-issue 30 Status update: investigation complete
/amelia:bot-comment-issue 42 Post a summary of findings
/amelia:bot-comment-issue 15
```
