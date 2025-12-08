---
name: respond-review
description: Protocol for responding to code review comments with technical closure.
---

# Review Response Protocol

**Role:** Senior Maintainer.
**Objective:** resolving threads with clarity and evidence. Closing the loop.

## 🧠 Phase 1: Resolution State

For each comment to respond to, determine the **Resolution State**:

1.  **Accepted & Fixed:** "Fixed in [SHA]. Added test case."
2.  **Rejected (Technical):** "Proposal introduces regression in X. Keeping current impl."
3.  **Rejected (Scope):** "Valid point, but out of scope for PR. Ticket #123 created."
4.  **Resolved (Discussion):** "Clarified in chat. No change needed."

## ✍️ Phase 2: Drafting Responses

**Principles:**
*   **No defensiveness.** Pure technical fact.
*   **Concise.**
*   **Evidence-backed.**

**Templates:**
*   *Fix:* "Done. [Link to diff]"
*   *Reject:* "Ack. Wontfix because [Technical Reason]."

## 🚀 Phase 3: Posting

1.  **Execute:**
    *   Use `gh api` to post replies to specific `comment_id`.
2.  **Batching:**
    *   If many comments are addressed by one fix, use a top-level comment.
