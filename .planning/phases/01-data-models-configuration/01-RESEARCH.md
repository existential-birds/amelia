# Phase 1: Data Models & Configuration - Research

**Researched:** 2026-03-13
**Domain:** Pydantic data models, configuration patterns, database migration
**Confidence:** HIGH

## Summary

Phase 1 is a pure data-definition phase: creating Pydantic models for PR auto-fix data structures and integrating configuration into the existing Profile system. The codebase has well-established patterns -- frozen Pydantic models in `amelia/core/types.py`, JSONB columns for nested config, migration files in `amelia/server/database/migrations/`. This phase follows those patterns exactly.

The key technical decisions are already locked via CONTEXT.md: three aggressiveness levels (not four), IntEnum for ordering, models in `types.py`, frozen config, `pr_autofix` as optional field on Profile. The codebase uses Pydantic v2.12.5 on Python 3.13 with `ConfigDict(frozen=True)` throughout.

**Primary recommendation:** Follow the existing `SandboxConfig` precedent exactly -- frozen BaseModel nested in Profile, JSONB column via migration, repository deserialization in `_row_to_profile`.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- All models go in `amelia/core/types.py` alongside existing `Profile`, `Settings`, `Issue`, etc.
- `PRSummary` and `PRReviewComment` are frozen (immutable) like `Profile` -- supports stateless reducer pattern in LangGraph pipelines
- `PRAutoFixConfig` also in `types.py` -- it's a Pydantic BaseModel nested in Profile, not a BaseSettings
- Field naming mirrors GitHub API naming (e.g., `number`, `head_branch`, `diff_hunk`) -- clear mapping from API response to model
- `PRAutoFixConfig` attaches as an optional field on `Profile`: `pr_autofix: PRAutoFixConfig | None = None`
- `None` means PR auto-fix is disabled for that profile -- polling service skips it entirely (clean opt-in)
- Stored as JSONB column on the `profiles` database table, matching how `agents` and `sandbox` are stored
- Per-PR overrides are ephemeral via CLI flags and API params -- not stored in database. Profile config is the baseline
- `PRReviewComment` mirrors GitHub API fields: `id`, `body`, `path`, `line`, `diff_hunk`, `author`, `created_at`, `in_reply_to_id`
- Handles both inline and general review comments -- `path`/`line`/`diff_hunk` are optional (`None` for general comments)
- `thread_id: str | None = None` -- optional, populated when available from GraphQL
- `node_id: str | None = None` -- included so Phase 5 can resolve threads without re-fetching
- Three levels (not four): `critical`, `standard`, `thorough` -- "exemplary" dropped
- `AggressivenessLevel` is an ordered `IntEnum`: critical=1, standard=2, thorough=3 -- enables threshold comparisons
- Default aggressiveness for new profiles: `standard`
- YAML config is fully deprecated -- all config is database-driven
- Profile model is frozen with `ConfigDict(frozen=True)` -- PRAutoFixConfig should follow the same pattern

