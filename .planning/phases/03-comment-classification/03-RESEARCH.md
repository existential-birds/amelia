# Phase 3: Comment Classification - Research

**Researched:** 2026-03-13
**Domain:** LLM-based comment classification, Pydantic structured output, comment grouping
**Confidence:** HIGH

## Summary

Phase 3 implements a classifier that takes raw PR review comments and produces structured classifications (actionable/non-actionable) with category, confidence, and aggressiveness-aware filtering. The classifier uses the existing `DriverInterface.generate()` with `schema=` for structured LLM output, following the established `EvaluationOutput` pattern from the evaluator agent.

The implementation is well-constrained by CONTEXT.md decisions: batch all comments in one LLM call, use the profile's configured driver+model, track iterations via Amelia footer signature counting, and group actionable comments by file path. No new external dependencies are needed -- this phase uses only existing project infrastructure (Pydantic, loguru, DriverInterface, PRReviewComment, AggressivenessLevel).

**Primary recommendation:** Follow the evaluator agent's pattern exactly -- a Pydantic schema for LLM output, a classifier module with an async classify function, and pure-function helpers for filtering, iteration detection, and grouping.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Classification output: Pydantic model per comment with `actionable: bool`, `category: CommentCategory` enum (6 categories: bug, security, style, suggestion, question, praise), `confidence: float (0-1)`, `reason: str`
- Category-to-aggressiveness mapping: critical catches bug+security, standard adds style, thorough adds suggestion+question. Praise always non-actionable.
- No fix hint for Developer -- Developer reads raw comment body. Single responsibility.
- Configurable confidence threshold (default 0.7) on PRAutoFixConfig -- below threshold means skip with structured log
- Single system prompt with aggressiveness level as parameter -- dynamically adjusts classification criteria
- Batch all unresolved comments in one LLM call -- returns list of classifications
- Uses profile's configured driver+model (no dedicated classifier model)
- Register prompt in `PROMPT_DEFAULTS` dict following "classifier.system" naming convention
- Log every classification decision via loguru structured logging: comment_id, category, confidence, actionable. No event bus emission yet.
- Group actionable comments by file path -- all comments on same file go to Developer together
- General comments (path=None) form their own separate group with full PR context
- Only classify top-level comments (in_reply_to_id=None) -- reply chains are follow-ups
- In-memory per pipeline run -- no persistent state storage. GitHub thread resolution is source of truth.
- Max iteration detection: count Amelia footer signature replies in thread before classifying. If count >= max_iterations config, skip.
- Skip comments that already have an Amelia reply (footer signature match), even if thread is not resolved
- Exception: if reviewer adds NEW reply AFTER Amelia's latest reply, treat that new reply as fresh feedback. Amelia reply count resets for iteration tracking.

### Claude's Discretion
- Exact prompt wording and classification instructions
- CommentCategory enum implementation details (StrEnum vs IntEnum)
- Internal helper decomposition for grouping logic
- How to structure the batch LLM request/response format
- Whether classifier is a standalone function, a class, or an agent

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CMNT-01 | System classifies review comments as actionable vs non-actionable using LLM | Classification schema + DriverInterface.generate() with schema= parameter for structured output |
| CMNT-02 | Classification respects configurable aggressiveness level (critical-only / standard / thorough / exemplary) | AggressivenessLevel IntEnum with threshold comparisons + category mapping |
| CMNT-03 | System tracks processed comment IDs to prevent re-fixing already-handled comments | Amelia footer signature detection in thread replies + in-memory tracking |
| CMNT-04 | System enforces max fix iterations per thread (configurable, default 3) | Count Amelia footer replies in thread, compare against PRAutoFixConfig.max_iterations |
| CMNT-05 | System groups comments by file/function for efficient batching to Developer agent | Group by PRReviewComment.path, None-path forms separate group |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | (project version) | Classification schema, structured LLM output | Already used for all data models in `core/types.py` |
| loguru | (project version) | Structured logging of classification decisions | Project convention, `logger.info("msg", key=value)` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| DriverInterface | N/A (internal) | LLM call with `schema=` for structured output | For the classification LLM call |
| PRReviewComment | N/A (internal) | Input data model | Already exists in `core/types.py` |
| AggressivenessLevel | N/A (internal) | Threshold comparisons | Already exists in `core/types.py` as IntEnum |
| PRAutoFixConfig | N/A (internal) | Config source for max_iterations, aggressiveness | Needs `confidence_threshold` field added |
| AMELIA_FOOTER | N/A (internal) | Footer signature for iteration detection | Already exists in `services/github_pr.py` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| StrEnum for CommentCategory | IntEnum | IntEnum allows ordering for threshold comparison but StrEnum is more readable in JSON. Use StrEnum since threshold logic maps category->aggressiveness level, not category ordering. |

