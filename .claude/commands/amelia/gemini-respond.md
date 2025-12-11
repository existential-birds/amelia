---
description: respond to gemini-code-assist review comments on the current PR after evaluation and fixes
---
Respond to the gemini-code-assist[bot] review comments on the current PR.

## Context

You have just evaluated the Gemini Code Assist feedback using `/amelia:gemini-review` and made any necessary fixes. Now post responses to the review comments.

## Steps

1. **Get PR context**:
   ```bash
   gh repo view --json nameWithOwner --jq '.nameWithOwner'
   gh pr view --json number --jq '.number'
   ```

2. **Get all gemini review comment IDs and content** (use `--paginate` to ensure all comments are fetched):
   ```bash
   gh api --paginate repos/{owner}/{repo}/pulls/{number}/comments \
     --jq '.[] | select(.user.login == "gemini-code-assist[bot]") | {id: .id, path: .path, line: .line, body: .body}'
   ```

3. **For each review comment, post a reply** based on the evaluation:

   - **If feedback was incorrect/unfounded**: Reply explaining why the current code is correct
   - **If feedback lacked context**: Reply explaining the design decision
   - **If feedback was valid and fixed**: Reply with "Fixed in [commit]" or brief description
   - **If feedback was valid but won't fix**: Reply explaining the tradeoff/decision

   Use this API call to reply:
   ```bash
   gh api repos/{owner}/{repo}/pulls/{number}/comments/{comment_id}/replies \
     -X POST --raw-field body="@gemini-code-assist Your response here"
   ```

4. **Summary**: List which comments were addressed and how.

## Response Guidelines

- **Always tag @gemini-code-assist at the start of each reply**
- Keep responses concise and technical
- No performative agreement ("Great point!", "You're right!")
- Reference specific code/design when explaining decisions
- If fixed: state what changed, not gratitude