### Claude's Discretion
- Exact field descriptions and docstrings
- Validator logic for PRAutoFixConfig defaults (poll_interval bounds, max_iterations bounds)
- Database migration details for the new JSONB column
- Whether to add a `pr_number` field to PRReviewComment or keep it external context

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DATA-01 | `PRSummary` Pydantic model (number, title, head_branch, author, updated_at) | Follows existing frozen model pattern in `types.py`; `Issue` model is closest precedent |
| DATA-02 | `PRReviewComment` Pydantic model (id, thread_id, pr_number, path, line, body, author, created_at, in_reply_to_id, diff_hunk) | Frozen model with optional fields for inline vs general comments; CONTEXT specifies exact fields |
| DATA-03 | `PRAutoFixConfig` Pydantic model (enabled, poll_interval, auto_resolve, max_iterations, commit_prefix, aggressiveness) | Follows `SandboxConfig` pattern -- frozen BaseModel with Field validators and defaults |
| DATA-04 | `AggressivenessLevel` enum (critical, standard, thorough) | IntEnum (not StrEnum) per CONTEXT; only 3 levels, "exemplary" dropped |
| CONF-01 | `PRAutoFixConfig` with all config fields | Same as DATA-03; validator bounds for poll_interval and max_iterations at Claude's discretion |
| CONF-02 | Fix aggressiveness configurable per-profile (default: standard) | `pr_autofix: PRAutoFixConfig \| None = None` on Profile; default aggressiveness is `standard` |
| CONF-03 | Fix aggressiveness overridable per-PR when triggering manually | Per-PR overrides are ephemeral (CLI/API params), not stored -- models just need to support the field type |
| CONF-04 | PR polling can be enabled/disabled globally via server settings | Requires new field on `ServerSettings` / `server_settings` table; separate from Profile-level config |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | Data model definitions | Already in use throughout codebase |
| pydantic-settings | 2.6.0 | Server settings (NOT for PRAutoFixConfig) | Existing pattern for ServerConfig |
| asyncpg | 0.30.0 | Database access for migrations | Existing database layer |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.3.4+ | Test framework | All unit tests for models |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| IntEnum | StrEnum | IntEnum enables `>=` comparisons for aggressiveness thresholds -- correct choice per CONTEXT |
| Separate model files | Single types.py | Codebase convention is single file -- follow it |

## Architecture Patterns

### Recommended Project Structure
```
amelia/core/types.py           # All new models added here (existing file)
amelia/server/database/
  migrations/
    008_add_pr_autofix_to_profiles.sql   # New migration
  profile_repository.py        # Update _row_to_profile deserialization
amelia/server/routes/settings.py  # Update ProfileCreate/Update/Response
tests/unit/core/
  test_pr_autofix_models.py    # New test file for all PR auto-fix models
```

### Pattern 1: Frozen Pydantic Model with Defaults
**What:** All data models use `ConfigDict(frozen=True)` with `Field()` for defaults and validation
**When to use:** Every model in this phase
**Example:**
```python
# Source: existing pattern in amelia/core/types.py
class PRAutoFixConfig(BaseModel):
    """Configuration for PR auto-fix behavior."""
    model_config = ConfigDict(frozen=True)

    aggressiveness: AggressivenessLevel = AggressivenessLevel.STANDARD
    poll_interval: int = Field(default=60, ge=10, le=3600, description="Polling interval in seconds")
    auto_resolve: bool = Field(default=True, description="Auto-resolve threads after fix")
    max_iterations: int = Field(default=3, ge=1, le=10, description="Max fix attempts per thread")
    commit_prefix: str = Field(default="fix(review):", description="Commit message prefix")
```

### Pattern 2: IntEnum for Ordered Levels
**What:** Use `IntEnum` instead of `StrEnum` when ordering matters
**When to use:** `AggressivenessLevel` -- enables `if level >= AggressivenessLevel.STANDARD`
**Example:**
```python
from enum import IntEnum

class AggressivenessLevel(IntEnum):
    """Aggressiveness level for PR auto-fix comment classification.

    Ordered so threshold comparisons work: if level >= STANDARD.
    """
    CRITICAL = 1
    STANDARD = 2
    THOROUGH = 3
```

### Pattern 3: Optional Nested Config on Profile
**What:** Profile has optional JSONB-backed config fields; `None` means feature disabled
**When to use:** `pr_autofix` field on Profile
**Example:**
```python
# Source: existing SandboxConfig pattern on Profile
class Profile(BaseModel):
    model_config = ConfigDict(frozen=True)
    # ... existing fields ...
    pr_autofix: PRAutoFixConfig | None = None
```

### Pattern 4: JSONB Migration
**What:** Single ALTER TABLE adding JSONB column with default
**When to use:** Adding pr_autofix column to profiles table
**Example:**
```sql
-- Source: existing pattern from 002_add_sandbox_to_profiles.sql
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS pr_autofix JSONB DEFAULT NULL;
```

