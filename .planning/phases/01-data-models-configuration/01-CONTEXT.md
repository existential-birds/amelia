# Phase 1: Data Models & Configuration - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

All Pydantic models and configuration structures for PR auto-fix: `PRSummary`, `PRReviewComment`, `PRAutoFixConfig`, `AggressivenessLevel` enum. Every downstream component (GitHub API layer, classification, pipeline, orchestration) builds against these typed interfaces. No runtime behavior — pure data definitions.

</domain>

<decisions>
## Implementation Decisions

### Model placement & structure
- All models go in `amelia/core/types.py` alongside existing `Profile`, `Settings`, `Issue`, etc.
- `PRSummary` and `PRReviewComment` are frozen (immutable) like `Profile` — supports stateless reducer pattern in LangGraph pipelines
- `PRAutoFixConfig` also in `types.py` — it's a Pydantic BaseModel nested in Profile, not a BaseSettings
- Field naming mirrors GitHub API naming (e.g., `number`, `head_branch`, `diff_hunk`) — clear mapping from API response to model

### Config integration with Profile
- `PRAutoFixConfig` attaches as an optional field on `Profile`: `pr_autofix: PRAutoFixConfig | None = None`
- `None` means PR auto-fix is disabled for that profile — polling service skips it entirely (clean opt-in)
- Stored as JSONB column on the `profiles` database table, matching how `agents` and `sandbox` are stored
- Per-PR overrides are ephemeral via CLI flags and API params — not stored in database. Profile config is the baseline.

### Comment model granularity
- `PRReviewComment` mirrors GitHub API fields: `id`, `body`, `path`, `line`, `diff_hunk`, `author`, `created_at`, `in_reply_to_id`
- Handles both inline and general review comments — `path`/`line`/`diff_hunk` are optional (`None` for general comments)
- `thread_id: str | None = None` — optional, populated when available from GraphQL
- `node_id: str | None = None` — included so Phase 5 can resolve threads without re-fetching
- No enrichment fields (classification, grouping) — that's Phase 3's concern

### Aggressiveness defaults & naming
- Three levels (not four): `critical`, `standard`, `thorough` — "exemplary" dropped
- `AggressivenessLevel` is an ordered `IntEnum`: critical=1, standard=2, thorough=3 — enables threshold comparisons (`if level >= AggressivenessLevel.STANDARD`)
- Default aggressiveness for new profiles: `standard`

### Claude's Discretion
- Exact field descriptions and docstrings
- Validator logic for PRAutoFixConfig defaults (poll_interval bounds, max_iterations bounds)
- Database migration details for the new JSONB column
- Whether to add a `pr_number` field to PRReviewComment or keep it external context

</decisions>

<specifics>
## Specific Ideas

- YAML config is fully deprecated — all config is database-driven via ProfileRepository and SettingsRepository
- Profile model is frozen with `ConfigDict(frozen=True)` — PRAutoFixConfig should follow the same pattern since it's embedded in Profile

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Profile` model (`amelia/core/types.py:146-186`): Frozen Pydantic model with optional nested configs — PRAutoFixConfig follows this exact pattern
- `ProfileRepository` (`amelia/server/database/profile_repository.py`): Full CRUD with JSONB serialization — will need extension for pr_autofix column
- `ServerConfig` (`amelia/server/config.py`): BaseSettings pattern — NOT used for PRAutoFixConfig (that's BaseModel)
- `Issue` model (`amelia/core/types.py`): Existing data model for tracker data — PRSummary follows similar purpose

### Established Patterns
- All core Pydantic models in `amelia/core/types.py` — no separate model files
- Frozen models for immutable data objects
- JSONB columns for nested config in profiles table
- `TrackerType` StrEnum for type discrimination — AggressivenessLevel follows similar pattern but as IntEnum

### Integration Points
- `Profile` class needs new `pr_autofix` field
- `ProfileRepository` needs migration + serialization for new column
- `ProfileCreate`/`ProfileUpdate`/`ProfileResponse` in `amelia/server/routes/settings.py` need pr_autofix field
- Database migration script needed (new JSONB column on profiles table)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-data-models-configuration*
*Context gathered: 2026-03-13*
