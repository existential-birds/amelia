# Brainstorm Workflow ID Design

**Issue**: #443
**Date**: 2026-02-15

## Problem

Brainstorm handoff generates workflow IDs like `brainstorm-d9336c40-4ce9-4b12-81e1-099bb70eaa01` (47 chars), overflowing the dashboard Job Queue card.

## Solution

Use a slugified title + 8-char hash, capped at 24 characters total.

**Format**: `{slug}-{session_id[:8]}`
**Fallback** (no title): `brainstorm-{session_id[:8]}`

Examples:
- "Add dark mode support" → `add-dark-mode-d9336c40` (22 chars)
- "Fix" → `fix-d9336c40` (12 chars)
- No title → `brainstorm-d9336c40` (19 chars)

## Components

### 1. `slugify()` utility

New function in `amelia/core/text.py`:

- Lowercase the input
- Replace spaces and non-alphanumeric chars with dashes
- Collapse consecutive dashes
- Strip leading/trailing dashes
- Truncate to `max_length` (default 15), breaking at a dash boundary to avoid mid-word cuts

### 2. `handoff_to_implementation()` change

In `amelia/server/services/brainstorm.py` line 980:

- When `issue_title` is provided: `f"{slugify(issue_title, max_length=15)}-{session_id[:8]}"`
- When no title: `f"brainstorm-{session_id[:8]}"`
- Empty slug after stripping special chars → use fallback

### 3. Validation

No changes needed to `CreateWorkflowRequest.validate_issue_id` — output is already alphanumeric + dashes only, under 100 chars.

## Edge Cases

- Title is all special chars → empty slug → fallback to `brainstorm-{hash}`
- Title starts/ends with dashes after stripping → trimmed
- Very short title → short slug, still unique via hash suffix

## Testing

- Unit tests for `slugify()`: normal titles, special chars, empty input, exact-length truncation, mid-word truncation at dash boundary
- Unit test for `handoff_to_implementation()`: verify short ID with title, fallback without title

## Backward Compatibility

Old workflows keep their existing long-format IDs. New brainstorm handoffs use the new short format. No migration needed.