### Pattern 5: Repository Deserialization
**What:** `_row_to_profile` in ProfileRepository deserializes JSONB to Pydantic model
**When to use:** Reading pr_autofix from database
**Example:**
```python
# Source: existing sandbox deserialization in profile_repository.py
pr_autofix_data = row.get("pr_autofix")
pr_autofix = PRAutoFixConfig(**pr_autofix_data) if pr_autofix_data else None
```

### Anti-Patterns to Avoid
- **Mutable data models:** Never use models without `frozen=True` for data objects in this codebase
- **BaseSettings for PRAutoFixConfig:** This is NOT server config -- it's per-profile config stored in DB
- **Separate model files:** All core models go in `types.py` per codebase convention
- **Dict instead of Pydantic:** CLAUDE.md explicitly says "Pydantic models for all data structures -- not ad-hoc dicts"
- **`exemplary` level:** CONTEXT explicitly dropped it -- only 3 levels

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Field validation bounds | Custom if-checks in __init__ | Pydantic `Field(ge=, le=)` | Pydantic handles validation errors with clear messages |
| Immutability | Manual __setattr__ override | `ConfigDict(frozen=True)` | Standard Pydantic v2 pattern already used everywhere |
| JSON serialization | Custom to_dict/from_dict | `.model_dump()` / `.model_validate()` | Pydantic handles all edge cases including nested models |
| Enum comparison logic | Manual if/elif chains | IntEnum with `>=` operator | Python IntEnum supports comparison operators natively |

## Common Pitfalls

### Pitfall 1: IntEnum Serialization in Pydantic
**What goes wrong:** IntEnum values serialize as integers (1, 2, 3) instead of names in JSON
**Why it happens:** Pydantic v2 serializes IntEnum by value by default
**How to avoid:** Use `model_config = ConfigDict(use_enum_values=False)` on the containing model, OR accept integer serialization since the DB stores JSONB (Pydantic will deserialize correctly either way). Alternatively, add a `@field_serializer` to output the name string.
**Warning signs:** API responses showing `1` instead of `"critical"`, config files hard to read
**Recommendation:** Test serialization explicitly. If API readability matters, add a field serializer. For DB storage, integer values are fine since Pydantic validates on load.

### Pitfall 2: Forgetting to Update ProfileRepository
**What goes wrong:** New field exists on Profile model but `_row_to_profile` and `create_profile`/`update_profile` don't handle it
**Why it happens:** Profile model and repository are separate files
**How to avoid:** Update `_row_to_profile` deserialization, `create_profile` INSERT, and `valid_fields` in `update_profile`
**Warning signs:** pr_autofix always `None` even when set in database

### Pitfall 3: Forgetting API Route Models
**What goes wrong:** Profile can be saved/loaded but API can't create/update pr_autofix config
**Why it happens:** `ProfileCreate`, `ProfileUpdate`, `ProfileResponse` in settings.py are separate from the core Profile model
**How to avoid:** Add `pr_autofix` field to all three API models in `settings.py`

### Pitfall 4: Migration Numbering
**What goes wrong:** Migration file conflicts with another branch
**Why it happens:** Sequential numbering assumes linear development
**How to avoid:** Check existing migrations before naming. Next migration is `008_*.sql`
**Warning signs:** Migrator skipping or failing on duplicate sequence numbers

### Pitfall 5: CONF-04 vs Profile-Level Config
**What goes wrong:** Confusing profile-level `pr_autofix` (per-profile) with global polling toggle (server-level)
**Why it happens:** Both relate to "enabling" PR auto-fix but at different scopes
**How to avoid:** CONF-04 is a server_settings field (global toggle). Profile `pr_autofix: None` means disabled for that profile. They are independent.

