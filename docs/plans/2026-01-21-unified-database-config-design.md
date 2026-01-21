# Unified Database Configuration Design

**Issue:** #307
**Date:** 2026-01-21
**Status:** Draft

## Summary

Migrate Amelia from split configuration systems (YAML files + environment variables) to a unified database-backed configuration. This eliminates the `settings.amelia.yaml` file entirely and reduces `ServerConfig` to minimal bootstrap settings.

## Problem

Currently Amelia has two separate configuration systems:

| Config System | Source | Purpose |
|---------------|--------|---------|
| `ServerConfig` | Env vars (`AMELIA_*`) + `.env` file | Server-level settings |
| `settings.amelia.yaml` | YAML file per worktree | Profile-level settings |

This split has caused bugs (e.g., brainstorming agent using wrong `working_dir` because it read from `ServerConfig` instead of the active profile) and creates confusion about where settings live.

## Solution

1. Store all configuration in SQLite database
2. Keep only bootstrap env vars: `AMELIA_HOST`, `AMELIA_PORT`, `AMELIA_DATABASE_PATH`
3. Add settings UI to dashboard for managing profiles and server config
4. Add `amelia config` CLI subcommand for terminal-based management
5. Remove `settings.amelia.yaml` entirely (no backwards compatibility)

## Design Decisions

- **Global profiles only** - No per-worktree profile overrides. Profiles live in central database.
- **Single active profile** - One profile marked active at a time, used as default for new workflows.
- **`working_dir` in Profile** - Each profile has a default `working_dir` that pre-fills the worktree picker, but can be overridden per-workflow.
- **Interactive first-run** - First run prompts user to create initial profile.

---

## Database Schema

### `server_settings` table (singleton)

```sql
CREATE TABLE server_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    log_retention_days INTEGER NOT NULL DEFAULT 30,
    log_retention_max_events INTEGER NOT NULL DEFAULT 100000,
    trace_retention_days INTEGER NOT NULL DEFAULT 7,
    checkpoint_retention_days INTEGER NOT NULL DEFAULT 0,
    checkpoint_path TEXT NOT NULL DEFAULT '~/.amelia/checkpoints.db',
    websocket_idle_timeout_seconds REAL NOT NULL DEFAULT 300.0,
    workflow_start_timeout_seconds REAL NOT NULL DEFAULT 60.0,
    max_concurrent INTEGER NOT NULL DEFAULT 5,
    stream_tool_results BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### `profiles` table

```sql
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    driver TEXT NOT NULL,
    model TEXT NOT NULL,
    validator_model TEXT NOT NULL,
    tracker TEXT NOT NULL DEFAULT 'none',
    working_dir TEXT NOT NULL,
    plan_output_dir TEXT NOT NULL DEFAULT 'docs/plans',
    plan_path_pattern TEXT NOT NULL DEFAULT 'docs/plans/{date}-{issue_key}.md',
    max_review_iterations INTEGER NOT NULL DEFAULT 3,
    max_task_review_iterations INTEGER NOT NULL DEFAULT 5,
    auto_approve_reviews BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Ensure only one active profile
CREATE TRIGGER ensure_single_active_profile
AFTER UPDATE OF is_active ON profiles
WHEN NEW.is_active = TRUE
BEGIN
    UPDATE profiles SET is_active = FALSE WHERE id != NEW.id;
END;
```

---

## Environment Variables (Bootstrap Only)

| Variable | Default | Purpose |
|----------|---------|---------|
| `AMELIA_HOST` | `127.0.0.1` | Server bind host |
| `AMELIA_PORT` | `8420` | Server bind port |
| `AMELIA_DATABASE_PATH` | `~/.amelia/amelia.db` | Path to SQLite database |

All other settings previously in env vars move to `server_settings` table.

---

## Backend Changes

### Files to Delete

- `amelia/config.py` - YAML loading logic
- `settings.amelia.yaml`
- `settings.amelia.yaml.example`

### Modified Files

**`amelia/server/config.py`** - Strip to bootstrap only:

```python
class ServerConfig(BaseSettings):
    """Minimal bootstrap config - only settings needed before DB is available."""

    model_config = SettingsConfigDict(env_prefix="AMELIA_")

    host: str = "127.0.0.1"
    port: int = 8420
    database_path: Path = Path.home() / ".amelia" / "amelia.db"
```

### New Files

**`amelia/server/database/settings_repository.py`:**

```python
class SettingsRepository:
    async def get_server_settings(self) -> ServerSettings
    async def update_server_settings(self, updates: dict) -> ServerSettings
    async def ensure_defaults(self) -> None  # Creates singleton row on first run
```

**`amelia/server/database/profile_repository.py`:**

```python
class ProfileRepository:
    async def list_profiles(self) -> list[Profile]
    async def get_profile(self, id: str) -> Profile | None
    async def get_active_profile(self) -> Profile | None
    async def create_profile(self, profile: Profile) -> Profile
    async def update_profile(self, id: str, updates: dict) -> Profile
    async def delete_profile(self, id: str) -> bool
    async def set_active(self, id: str) -> None
```

**`amelia/server/orchestrator/service.py`** changes:
- Replace `_load_settings_for_worktree()` with `ProfileRepository.get_profile()`
- Remove all YAML file loading logic

---

## API Routes

New routes in `amelia/server/routes/settings.py`:

```
GET    /api/settings              → Get server settings
PUT    /api/settings              → Update server settings

