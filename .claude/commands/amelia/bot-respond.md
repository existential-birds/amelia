---
description: respond to code review bot comments on the current PR as hey-amelia
---
Respond to code review bot comments on the current PR as the hey-amelia GitHub App.

## Prerequisites

The hey-amelia GitHub App must be configured. See `.claude/skills/hey-amelia/skill.md` for setup instructions.

## Supported Bots

This command responds to comments from these code review assistants:

| Bot | Login |
|-----|-------|
| CodeRabbit | `coderabbitai[bot]` |
| Gemini Code Assist | `gemini-code-assist[bot]` |
| Greptile | `greptile-apps[bot]` |
| GitHub Copilot | `copilot[bot]` |

## Steps

1. **Get PR context**:
   ```bash
   gh repo view --json nameWithOwner --jq '.nameWithOwner'
   gh pr view --json number --jq '.number'
   ```

2. **Get all code review bot comments**:
   ```bash
   # Get review comments from all supported bots
   gh api repos/{owner}/{repo}/pulls/{number}/comments \
     --jq '.[] | select(.user.login == "coderabbitai[bot]" or .user.login == "gemini-code-assist[bot]" or .user.login == "greptile-apps[bot]" or .user.login == "copilot[bot]") | {id: .id, user: .user.login, path: .path, line: .line, body: .body}'
   ```

3. **Evaluate each comment** by reading the relevant code and understanding the context:
   - Is the feedback correct?
   - Does it lack context about the design?
   - Is it a valid issue that should be fixed?
   - Is it a valid issue but not worth fixing?

4. **For each comment, determine the response**:

   - **If feedback was incorrect/unfounded**: Reply explaining why the current code is correct
   - **If feedback lacked context**: Reply explaining the design decision or architectural choice
   - **If feedback was valid and fixed**: Reply with "Fixed in [commit hash]" or brief description of the fix
   - **If feedback was valid but won't fix**: Reply explaining the tradeoff or decision to defer

5. **Post responses using the hey-amelia bot**:
   ```bash
   uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
     --repo "{owner}/{repo}" \
     --comment-id {comment_id} \
     --body "Your response here"
   ```

6. **Summary**: List which comments were addressed and how.

## Response Guidelines

- Keep responses concise and technical
- No performative agreement ("Great point!", "You're right!", "Thanks for catching this!")
- Reference specific code, design patterns, or architectural decisions when explaining
- If fixed: state what changed, not gratitude
- If disagreeing: be direct but professional, cite specific reasons
- Use code blocks when referencing specific code

## Example Responses

**Incorrect feedback:**
```
This is intentional. The `retry_count` is bounded by `MAX_RETRIES` (line 42), so the loop will always terminate. The static analyzer may not trace through the config lookup.
```

**Lacking context:**
```
This follows the repository pattern established in `base_repository.py`. The indirection allows swapping implementations for testing without mocking the database layer.
```

**Fixed:**
```
Fixed in abc1234. Added null check before accessing `user.email`.
```

**Won't fix:**
```
Acknowledged, but deferring. The current implementation handles the 99% case. Edge case handling would add significant complexity for minimal benefit. Tracking in #456.
```
