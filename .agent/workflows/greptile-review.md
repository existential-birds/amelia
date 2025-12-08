---
name: greptile-review
description: Protocol for ingesting and processing external automated reviews (Greptile).
---

# External Review Ingestion

**Role:** Code Review Triager.
**Objective:** Signal-to-noise filtering. Extract value from automated review bots.

## 📥 Phase 1: Ingestion

1.  **Fetch Context:**
    *   Get PR Metadata: `gh pr view --json number`.

2.  **Fetch Comments:**
    *   Target `greptile-apps[bot]`.
    *   **Tool:** `gh api` to fetch review comments.

## 🧠 Phase 2: Evaluation (The Filter)

**Treat the bot as a Junior Engineer with infinite stamina but zero context.**

Pass the fetched content to the **Eval Feedback** workflow with strict instructions:

*   **Ignore:** Stylistic nitpicks (unless strictly lint-related).
*   **Highlight:** Logic errors, potential bugs, security risks.
*   **Verify:** "Does this suggestion actually work in our context?"

**Output:** A distilled list of *Actionable Items*.

## 🚀 Phase 3: Action Plan

For each actionable item:
1.  Create a task in `task.md`.
2.  Link to the comment ID.
3.  Status: `Pending Verification`.
