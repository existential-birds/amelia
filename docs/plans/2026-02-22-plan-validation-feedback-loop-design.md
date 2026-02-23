# Plan Validation Feedback Loop Design

## Problem

When the plan validator fails, two things go wrong:

1. **Schema validation errors restart the entire workflow.** The codex driver wraps `ValidationError` as `ModelProviderError`, which is in `TRANSIENT_EXCEPTIONS`. The orchestrator retries the whole workflow from scratch — re-running the architect, re-generating the plan. This is a content issue being treated as a network issue.

2. **No feedback loop to the architect.** The graph is `architect_node → plan_validator_node → human_approval_node` with no conditional edge. When validation detects structural issues, there's no path back to the architect to fix them. The validator either uses a heuristic fallback (silently degrading quality) or the error propagates up.

## Design Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | LLM quality checks | Defer. This pass is structural checks only. |
| 2 | Regex fallback validation | Yes — same structural checks run on fallback output. |
| 3 | Max revisions exhausted | Escalate to `human_approval_node` with warning. |
| 4 | SchemaValidationError retry | Always propagate immediately. No driver-level retry. |
| 5 | Codex streaming skip | Keep as-is. Only change `_validate_schema()` and `generate()`. |

## Approach

Expand `plan_validator_node` with structural checks (deterministic, no LLM). Add a conditional edge from the validator back to the architect when issues are found. Separate schema validation errors from transient network errors with a new exception type.

This follows the existing developer-reviewer feedback loop pattern: structured result in state, iteration counter, conditional routing, feedback injection in prompt.

## New Types

### SchemaValidationError — `amelia/core/exceptions.py`

Subclass of `AmeliaError`, NOT `ModelProviderError`. Not in `TRANSIENT_EXCEPTIONS`. Raised by drivers when Pydantic schema validation fails on final structured output. Always propagates immediately — no retries.

```python
class SchemaValidationError(AmeliaError):
    def __init__(
        self,
        message: str,
        provider_name: str | None = None,
        original_message: str | None = None,
    ) -> None: ...
```

### PlanValidationResult — `amelia/core/types.py`

Mirrors `ReviewResult` but for plan quality.

```python
class PlanValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    valid: bool
    issues: list[str]
    severity: Severity  # critical | major | minor | none
```

## State Changes — `amelia/pipelines/implementation/state.py`

```python
plan_validation_result: PlanValidationResult | None = None
plan_revision_count: int = 0
```

## Structural Validation — `amelia/pipelines/implementation/nodes.py`

Pure function `validate_plan_structure(goal, plan_markdown) -> PlanValidationResult`. Runs on both happy path and regex fallback output.

Checks:
- At least one `### Task N:` header
- Goal section present (non-empty after extraction)
- Minimum content length (e.g., 200 chars)

## Graph Changes — `amelia/pipelines/implementation/graph.py`

Replace direct edge with conditional routing:

```python
workflow.add_conditional_edges(
    "plan_validator_node",
    route_after_plan_validation,
    {
        "approved": "human_approval_node",
        "revise": "architect_node",
        "escalate": "human_approval_node",
    }
)
```

## Routing — `amelia/pipelines/implementation/routing.py`

`route_after_plan_validation()` follows `route_after_task_review()` pattern:

- `valid == True` → `"approved"`
- `plan_revision_count >= max_iterations` → `"escalate"` (log warning, let human decide)
- Otherwise → `"revise"`

Max iterations from `profile.agents["plan_validator"].options.get("max_iterations", 3)`.

## Architect Revision — `amelia/agents/architect.py`

Reuses the same feedback injection pattern as `Developer._build_prompt()`. In `Architect._build_agentic_prompt()`, append validation issues:

```python
# Same pattern as Developer's review feedback injection
if state.plan_validation_result and not state.plan_validation_result.valid:
    issues = "\n".join(f"- {i}" for i in state.plan_validation_result.issues)
    parts.append(f"\n\nThe plan validator found structural issues:\n{issues}")
    parts.append("Revise the plan to address these issues.")
```

## Driver Exception Changes

| Driver | File | Site | Current | New |
|--------|------|------|---------|-----|
| Codex | `codex.py` | `_validate_schema()` | `ModelProviderError` | `SchemaValidationError` |
| Codex | `codex.py` | `generate()` schema block | `ModelProviderError` | `SchemaValidationError` |
| Codex | `codex.py` | streaming events | Skip & continue | **No change** |
| Claude | `claude.py` | `generate()` | `RuntimeError` | `SchemaValidationError` |
| DeepAgents | `deepagents.py` | `generate()` | `RuntimeError` | `SchemaValidationError` |

## extraction.py — No Changes

`extract_structured` lets exceptions propagate. After driver changes, `SchemaValidationError` propagates instead of `RuntimeError`/`ModelProviderError`. The caller (`plan_validator_node`) catches it.

## Code Reuse

- **Routing:** `route_after_plan_validation` mirrors `route_after_task_review` — same shape
- **Feedback injection:** Architect appends validation issues like Developer appends review comments
- **State:** `plan_validation_result` + `plan_revision_count` mirrors `last_review` + `task_review_iteration`
- **Validation:** `validate_plan_structure()` is a pure function, testable independently
