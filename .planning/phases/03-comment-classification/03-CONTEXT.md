# Phase 3: Comment Classification - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Take raw review comments and classify each as actionable or non-actionable based on the configured aggressiveness level. Return structured classification with category, confidence, and actionability. Track processed comments via GitHub thread state (Amelia reply detection). Group actionable comments by file path for efficient batching to the Developer agent. No pipeline orchestration — pure classification and grouping logic.

</domain>

<decisions>
## Implementation Decisions

### Classification output structure
- Return a structured Pydantic model per comment: `actionable: bool`, `category: CommentCategory` enum, `confidence: float (0-1)`, `reason: str`
- 6 categories: `bug`, `security`, `style`, `suggestion`, `question`, `praise`
- Category-to-aggressiveness mapping: critical catches bug+security, standard adds style, thorough adds suggestion+question. Praise is always non-actionable.
- No fix hint for Developer — Developer reads the raw comment body directly. Single responsibility for classifier.
- Configurable confidence threshold (default 0.7) on PRAutoFixConfig — below threshold → skip with structured log

### Prompt & model strategy
- Single system prompt with aggressiveness level as parameter — dynamically adjusts classification criteria
- Batch all unresolved comments in one LLM call — returns list of classifications. Faster, cheaper, LLM sees comment relationships.
- Uses profile's configured driver+model (no dedicated classifier model)
- Register prompt in `PROMPT_DEFAULTS` dict following "classifier.system" naming convention
- Log every classification decision via loguru structured logging: comment_id, category, confidence, actionable. No event bus emission yet (Phase 10 adds persistence/dashboards).

### Comment grouping
- Group actionable comments by file path — all comments on the same file go to Developer together
- General comments (path=None) form their own separate group with full PR context
- Only classify top-level comments (in_reply_to_id=None) — reply chains are follow-ups, original comment captures the request

### State tracking & iteration control
- In-memory per pipeline run — no persistent state storage. GitHub thread resolution status is the source of truth.
- Max iteration detection: count Amelia's footer signature replies in the thread before classifying. If count >= max_iterations config, skip the comment.
- Skip comments that already have an Amelia reply (footer signature match), even if thread isn't resolved — Amelia already attempted this.
- Exception: if a reviewer adds a NEW reply AFTER Amelia's latest reply in a thread, treat that new reply as fresh feedback. Amelia reply count resets for iteration tracking on that thread.

### Claude's Discretion
- Exact prompt wording and classification instructions
- CommentCategory enum implementation details (StrEnum vs IntEnum)
- Internal helper decomposition for grouping logic
- How to structure the batch LLM request/response format
- Whether classifier is a standalone function, a class, or an agent

</decisions>

<specifics>
## Specific Ideas

- Follow the `Disposition` enum + `EvaluatedItem` pattern from `agents/schemas/evaluator.py` for the classification output model
- Use `DriverInterface.generate()` with `schema=` parameter for structured LLM output (Pydantic model enforcement)
- Aggressiveness threshold comparison uses IntEnum ordering: `if comment_category_level <= configured_aggressiveness`

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DriverInterface` protocol (`drivers/base.py`): `generate()` with `schema=` for structured output — use directly for classification
- `Disposition` enum + `EvaluatedItem` pattern (`agents/schemas/evaluator.py`): Reference for classification output schema design
- `AggressivenessLevel` IntEnum (`core/types.py:154-167`): 3 levels, already supports threshold comparisons
- `PRReviewComment` model (`core/types.py:189-222`): Frozen model with all needed fields (body, path, line, diff_hunk, in_reply_to_id, thread_id)
- `PRAutoFixConfig` (`core/types.py`): Add `confidence_threshold: float = 0.7` field
- `PROMPT_DEFAULTS` system (`agents/prompts/defaults.py`): Prompt registration and resolution
- `GitHubPRService` (`services/github_pr.py`): Already filters self-authored comments via footer match — extend or reuse for iteration counting

### Established Patterns
- Structured LLM output via `ToolStrategy(schema=schema)` in ApiDriver
- All core enums and models in `amelia/core/types.py`
- Agent schemas in `amelia/agents/schemas/` directory
- Loguru structured logging with kwargs: `logger.info("msg", key=value)`
- Async throughout — classification must be async

### Integration Points
- `PRAutoFixConfig` needs new `confidence_threshold` field
- New classification schema in `amelia/agents/schemas/`
- New classifier module (function or class) consumable by Phase 4 pipeline
- New prompt in `PROMPT_DEFAULTS` for classifier system prompt
- `GitHubPRService.fetch_review_comments()` provides input data

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-comment-classification*
*Context gathered: 2026-03-13*
