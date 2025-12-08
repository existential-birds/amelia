---
name: gen-release-notes
description: Protocol for generating SemVer-compliant release notes. Filters noise and categorizes impact.
---

# Release Notes Generation

**Role:** Release Manager.
**Objective:** Translate git history into user value.

## 🔍 Phase 1: History Extraction

1.  **Define Range:**
    *   Input: `PREV_TAG` (default: latest git tag).
    *   Range: `PREV_TAG..HEAD`.

2.  **Noise Filtering (Crucial):**
    *   **Exclude:** `chore`, `ci`, `test`, `style`, `refactor` (unless critical).
    *   **Include:** `feat`, `fix`, `docs` (if user-facing), `perf`.
    *   **Tool:** `git log {RANGE} --no-merges --format="%s"`

## 🧠 Phase 2: Impact Categorization

Map commits to [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) sections:

| Commit Type | Changelog Section |
| :--- | :--- |
| `feat` | **Added** |
| `fix` | **Fixed** |
| `perf` | **Changed** |
| `!` (Breaking) | **Changed** (Add WARNING) |
| `deprecated` | **Deprecated** |

**Rule:** If a commit is titled "update utils", read the diff. What *actually* changed?

## ✍️ Phase 3: Drafting

Draft the notes in `releases/VERSION.md` (or temp file).

### Style Guide
*   **Audience:** Users and Developers consuming the library/app.
*   **Tone:** Professional, direct.
*   **Format:** `- **[Scope]** Description usually in past tense or imperative.` (e.g., "Added support for X").

### Example Output
```markdown
## [1.2.0] - 2024-03-15

### Added
- **Dashboard:** New visualization for Agent workflow steps.
- **API:** `/health` endpoint now returns DB latency.

### Fixed
- **Core:** Resolved race condition in state management.
```

## 🚀 Phase 4: SemVer Recommendation

*   **MAJOR:** If breaking changes (`!`) found.
*   **MINOR:** If `feat` found.
*   **PATCH:** If only `fix`/`perf`/`docs`.

**Output:** "Recommended Version: X.Y.Z based on [Analysis]."
