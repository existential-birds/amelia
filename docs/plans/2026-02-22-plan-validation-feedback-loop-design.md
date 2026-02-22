# Plan Validation Feedback Loop Design

## Problem

When the plan validator fails, two things go wrong:

1. **Schema validation errors restart the entire workflow.** The codex driver wraps `ValidationError` as `ModelProviderError`, which is in `TRANSIENT_EXCEPTIONS`. The orchestrator retries the whole workflow from scratch — re-running the architect, re-generating the plan. This is a content issue being treated as a network issue.

2. **No feedback loop to the architect.** The graph is `architect_node → plan_validator_node → human_approval_node` with no conditional edge. When validation detects structural issues, there's no path back to the architect to fix them. The validator either uses a heuristic fallback (silently degrading quality) or the error propagates up.

## Approach

Expand `plan_validator_node` with structural + basic quality checks. Add a conditional edge from the validator back to the architect when issues are found. Separate schema validation errors from transient network errors with a new exception type.

This follows the existing developer-reviewer feedback loop pattern: structured result in state, iteration counter, conditional routing.

## New Types

### SchemaValidationError

New exception in `amelia/core/exceptions.py`. Subclass of `AmeliaError`, NOT `ModelProviderError`. Not in `TRANSIENT_EXCEPTIONS`. Raised by all three drivers when Pydantic schema validation fails on LLM output.

```python
class SchemaValidationError(AmeliaError):
    def __init__(
        self,
        message: str,
        provider_name: str | None = None,
        original_message: str | None = None,
    ) -> None: ...
```

### PlanValidationResult

New model in `amelia/core/types.py`. Mirrors `ReviewResult` but for plan quality.

```python
class PlanValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    valid: bool
    issues: list[str]
    severity: Severity
```

## State Changes

Add to `ImplementationState`:

```python
plan_validation_result: PlanValidationResult | None = None
plan_revision_count: int = 0
```

## Validation Logic

After extraction in `plan_validator_node`, run checks:

**Structural (deterministic):**
- At least one `### Task N:` header
- Goal section present (`**Goal:**` or equivalent)
- Minimum content length (not just a title)

**Basic quality (LLM-assisted):**
- Tasks are specific (not "implement the feature")
- File paths referenced are plausible
- Each task has deliverables or acceptance criteria

Result stored in `plan_validation_result` regardless of outcome.

## Graph Changes

Replace direct edge with conditional routing:

```python
workflow.add_conditional_edges(
    "plan_validator_node",
    route_after_plan_validation,
    {
        "approved": "human_approval_node",
        "revise": "architect_node",
        "fail": END,
    }
)
```

**route_after_plan_validation:**
- `valid == True` → `"approved"`
- `plan_revision_count >= max` → `"fail"`
- Otherwise → `"revise"`

## Architect Revision

When `call_architect_node` runs with `plan_validation_result.valid == False`, append issues to the prompt:

```
Your previous plan had these issues:
- Missing ### Task headers for structured task execution
- Task 2 has no clear deliverables
Please revise the plan file.
```

Session continuity gives the architect context from its previous attempt.

## Driver Exception Changes

All three drivers change schema validation failures from `ModelProviderError` to `SchemaValidationError`:

- **Codex** (`codex.py`): Two locations where `ValidationError` is caught
- **Claude** (`claude.py`): Currently raises `RuntimeError` — change to `SchemaValidationError`
- **API** (`deepagents.py`): Schema failures through `ToolStrategy`

The `plan_validator_node` catches `SchemaValidationError` in its fallback path alongside `RuntimeError`.

## Config

Max plan revisions controlled by agent config option (default: 2). Accessed via `profile.get_agent_config("plan_validator").options.get("max_revisions", 2)`.