**Installation:**
No new dependencies needed. All libraries already in project.

## Architecture Patterns

### Recommended Project Structure
```
amelia/
├── agents/
│   ├── schemas/
│   │   ├── evaluator.py          # Existing pattern to follow
│   │   └── classifier.py         # NEW: CommentCategory, CommentClassification, ClassificationResult
│   └── prompts/
│       └── defaults.py           # ADD: "classifier.system" entry
├── core/
│   └── types.py                  # MODIFY: Add confidence_threshold to PRAutoFixConfig
└── services/
    └── classifier.py             # NEW: classify_comments(), group_by_file(), filter helpers
```

### Pattern 1: Structured LLM Output via DriverInterface
**What:** Use `driver.generate(prompt=..., system_prompt=..., schema=OutputSchema)` to get validated Pydantic instances from LLM
**When to use:** Always for classification -- guarantees structured output
**Example:**
```python
# Source: amelia/agents/evaluator.py:246-252
response, session_id = await driver.generate(
    prompt=user_prompt,
    system_prompt=system_prompt,
    schema=ClassificationOutput,
    cwd=profile.repo_root,
    session_id=None,
)
# response is now a ClassificationOutput instance
for item in response.classifications:
    logger.info("classified", comment_id=item.comment_id, category=item.category, ...)
```

### Pattern 2: Enum + Threshold Mapping for Aggressiveness
**What:** Map CommentCategory to minimum AggressivenessLevel required, then filter
**When to use:** Determining actionability based on configured aggressiveness
**Example:**
```python
# Category -> minimum aggressiveness level needed to act on it
CATEGORY_THRESHOLD: dict[CommentCategory, AggressivenessLevel] = {
    CommentCategory.BUG: AggressivenessLevel.CRITICAL,
    CommentCategory.SECURITY: AggressivenessLevel.CRITICAL,
    CommentCategory.STYLE: AggressivenessLevel.STANDARD,
    CommentCategory.SUGGESTION: AggressivenessLevel.THOROUGH,
    CommentCategory.QUESTION: AggressivenessLevel.THOROUGH,
    CommentCategory.PRAISE: None,  # Never actionable
}

def is_actionable(category: CommentCategory, level: AggressivenessLevel) -> bool:
    threshold = CATEGORY_THRESHOLD[category]
    if threshold is None:
        return False
    return level >= threshold
```

### Pattern 3: Iteration Detection via Thread Analysis
**What:** Count Amelia footer signatures in comment thread to detect iteration count
**When to use:** Before classification, to skip comments that exceeded max iterations
**Example:**
```python
def count_amelia_replies(thread_comments: list[PRReviewComment]) -> int:
    return sum(1 for c in thread_comments if AMELIA_FOOTER in c.body)

def has_new_feedback_after_amelia(thread_comments: list[PRReviewComment]) -> bool:
    """Check if reviewer added new feedback after Amelia's last reply."""
    last_amelia_idx = -1
    for i, c in enumerate(thread_comments):
        if AMELIA_FOOTER in c.body:
            last_amelia_idx = i
    return last_amelia_idx >= 0 and last_amelia_idx < len(thread_comments) - 1
```