### Pitfall 6: Frozen Model and JSONB Default
**What goes wrong:** `PRAutoFixConfig` with `Field(default_factory=...)` inside frozen Profile causes issues
**Why it happens:** Profile is frozen -- setting pr_autofix requires passing it at construction time
**How to avoid:** Default is `None`, not a PRAutoFixConfig instance. Constructed explicitly when needed.

## Code Examples

### PRSummary Model
```python
# Follows Issue model pattern
class PRSummary(BaseModel):
    """Summary of a GitHub pull request."""
    model_config = ConfigDict(frozen=True)

    number: int = Field(description="PR number")
    title: str = Field(description="PR title")
    head_branch: str = Field(description="Head branch name")
    author: str = Field(description="PR author login")
    updated_at: datetime = Field(description="Last update timestamp")
```

### PRReviewComment Model
```python
class PRReviewComment(BaseModel):
    """A review comment on a GitHub pull request.

    Handles both inline (file-specific) and general review comments.
    For general comments, path/line/diff_hunk are None.
    """
    model_config = ConfigDict(frozen=True)

    id: int = Field(description="GitHub comment ID")
    body: str = Field(description="Comment body text")
    author: str = Field(description="Comment author login")
    created_at: datetime = Field(description="Comment creation timestamp")
    path: str | None = Field(default=None, description="File path for inline comments")
    line: int | None = Field(default=None, description="Line number for inline comments")
    diff_hunk: str | None = Field(default=None, description="Diff context for inline comments")
    in_reply_to_id: int | None = Field(default=None, description="Parent comment ID for threaded replies")
    thread_id: str | None = Field(default=None, description="Review thread ID from GraphQL")
    node_id: str | None = Field(default=None, description="GraphQL node ID for thread resolution")
    # pr_number: discretionary -- recommend including for self-contained context
    pr_number: int | None = Field(default=None, description="PR number this comment belongs to")
```

### AggressivenessLevel IntEnum
```python
from enum import IntEnum

class AggressivenessLevel(IntEnum):
    """Aggressiveness level for PR auto-fix classification.

    Ordered for threshold comparisons: `if level >= AggressivenessLevel.STANDARD`.
    - CRITICAL (1): Only fix clear bugs, security issues, build failures
    - STANDARD (2): Fix style issues, common patterns, and critical items
    - THOROUGH (3): Fix all actionable comments including suggestions and nitpicks
    """
    CRITICAL = 1
    STANDARD = 2
    THOROUGH = 3
```

### Server Settings Extension for CONF-04
```python
# In server_settings table migration:
# ALTER TABLE server_settings ADD COLUMN IF NOT EXISTS pr_polling_enabled BOOLEAN NOT NULL DEFAULT FALSE;

# In SettingsRepository / ServerConfig -- add pr_polling_enabled field
```