GET    /api/profiles              → List all profiles
POST   /api/profiles              → Create new profile
GET    /api/profiles/{id}         → Get profile by ID
PUT    /api/profiles/{id}         → Update profile
DELETE /api/profiles/{id}         → Delete profile
POST   /api/profiles/{id}/activate → Set as active profile
```

---

## Dashboard UI

### Route Structure

```
/settings           → Redirect to /settings/profiles
/settings/profiles  → Profile management
/settings/server    → Server configuration
```

Tab navigation between the two settings pages.

### Profiles Page (`/settings/profiles`)

**Layout:**
- Header with "Create Profile" button
- Filter tabs: All | API | CLI
- Search input
- Active profile featured at top with distinct visual treatment (border-primary)
- Other profiles in card grid below

**Profile Card:**
- Name, driver, model, working_dir displayed
- Driver-specific accent color (cli:claude = gold, api:openrouter = blue)
- Actions: Edit, Set Active, three-dot menu (Delete, Clone)

**Profile Create/Edit Modal:**
- Basic Settings section: name, driver (dropdown), model, working_dir (reuse `WorktreePathField`)
- Collapsible Tracker Settings section
- Collapsible Advanced section (validator_model, plan settings, review iterations)
- Driver-conditional fields (API key only for api:openrouter)

### Server Settings Page (`/settings/server`)

**Layout (direct editing, no modal):**
- Grouped sections with headers and descriptions:
  - Retention Policies (log, trace, checkpoint)
  - Execution Limits (max_concurrent)
  - Debugging (stream_tool_results)
- Select dropdowns for numeric fields (predefined options: 7, 14, 30, 60, 90 days)
- Toggle switches for booleans
- Sticky footer with unsaved changes indicator, Reset and Save buttons

### State Management

Use React Router loaders/actions (matches existing patterns):

```typescript
// loaders/settings.ts
export async function settingsLoader() {
  const [config, profiles] = await Promise.all([
    api.getServerConfig(),
    api.getProfiles(),
  ]);
  return { config, profiles };
}
```

No new Zustand stores - Zustand is for real-time WebSocket state, not CRUD.

### File Structure

```
dashboard/src/
├── pages/
│   ├── SettingsProfilesPage.tsx
│   └── SettingsServerPage.tsx
├── components/
│   └── settings/
│       ├── ProfileCard.tsx
│       ├── ProfileEditModal.tsx
│       └── ServerSettingsForm.tsx
├── loaders/
│   └── settings.ts
└── actions/
    └── settings.ts
```

---

## CLI Changes

### New `amelia config` Subcommand

```bash
# Profile management
amelia config profile list
amelia config profile show <name>
amelia config profile create                  # Interactive
amelia config profile create --name dev --driver cli:claude --model opus --working-dir /path
amelia config profile edit <name>             # Interactive
amelia config profile delete <name>
amelia config profile activate <name>

# Server settings
amelia config server show
amelia config server set <key> <value>
amelia config server reset
```

### First-Run Experience

When database has no profiles and user runs `amelia dev` or `amelia start`:

```
No profiles configured. Let's create your first profile.

Profile name [dev]:
Driver (cli:claude, api:openrouter) [cli:claude]:
Model [opus]:
Working directory [/current/dir]:

✓ Profile 'dev' created and set as active.
```

### Existing Command Changes

- `amelia start` / `amelia review` - `--profile` flag reads from DB
- Remove any `--config` or settings file path flags

---

## Documentation Updates

### Files to Update

**CLAUDE.md:**
- Remove "Configuration" section referencing YAML
- Update env var table to bootstrap-only vars
- Add `amelia config` command reference
- Update "Server Configuration" section

**README.md:**
- Remove YAML setup instructions
- Update quickstart to mention first-run interactive setup

**VitePress docs (`docs/site/`):**
- Remove YAML configuration guides
- Add new "Configuration" page covering:
  - First-run setup
  - Managing profiles via CLI and dashboard
  - Server settings reference
  - Environment variables (bootstrap only)

---

## Test Updates

- Delete tests for `load_settings()`, `Settings` class
- Update integration tests that mock YAML loading to use DB fixtures
- Add unit tests for `ProfileRepository`, `SettingsRepository`
- Add API route tests for `/api/settings` and `/api/profiles`
- Add CLI tests for `amelia config` subcommand

---

## Implementation Phases

### Phase 1: Database Foundation
1. Add `server_settings` and `profiles` tables to schema
2. Create `SettingsRepository` and `ProfileRepository`
3. Write unit tests for repositories

### Phase 2: Backend Migration
4. Strip `ServerConfig` to bootstrap-only
5. Create new settings/profile API routes
6. Update orchestrator to use `ProfileRepository`
7. Delete `amelia/config.py` and YAML loading

### Phase 3: CLI
8. Add `amelia config` subcommand with profile/server management
9. Implement first-run interactive setup
10. Update existing commands to use DB

### Phase 4: Dashboard
11. Create `/settings/profiles` page with card grid
12. Create `/settings/server` page with form
13. Add profile create/edit modal
14. Wire up to API routes

### Phase 5: Cleanup
15. Delete YAML files
16. Update CLAUDE.md, README.md
17. Update VitePress docs
18. Clean up tests

---

## Migration Path

None. This is a clean break with no backwards compatibility. Users will create new profiles on first run after upgrading.
