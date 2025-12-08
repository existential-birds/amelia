---
name: commit-push
description: Agentic protocol for safely committing and pushing changes. Emphasizes verification of staged content and adherence to Conventional Commits.
---

# Git Operation: Commit & Push

**Role:** Git Operator & Quality Gatekeeper.
**Objective:** Maintain a clean, atomic, and descriptive history.

## 🛑 Phase 1: Pre-Flight Safety Checks

Before touching the staging area, verify the current state.

1.  **Status Check:**
    *   **Action:** `run_command('git status')`
    *   **Verify:** Are there unexpected untracked files? (e.g., `.env`, temporary builds).
    *   **Decision:** If yes, ignore them or delete them. Do not commit junk.

2.  **Diff Analysis:**
    *   **Action:** `run_command('git diff')` (unstaged) and `run_command('git diff --cached')` (staged).
    *   **Verify:** "Does this code do what the user asked?"
    *   **Verify:** "Are there debug prints (console.log, print) or commented-out code?"
    *   **Action:** Clean up artifacts before proceeding.

## 📝 Phase 2: Staging & Committing

1.  **Atomic Staging:**
    *   **Action:** `git add <file>` (Prefer specific files over `git add .` unless you are sure of everything).

2.  **Commit Message Engineering:**
    *   **Standard:** [Conventional Commits](https://www.conventionalcommits.org/)
    *   **Format:** `<type>(<scope>): <subject>`
    *   **Types:**
        *   `feat`: New feature (user-facing).
        *   `fix`: Bug fix (user-facing).
        *   `docs`: Documentation only.
        *   `style`: Formatting, missing semi-colons, etc.
        *   `refactor`: Code change that neither fixes a bug nor adds a feature.
        *   `test`: Adding tests.
        *   `chore`: Maintainance.

3.  **Execute:**
    *   `run_command('git commit -m "..."')`

## 🚀 Phase 3: Push & Verify

1.  **Push:**
    *   `run_command('git push')`
    *   **Handle Rejection:** If rejected (non-fast-forward), run `git pull --rebase` and retry.

2.  **Final Verification:**
    *   `run_command('git status')` -> Should be clean and ahead/up-to-date.