### Profile Repository Update
```python
# In _row_to_profile:
pr_autofix_data = row.get("pr_autofix")
pr_autofix = PRAutoFixConfig(**pr_autofix_data) if pr_autofix_data else None

return Profile(
    # ... existing fields ...
    pr_autofix=pr_autofix,
)

# In create_profile -- serialize pr_autofix:
pr_autofix_data = profile.pr_autofix.model_dump() if profile.pr_autofix else None

# In update_profile -- add to valid_fields:
valid_fields = {
    "tracker", "repo_root", "plan_output_dir",
    "plan_path_pattern", "agents", "sandbox", "pr_autofix",
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 validators | Pydantic v2 `model_validator`, `field_validator` | Pydantic v2 (2023) | Use `mode="after"` for model validators |
| `class Config:` | `model_config = ConfigDict(...)` | Pydantic v2 (2023) | Codebase already uses v2 style |
| `StrEnum` for all enums | `IntEnum` when ordering needed | N/A | `AggressivenessLevel` uses IntEnum per CONTEXT decision |
| YAML config files | Database-driven config | Per CONTEXT decision | No YAML -- everything is DB/JSONB |

## Open Questions

1. **pr_number on PRReviewComment**
   - What we know: CONTEXT lists it as Claude's discretion
   - Recommendation: Include it as `pr_number: int | None = None`. Makes the model self-contained -- downstream consumers (classification, pipeline) don't need to pass PR context separately. Optional because it can be set after construction.

2. **IntEnum serialization in API responses**
   - What we know: Pydantic v2 serializes IntEnum as integer by default
   - What's unclear: Whether API consumers (dashboard) expect string names or integer values
   - Recommendation: Add a custom serializer to output string names in JSON while keeping integer comparison behavior. Test this explicitly.

3. **CONF-04 scope**
   - What we know: "PR polling can be enabled/disabled globally via server settings"
   - What's unclear: Whether this belongs in Phase 1 (data models) or Phase 8 (polling service)
   - Recommendation: Add the `pr_polling_enabled` field to server settings in this phase since it's a data model concern. The polling service (Phase 8) will read this field.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4+ with pytest-asyncio |
| Config file | `pyproject.toml` (existing) |
| Quick run command | `uv run pytest tests/unit/core/test_pr_autofix_models.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | PRSummary fields and immutability | unit | `uv run pytest tests/unit/core/test_pr_autofix_models.py::TestPRSummary -x` | No -- Wave 0 |
| DATA-02 | PRReviewComment fields, optional inline fields, immutability | unit | `uv run pytest tests/unit/core/test_pr_autofix_models.py::TestPRReviewComment -x` | No -- Wave 0 |
| DATA-03 | PRAutoFixConfig defaults, validation bounds, immutability | unit | `uv run pytest tests/unit/core/test_pr_autofix_models.py::TestPRAutoFixConfig -x` | No -- Wave 0 |
| DATA-04 | AggressivenessLevel enum values, ordering, comparison | unit | `uv run pytest tests/unit/core/test_pr_autofix_models.py::TestAggressivenessLevel -x` | No -- Wave 0 |
| CONF-01 | PRAutoFixConfig has all required fields with correct defaults | unit | `uv run pytest tests/unit/core/test_pr_autofix_models.py::TestPRAutoFixConfig -x` | No -- Wave 0 |
| CONF-02 | Profile with pr_autofix field, None means disabled | unit | `uv run pytest tests/unit/core/test_pr_autofix_models.py::TestProfilePRAutoFix -x` | No -- Wave 0 |
| CONF-03 | PRAutoFixConfig fields can be overridden (model_copy) | unit | `uv run pytest tests/unit/core/test_pr_autofix_models.py::TestPRAutoFixOverride -x` | No -- Wave 0 |
| CONF-04 | Server settings pr_polling_enabled field | unit | `uv run pytest tests/unit/core/test_pr_autofix_models.py::TestServerSettingsPRPolling -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/core/test_pr_autofix_models.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/core/test_pr_autofix_models.py` -- all PR auto-fix model tests (DATA-01 through CONF-04)
- No framework install needed -- pytest already configured
- No shared fixtures needed -- models are self-contained with no async or DB dependencies for unit tests

## Sources

### Primary (HIGH confidence)
- `amelia/core/types.py` -- existing model patterns (frozen, ConfigDict, Field validators)
- `amelia/server/database/profile_repository.py` -- JSONB deserialization pattern
- `amelia/server/database/migrations/002_add_sandbox_to_profiles.sql` -- migration pattern
- `amelia/server/routes/settings.py` -- API model pattern (ProfileCreate/Update/Response)
- `tests/unit/core/test_types.py` -- test patterns for Pydantic models
- Pydantic v2.12.5 installed (verified via `uv pip show pydantic`)

### Secondary (MEDIUM confidence)
- Pydantic v2 IntEnum serialization behavior -- verified against known Pydantic v2 behavior

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, versions verified
- Architecture: HIGH -- follows exact existing patterns in codebase
- Pitfalls: HIGH -- derived from examining actual codebase patterns and integration points

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable domain, no fast-moving dependencies)
