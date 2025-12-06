---
description: update an existing PR description after additional changes
---

# Update Pull Request Description

Update an existing PR description when additional fixes or changes have been made after the original PR was opened.

## Use Cases

- Follow-up fixes after code review feedback
- Additional changes discovered during testing
- Expanding scope based on new requirements
- Bug fixes found during PR review

## Instructions

### 1. Find the Current PR

```bash
# Get the PR number for current branch
gh pr view --json number,title,body,url,createdAt

# Get the original PR description
gh pr view --json body --jq '.body'

# Get the base commit (when PR was created)
gh pr view --json baseRefName,headRefName,commits
```

### 2. Analyze New Changes

```bash
# Get the original PR merge base
MERGE_BASE=$(git merge-base main HEAD)

# Find commits added since PR was opened
# (Compare against the first commit in the PR)
FIRST_COMMIT=$(gh pr view --json commits --jq '.commits[0].oid')

# Show new commits (those after the first PR commit)
git log --oneline ${FIRST_COMMIT}..HEAD

# Show what files changed in new commits
git diff --stat ${FIRST_COMMIT}..HEAD

# Get detailed view of new changes
git diff ${FIRST_COMMIT}..HEAD
```

### 3. Prepare Updated Description

Preserve the original PR content and append a "Follow-up Changes" section:

```markdown
<original PR body preserved as-is>

---

## Follow-up Changes

<Date or context for when these changes were added>

### Additional Changes

- <Change 1: what and why>
- <Change 2: what and why>

### New Commits

- `<sha>` <commit message>
- `<sha>` <commit message>

### Reason for Changes

<Brief explanation of why follow-up changes were needed>
- Code review feedback
- Bug discovered during testing
- Expanded scope
- etc.
```

### 4. Update the PR

```bash
gh pr edit --body "$(cat <<'EOF'
<complete updated body here>
EOF
)"
```

### 5. Add a Comment (Optional)

For visibility, add a PR comment summarizing the update:

```bash
gh pr comment --body "$(cat <<'EOF'
## PR Updated

Added follow-up changes:
- <brief summary of changes>

See updated PR description for details.
EOF
)"
```

## Guidelines

**DO:**
- Preserve the original PR description intact
- Clearly separate follow-up changes with `---` divider
- Include dates/context for when changes were added
- Explain WHY follow-up changes were needed
- Reference code review comments if applicable

**DON'T:**
- Rewrite the original description (preserve history)
- Remove the original context
- Make it unclear what was in the original PR vs. added later
- Forget to update the testing section if new tests added

## Multiple Updates

If updating the PR multiple times, stack the follow-up sections:

```markdown
<original PR body>

---

## Follow-up Changes (2024-01-15)

<first round of follow-up changes>

---

## Follow-up Changes (2024-01-16)

<second round of follow-up changes>
```

## Example Workflow

```bash
# 1. View current PR state
gh pr view

# 2. See what's new since PR opened
gh pr view --json commits --jq '.commits | length'
git log --oneline $(gh pr view --json commits --jq '.commits[0].oid')..HEAD

# 3. Update the description
gh pr edit --body "<updated body>"

# 4. Optionally notify reviewers
gh pr comment --body "Updated PR with follow-up fixes for review feedback."
```

## Example Output

```
Updated PR #42: fix(health): wire websocket_connections to actual count

Added follow-up changes section with 2 new commits:
- abc1234 fix: handle edge case for zero connections
- def5678 test: add unit test for connection counting

PR URL: https://github.com/owner/repo/pull/42
```