### Anti-Patterns to Avoid
- **Classifying reply comments:** Only classify top-level comments (in_reply_to_id=None). Replies are follow-ups; the original comment captures the request.
- **Per-comment LLM calls:** Batch all comments in one call. The LLM sees comment relationships, and it is faster and cheaper.
- **Storing iteration state outside GitHub:** GitHub thread resolution is the source of truth. Do not build a separate state store for processed comment IDs.
- **Embedding fix hints in classification:** The classifier has single responsibility -- classification only. The Developer agent reads the raw comment body directly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured LLM output | Custom JSON parsing | `DriverInterface.generate(schema=...)` | Handles schema enforcement, retries, provider differences |
| Footer signature matching | New regex pattern | `AMELIA_FOOTER` constant from `services/github_pr.py` | Already defined, used in existing skip logic |
| Aggressiveness config | New config model | `PRAutoFixConfig` (add `confidence_threshold` field) | Config model already exists with all other fields |
| Prompt management | Inline prompt strings | `PROMPT_DEFAULTS` registration system | Allows runtime customization via dashboard |

## Common Pitfalls

### Pitfall 1: Aggressiveness Level Mismatch
**What goes wrong:** CONTEXT.md mentions 3 levels (critical=1, standard=2, thorough=3) but REQUIREMENTS.md lists 4 (critical, standard, thorough, exemplary). The AggressivenessLevel IntEnum in code has only 3 values.
**Why it happens:** Requirements were written before implementation decisions narrowed scope.
**How to avoid:** Follow the code (3 levels). The CONTEXT.md decisions explicitly map to 3 levels only. The category mapping covers all 6 categories across 3 levels. No need for a 4th level.
**Warning signs:** Tests checking for "exemplary" level will fail.

