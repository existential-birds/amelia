---
name: update-pr-desc
description: Protocol for maintaining PR description accuracy as the branch evolves.
---

# PR Description Maintenance

**Role:** Documentation Steward.
**Objective:** Ensure the PR description reflects reality, not history.

## 🧠 Reasoning

Code evolves during the review process. A PR description that describes the *initial* state but ignores subsequent refactors is misleading.

## 🔄 Phase 1: Delta Analysis

1.  **Identify Changes:**
    *   Compare current `HEAD` vs the state when the PR was opened/last updated.
    *   **Tool:** `git diff {OLD_SHA}..HEAD`

2.  **Determine Impact:**
    *   Did we change the implementation approach? (e.g., switched from polling to WebSockets).
    *   Did we add new dependencies?

## 📝 Phase 2: Update Execution

1.  **Fetch Current Body:**
    *   `gh pr view {PR_NUMBER} --json body`

2.  **Append/Edit:**
    *   **If minor fix:** Append a "Update: [Date]" note.
    *   **If major refactor:** REWRITE the "Implementation Details" section.
    *   **Update Verification:** If new tests were added, update the Verification table.

3.  **Push Update:**
    *   `gh pr edit {PR_NUMBER} --body "..."`

## 📣 Phase 3: Notification

1.  **Notify Reviewers:**
    *   If the change was significant, leave a comment:
    *   `gh pr comment {PR_NUMBER} --body "🔄 Updated PR description to reflect the switch to [New Approach]."`
