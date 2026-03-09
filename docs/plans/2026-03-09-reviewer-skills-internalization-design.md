# Reviewer Skills Internalization

## Problem

The reviewer prompts reference external beagle skill files via the `Skill` tool. This has two issues:

1. Users must separately install the beagle skills plugin
2. Only Claude has access to the `Skill` tool — other drivers (OpenAI, Codex) can't load skills

## Solution

Internalize review skills into the Amelia repo and inject them directly into the reviewer prompt at assembly time. This is driver-agnostic and requires no external dependencies.

## Skill File Structure

```
amelia/skills/
└── review/
    ├── __init__.py               # registry, loader, detector
    ├── general.md                # always included (general review type)
    ├── verification.md           # always included (false positive reduction)
    ├── python/
    │   ├── python.md
    │   ├── pytest.md
    │   ├── fastapi.md
    │   ├── sqlalchemy.md
    │   └── postgres.md
    ├── react/
    │   ├── react.md
    │   ├── shadcn.md
    │   ├── vitest.md
    │   ├── react-router.md
    │   └── react-flow.md
    ├── go/
    │   ├── go.md
    │   ├── go-testing.md
    │   ├── go-concurrency.md
    │   └── go-middleware.md
    ├── elixir/
    │   ├── elixir.md
    │   ├── phoenix.md
    │   ├── liveview.md
    │   ├── exunit.md
    │   ├── elixir-security.md
    │   └── elixir-performance.md
    ├── swift/
    │   ├── swift.md
    │   ├── swiftui.md
    │   └── combine.md
    └── security/
        └── general.md            # cross-language security review
```

Skills are plain markdown files copied from beagle (SKILL.md content only, no reference docs). The Python module provides three components:

### Registry

```python
REVIEW_SKILLS: dict[str, list[Path]] = {
    "python": ["python/python.md"],
    "pytest": ["python/pytest.md"],
    "fastapi": ["python/fastapi.md"],
    # ...
}

REVIEW_TYPE_SKILLS: dict[str, list[Path]] = {
    "general": ["general.md", "verification.md"],
    "security": ["security/general.md"],
}
```

### Stack Detection

`detect_stack(file_paths: list[str], diff_content: str) -> set[str]`

Two-pass detection:

1. **File extensions** — `.py` -> `"python"`, `.tsx` -> `"react"`, `.go` -> `"go"`, `.ex` -> `"elixir"`, `.swift` -> `"swift"`, etc. Path patterns like `test_*.py` or `conftest.py` add `"pytest"`.
2. **Import scanning** — regex on diff content for framework imports: `from fastapi` -> `"fastapi"`, `from sqlalchemy` -> `"sqlalchemy"`, `from @xyflow` -> `"react-flow"`, etc.

### Skill Loader

`load_skills(tags: set[str], review_types: list[str]) -> str`

Resolves tags + review types to file paths via the registry, reads them, deduplicates, and returns concatenated markdown.

## Reviewer Prompt Changes

The current prompt in `defaults.py` (`reviewer.agentic` key) instructs the LLM to detect technologies and use the `Skill` tool to load beagle skills. The new prompt removes all Skill/beagle references and uses an `{injected_skill_content}` placeholder:

```
You are an expert code reviewer.

## Review Guidelines

{injected_skill_content}

## Process

1. Run `git diff --name-only {base_commit}` to see what files changed
2. Run `git diff {base_commit}` to get the full diff
3. Review the code against the guidelines above
4. Output your review in the following format:
   [REVIEW_OUTPUT_FORMAT — unchanged from current]

## Rules
[unchanged from current, minus "Load skills BEFORE reviewing"]
```

Technology detection and skill selection moves from LLM-side to Python-side — deterministic and driver-agnostic.

## Prompt Assembly Flow

In `call_reviewer_node()`:

1. Run `git diff --name-only {base_commit}` to get changed file paths
2. Call `detect_stack(file_paths, diff_content)` -> tags
3. Read `review_types` from `profile.agents["reviewer"].options.get("review_types", ["general"])`
4. Call `load_skills(tags, review_types)` -> concatenated markdown
5. Format the prompt template with `injected_skill_content`
6. Pass assembled prompt to reviewer agent

## Review Types

Configured in profile options:

```yaml
agents:
  reviewer:
    driver: "api:openai"
    model: "gpt-4o"
    options:
      review_types: ["general"]
      max_iterations: 5
```

Available types:
- `"general"` — standard code review (loads `general.md` + `verification.md` + stack-detected skills)
- `"security"` — security-focused (loads `security/general.md` + language-specific security skills)
- Future: `"performance"`, `"accessibility"`, etc.

Multiple types trigger separate reviewer runs, each producing its own `ReviewResult`. For example, `review_types: ["general", "security"]` runs two review passes with different prompts.

### State Changes

`last_review: ReviewResult | None` becomes `last_reviews: list[ReviewResult]`.

Each result has `reviewer_persona` set to the review type name (e.g., `"general"`, `"security"`).

### Routing Changes

`route_after_task_review()` checks `all(r.approved for r in last_reviews)`. Highest severity across all reviews determines aggregate severity.

## On-Demand Review from Dashboard

### API Endpoint

```
POST /api/v1/workflows/{workflow_id}/review
Body: {
  "review_types": ["general"],
  "mode": "review_only" | "review_fix",
  "base_commit": "abc123"              // optional
}
```

- `review_only` — runs just the reviewer node, returns feedback via WebSocket events
- `review_fix` — invokes the existing review pipeline (Reviewer -> Evaluator -> Developer loop)

### Dashboard UI

"Request Review" button on the workflow detail page. Opens a dialog with:
- Checkboxes for review type(s): General, Security, etc.
- Toggle for mode: "Review only" (default) vs "Review & fix"
- Submit button

Results appear in the existing ActivityLog via WebSocket events (`REVIEW_COMPLETED`). No new pages or components needed beyond the dialog.

## What Doesn't Change

- `Reviewer` class and `agentic_review()` method — same interface, different prompt content
- Review output format — same markdown structure, same parsing logic
- Evaluator and developer agents
- Existing review pipeline (used for `review_fix` mode)
- WebSocket event system

## Migration

The old prompt in `defaults.py` referencing beagle skills is replaced directly. No backwards compatibility needed — it's a hardcoded default, not user-facing config.