### Pitfall 2: Thread Comments Need Full Fetch for Iteration Detection
**What goes wrong:** `fetch_review_comments()` returns only unresolved, non-Amelia comments. But iteration detection needs to see ALL comments in a thread (including Amelia's own replies) to count attempts.
**Why it happens:** The existing service filters out Amelia comments before returning.
**How to avoid:** Either (a) add a separate method to fetch raw thread comments without filtering, or (b) pass the full REST response data to the classifier before filtering. Option (a) is cleaner -- add a `fetch_thread_comments()` or modify `fetch_review_comments()` to also return thread metadata.
**Warning signs:** Amelia reply count always returns 0 because Amelia comments are filtered out.

### Pitfall 3: Confidence Threshold vs Actionability
**What goes wrong:** Confusing confidence threshold with aggressiveness-based actionability. Both can make a comment non-actionable, but for different reasons.
**How to avoid:** Apply in order: (1) filter top-level only, (2) check iteration limits, (3) LLM classifies with category+confidence, (4) apply confidence threshold, (5) apply aggressiveness threshold. Log each filter step separately.
**Warning signs:** Comments being silently dropped without knowing which filter caught them.

### Pitfall 4: Batch LLM Call Token Limits
**What goes wrong:** PRs with many long comments could exceed model context window when batched.
**Why it happens:** Batching all comments in one call is faster but unbounded.
**How to avoid:** For v1, log a warning if input exceeds a threshold (e.g., 50 comments or estimated 50k tokens). Do not implement splitting now -- it is a premature optimization for edge cases. The warning surfaces the issue for future work.
**Warning signs:** LLM returns truncated or incomplete classifications.

### Pitfall 5: Fresh Feedback Detection Edge Case
**What goes wrong:** The "reset iteration count when reviewer adds new reply after Amelia" rule requires careful thread ordering by created_at.
**Why it happens:** GitHub API may not guarantee comment order within a thread.
**How to avoid:** Sort thread comments by `created_at` before analyzing. The `PRReviewComment.created_at` is a datetime field that supports comparison.
**Warning signs:** Amelia skips comments that have new reviewer feedback because it counted old iterations.

## Code Examples

### Classification Schema (new file: `amelia/agents/schemas/classifier.py`)
```python
# Follows Disposition + EvaluatedItem pattern from evaluator.py
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class CommentCategory(StrEnum):
    """Category of a PR review comment."""
    BUG = "bug"
    SECURITY = "security"
    STYLE = "style"
    SUGGESTION = "suggestion"
    QUESTION = "question"
    PRAISE = "praise"


class CommentClassification(BaseModel):
    """Classification of a single review comment."""
    model_config = ConfigDict(frozen=True)

    comment_id: int = Field(description="GitHub comment ID")
    category: CommentCategory = Field(description="Classification category")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")
    actionable: bool = Field(description="Whether this comment requires action")
    reason: str = Field(description="Brief explanation for the classification")


class ClassificationOutput(BaseModel):
    """Schema for LLM-generated classification output (batch)."""
    classifications: list[CommentClassification]
```

### PRAutoFixConfig Update
```python
# Add to PRAutoFixConfig in core/types.py
confidence_threshold: float = Field(
    default=0.7, ge=0.0, le=1.0,
    description="Minimum confidence to act on a classification",
)
```

### Grouping Helper
```python
from collections import defaultdict

def group_comments_by_file(
    comments: list[PRReviewComment],
    classifications: dict[int, CommentClassification],
) -> dict[str | None, list[PRReviewComment]]:
    """Group actionable comments by file path.

    Args:
        comments: Original review comments.
        classifications: Map of comment_id -> classification.

    Returns:
        Dict mapping file path (or None for general) to list of comments.
    """
    groups: dict[str | None, list[PRReviewComment]] = defaultdict(list)
    for comment in comments:
        classification = classifications.get(comment.id)
        if classification and classification.actionable:
            groups[comment.path].append(comment)
    return dict(groups)
```

### Prompt Registration
```python
# Add to PROMPT_DEFAULTS in agents/prompts/defaults.py
"classifier.system": PromptDefault(
    agent="classifier",
    name="Classifier System Prompt",
    description="Instructions for classifying PR review comments",
    content="""You are a PR review comment classifier. ...""",
),
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Parse comments with regex rules | LLM classification with structured output | Current design | Much higher accuracy, handles nuance |
| Per-comment API calls | Batch classification in single call | Current design | Lower cost, sees comment relationships |
| Persistent state DB for tracking | GitHub thread resolution as source of truth | Current design | Simpler, no state sync issues |

## Open Questions

1. **Thread comment fetching for iteration detection**
   - What we know: `fetch_review_comments()` filters out Amelia's own replies, but iteration detection needs to count them
   - What's unclear: Whether to add a new method or modify the existing one
   - Recommendation: Add a lightweight helper that fetches all comments in a thread (including Amelia's) for iteration analysis. Keep `fetch_review_comments()` unchanged since it serves the main fetch-comments use case well.

2. **AMELIA_FOOTER import location**
   - What we know: `AMELIA_FOOTER` is defined in `services/github_pr.py`
   - What's unclear: Whether the classifier module should import from the service module (creates coupling) or the constant should move to a shared location
   - Recommendation: Import `AMELIA_FOOTER` from `services/github_pr.py` for now. It is a simple constant with no risk of circular imports. Move it later if needed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (auto mode) |
| Config file | `pyproject.toml` (line 55: `asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/unit/services/ -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CMNT-01 | LLM classifies comments as actionable/non-actionable | unit | `uv run pytest tests/unit/services/test_classifier.py::test_classify_comments_returns_structured_output -x` | No -- Wave 0 |
| CMNT-01 | Classification schema validates correctly | unit | `uv run pytest tests/unit/agents/schemas/test_classifier_schema.py -x` | No -- Wave 0 |
| CMNT-02 | Aggressiveness filtering: critical only gets bug+security | unit | `uv run pytest tests/unit/services/test_classifier.py::test_aggressiveness_critical_filters_non_critical -x` | No -- Wave 0 |
| CMNT-02 | Aggressiveness filtering: standard adds style | unit | `uv run pytest tests/unit/services/test_classifier.py::test_aggressiveness_standard_includes_style -x` | No -- Wave 0 |
| CMNT-02 | Aggressiveness filtering: thorough adds suggestion+question | unit | `uv run pytest tests/unit/services/test_classifier.py::test_aggressiveness_thorough_includes_suggestions -x` | No -- Wave 0 |
| CMNT-03 | Skip comments with existing Amelia reply | unit | `uv run pytest tests/unit/services/test_classifier.py::test_skip_comments_with_amelia_reply -x` | No -- Wave 0 |
| CMNT-03 | Fresh feedback after Amelia reply is not skipped | unit | `uv run pytest tests/unit/services/test_classifier.py::test_fresh_feedback_after_amelia_not_skipped -x` | No -- Wave 0 |
| CMNT-04 | Max iterations enforcement | unit | `uv run pytest tests/unit/services/test_classifier.py::test_max_iterations_enforcement -x` | No -- Wave 0 |
| CMNT-04 | Iteration count resets on new reviewer feedback | unit | `uv run pytest tests/unit/services/test_classifier.py::test_iteration_count_resets_on_new_feedback -x` | No -- Wave 0 |
| CMNT-05 | Group comments by file path | unit | `uv run pytest tests/unit/services/test_classifier.py::test_group_comments_by_file -x` | No -- Wave 0 |
| CMNT-05 | General comments (path=None) in separate group | unit | `uv run pytest tests/unit/services/test_classifier.py::test_general_comments_separate_group -x` | No -- Wave 0 |
| CMNT-01 | confidence_threshold field on PRAutoFixConfig | unit | `uv run pytest tests/unit/services/test_classifier.py::test_confidence_threshold_config -x` | No -- Wave 0 |
| CMNT-01 | Below-threshold classifications are skipped | unit | `uv run pytest tests/unit/services/test_classifier.py::test_below_threshold_skipped -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/services/test_classifier.py tests/unit/agents/schemas/test_classifier_schema.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/agents/schemas/test_classifier_schema.py` -- covers schema validation (CommentCategory, CommentClassification, ClassificationOutput)
- [ ] `tests/unit/services/test_classifier.py` -- covers CMNT-01 through CMNT-05 (classification, filtering, iteration, grouping)
- [ ] No new framework install needed -- pytest + pytest-asyncio already configured

## Sources

### Primary (HIGH confidence)
- `amelia/agents/schemas/evaluator.py` -- Disposition + EvaluatedItem pattern for classification schema design
- `amelia/agents/evaluator.py:246-252` -- `driver.generate(schema=EvaluationOutput)` usage pattern
- `amelia/drivers/api/deepagents.py:373-412` -- ToolStrategy structured output implementation
- `amelia/drivers/base.py:142-169` -- DriverInterface protocol with generate() signature
- `amelia/core/types.py:154-257` -- AggressivenessLevel, PRReviewComment, PRAutoFixConfig definitions
- `amelia/services/github_pr.py` -- AMELIA_FOOTER constant, fetch_review_comments(), _should_skip_comment()
- `amelia/agents/prompts/defaults.py` -- PROMPT_DEFAULTS registration pattern

### Secondary (MEDIUM confidence)
- None needed -- all relevant patterns exist in codebase

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new dependencies
- Architecture: HIGH -- follows established evaluator pattern exactly
- Pitfalls: HIGH -- identified from direct code analysis of existing implementations

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable -- internal codebase patterns, no external API changes)
