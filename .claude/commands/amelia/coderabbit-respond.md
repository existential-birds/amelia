---
description: respond to coderabbitai review comments on the current PR after evaluation and fixes
---
Respond to the coderabbitai[bot] review comments on the current PR.

## Context

You have just evaluated the CodeRabbit feedback using `/amelia:coderabbit-review` and made any necessary fixes. Now post responses to the review comments.

**Important**: CodeRabbit re-posts comments on each review iteration, creating duplicates. This command filters to only show unreplied comments and picks the newest version of each duplicate set.

## Steps

1. **Get PR context**:
   ```bash
   gh repo view --json nameWithOwner --jq '.nameWithOwner'
   gh pr view --json number --jq '.number'
   ```

2. **Get unreplied CodeRabbit comments** (filters out already-replied comments and duplicates):
   ```bash
   gh api --paginate repos/{owner}/{repo}/pulls/{number}/comments | jq -s 'add |
     # Get root CodeRabbit comments (not replies to other comments)
     [.[] | select(.user.login == "coderabbitai[bot]" and .in_reply_to_id == null)] as $roots |
     # Get IDs that hey-amelia has already replied to
     [.[] | select(.user.login == "hey-amelia[bot]") | .in_reply_to_id] as $replied |
     # Filter to unreplied comments only
     $roots | map(select(. as $c | $replied | index($c.id) == null)) |
     # Group by file:line and pick newest comment for each (handles duplicates)
     group_by({p: .path, l: .line}) |
     map(sort_by(.created_at) | last) |
     # Format output
     map({id, path, line, body})
   '
   ```

   This query:
   - Excludes comments that are replies (e.g., CodeRabbit responding to itself)
   - Excludes comments that hey-amelia has already responded to
   - Groups duplicate comments by file:line and picks the newest one
   - Returns only the comments that need responses

3. **For each unreplied comment, post a reply** based on the evaluation:

   - **If feedback was incorrect/unfounded**: Reply explaining why the current code is correct
   - **If feedback lacked context**: Reply explaining the design decision
   - **If feedback was valid and fixed**: Reply with "Fixed in [commit]" or brief description
   - **If feedback was valid but won't fix**: Reply explaining the tradeoff/decision

   Use this API call to reply:
   ```bash
   gh api repos/{owner}/{repo}/pulls/{number}/comments/{comment_id}/replies \
     -X POST --raw-field body="@coderabbitai Your response here"
   ```

4. **Summary**: List which comments were addressed and how.

## Response Guidelines

- **Always tag @coderabbitai at the start of each reply**
- Keep responses concise and technical
- No performative agreement ("Great point!", "You're right!")
- Reference specific code/design when explaining decisions
- If fixed: state what changed, not gratitude
