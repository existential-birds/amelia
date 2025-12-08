---
name: create-pr
description: Protocol for generating high-quality Pull Requests with self-verifying descriptions.
---

# Pull Request Creation Protocol

**Role:** Technical Communicator.
**Objective:** Create a PR description that allows a reviewer to understand *what*, *why*, and *how* without reading the code.

## 🔍 Phase 1: Impact Analysis

You generally know what you did, but now you must verify the scope.

1.  **Diff Review:**
    *   Command: `git diff main..HEAD --stat`
    *   Question: "Is this PR too large?" (If >500 lines, mention broadly what is covered).

2.  **Commit Log Review:**
    *   Command: `git log main..HEAD --oneline`
    *   Question: "Does the story makes sense?"

## ✍️ Phase 2: Description Generation

Construct the PR description using the following strict template. Do not omit sections.

### Template

```markdown
## 🎯 Goal
[One sentence: What does this PR accomplish?]

## 🛠 Implementation Details
- **[Component]:** [Brief technical explanation of change]
- **[Component]:** [Brief technical explanation of change]

## 🧪 Verification
| Type | Status | Command/Proof |
| :--- | :--- | :--- |
| **Manual** | [Pass/Fail] | `[How you verified locally]` |
| **Automated** | [Pass/Fail] | `npm test` / `pytest` |
| **Visual** | [N/A or Link] | [Screenshots/Videos] |

## ⚠️ Breaking Changes
- [ ] List any breaking API changes or DB migrations.

## 🔗 Related Issues
- Closes #[Issue Number]
```

## 🚀 Phase 3: Execution and Handoff

1.  **Create PR:**
    *   Command: `gh pr create --title "..." --body "..."`
    *   **Title Rules:** Use Conventional Commits (`type(scope): subject`).

2.  **Self-Review (Post-Create):**
    *   Check the generated link.
    *   Verify the diff looks correct on GitHub (sometimes local diffs hide file mode changes).
