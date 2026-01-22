# Unified Database Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate Amelia from split YAML+env configuration to a unified SQLite database-backed configuration.

**Architecture:** Store all settings (server config + profiles) in SQLite. `ServerConfig` becomes bootstrap-only (host, port, database_path). Add repository classes, API routes, CLI commands, and dashboard UI for managing configuration.

**Tech Stack:** Python (Pydantic, aiosqlite, Typer), TypeScript (React, React Router, Tailwind, shadcn/ui)

---

## Phase 1: Database Foundation

### Task 1.1: Add Database Schema for Settings

**Files:**
- Modify: `amelia/server/database/connection.py:255-489` (ensure_schema method)
- Test: `tests/unit/server/test_database_schema.py` (new)

**Step 1: Write the failing test**

```python
# tests/unit/server/test_database_schema.py
"""Tests for database schema including server_settings and profiles tables."""
import pytest
from pathlib import Path
import tempfile

from amelia.server.database.connection import Database


@pytest.fixture
async def db():
    """Create an in-memory database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")
        await db.connect()
        await db.ensure_schema()
        yield db
        await db.close()


class TestServerSettingsSchema:
    """Tests for server_settings table."""

    async def test_server_settings_table_exists(self, db: Database):
        """Verify server_settings table was created."""
        row = await db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='server_settings'"
        )
        assert row is not None

    async def test_server_settings_singleton_constraint(self, db: Database):
        """Verify only one row can exist in server_settings (id=1)."""
        # First insert should succeed
        await db.execute(
            """INSERT INTO server_settings (id, log_retention_days) VALUES (1, 30)"""
        )

        # Second insert with id=2 should fail
        with pytest.raises(Exception):
            await db.execute(
                """INSERT INTO server_settings (id, log_retention_days) VALUES (2, 60)"""
            )


class TestProfilesSchema:
    """Tests for profiles table."""

    async def test_profiles_table_exists(self, db: Database):
        """Verify profiles table was created."""
        row = await db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='profiles'"
        )
        assert row is not None

    async def test_profile_insert(self, db: Database):
        """Verify profile can be inserted."""
        await db.execute(
            """INSERT INTO profiles (id, driver, model, validator_model, tracker, working_dir, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("dev", "cli:claude", "opus", "haiku", "noop", "/path/to/repo", True),
        )
        row = await db.fetch_one("SELECT * FROM profiles WHERE id = ?", ("dev",))
        assert row is not None
        assert row["driver"] == "cli:claude"
        assert row["is_active"] == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_database_schema.py -v`
Expected: FAIL with "no such table: server_settings"

**Step 3: Add server_settings and profiles tables to schema**

In `amelia/server/database/connection.py`, add to `ensure_schema()` method (after brainstorm tables):

```python
        # Server settings singleton table
        await self.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                log_retention_days INTEGER NOT NULL DEFAULT 30,
                log_retention_max_events INTEGER NOT NULL DEFAULT 100000,
                trace_retention_days INTEGER NOT NULL DEFAULT 7,
                checkpoint_retention_days INTEGER NOT NULL DEFAULT 0,
                checkpoint_path TEXT NOT NULL DEFAULT '~/.amelia/checkpoints.db',
                websocket_idle_timeout_seconds REAL NOT NULL DEFAULT 300.0,
                workflow_start_timeout_seconds REAL NOT NULL DEFAULT 60.0,
                max_concurrent INTEGER NOT NULL DEFAULT 5,
                stream_tool_results INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Profiles table
        await self.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                driver TEXT NOT NULL,
                model TEXT NOT NULL,
                validator_model TEXT NOT NULL,
                tracker TEXT NOT NULL DEFAULT 'noop',
                working_dir TEXT NOT NULL,
                plan_output_dir TEXT NOT NULL DEFAULT 'docs/plans',
                plan_path_pattern TEXT NOT NULL DEFAULT 'docs/plans/{date}-{issue_key}.md',
                max_review_iterations INTEGER NOT NULL DEFAULT 3,
                max_task_review_iterations INTEGER NOT NULL DEFAULT 5,
                auto_approve_reviews INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Trigger to ensure only one active profile
        await self.execute("""
            CREATE TRIGGER IF NOT EXISTS ensure_single_active_profile
            AFTER UPDATE OF is_active ON profiles
            WHEN NEW.is_active = 1
            BEGIN
                UPDATE profiles SET is_active = 0 WHERE id != NEW.id;
            END
        """)

        # Index for active profile lookup
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_profiles_active ON profiles(is_active)"
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_database_schema.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/connection.py tests/unit/server/test_database_schema.py
git commit -m "$(cat <<'EOF'
feat(db): add server_settings and profiles tables

Adds database schema for unified configuration:
- server_settings: singleton table for server-level config
- profiles: table for LLM/workflow profiles with single-active trigger

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.2: Create SettingsRepository

**Files:**
- Create: `amelia/server/database/settings_repository.py`
- Test: `tests/unit/server/test_settings_repository.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_settings_repository.py
"""Tests for SettingsRepository."""
import pytest
from pathlib import Path
import tempfile

from amelia.server.database.connection import Database
from amelia.server.database.settings_repository import SettingsRepository, ServerSettings


@pytest.fixture
async def db():
    """Create an in-memory database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")
        await db.connect()
        await db.ensure_schema()
        yield db
        await db.close()


@pytest.fixture
def repo(db: Database):
    """Create a SettingsRepository instance."""
    return SettingsRepository(db)


class TestSettingsRepository:
    """Tests for SettingsRepository."""

    async def test_ensure_defaults_creates_singleton(self, repo: SettingsRepository, db: Database):
        """Verify ensure_defaults creates the singleton row."""
        await repo.ensure_defaults()
        row = await db.fetch_one("SELECT * FROM server_settings WHERE id = 1")
        assert row is not None
        assert row["log_retention_days"] == 30

    async def test_ensure_defaults_idempotent(self, repo: SettingsRepository):
        """Verify ensure_defaults can be called multiple times."""
        await repo.ensure_defaults()
        await repo.ensure_defaults()  # Should not raise
        settings = await repo.get_server_settings()
        assert settings.log_retention_days == 30

    async def test_get_server_settings(self, repo: SettingsRepository):
        """Verify get_server_settings returns defaults."""
        await repo.ensure_defaults()
        settings = await repo.get_server_settings()
        assert isinstance(settings, ServerSettings)
        assert settings.log_retention_days == 30
        assert settings.max_concurrent == 5
        assert settings.stream_tool_results is False

    async def test_update_server_settings(self, repo: SettingsRepository):
        """Verify update_server_settings modifies values."""
        await repo.ensure_defaults()
        updated = await repo.update_server_settings(
            {"log_retention_days": 60, "max_concurrent": 10}
        )
        assert updated.log_retention_days == 60
        assert updated.max_concurrent == 10

        # Verify persistence
        fetched = await repo.get_server_settings()
        assert fetched.log_retention_days == 60
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_settings_repository.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement SettingsRepository**

```python
# amelia/server/database/settings_repository.py
"""Repository for server settings management."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from amelia.server.database.connection import Database


@dataclass
class ServerSettings:
    """Server settings data class."""

    log_retention_days: int
    log_retention_max_events: int
    trace_retention_days: int
    checkpoint_retention_days: int
    checkpoint_path: str
    websocket_idle_timeout_seconds: float
    workflow_start_timeout_seconds: float
    max_concurrent: int
    stream_tool_results: bool
    created_at: datetime
    updated_at: datetime


class SettingsRepository:
    """Repository for server settings CRUD operations."""

    def __init__(self, db: Database):
        """Initialize repository with database connection.

        Args:
            db: Database connection instance.
        """
        self._db = db

    async def ensure_defaults(self) -> None:
        """Create server_settings singleton row if it doesn't exist.

        Idempotent - safe to call multiple times.
        """
        await self._db.execute(
            """INSERT OR IGNORE INTO server_settings (id) VALUES (1)"""
        )

    async def get_server_settings(self) -> ServerSettings:
        """Get current server settings.

        Returns:
            ServerSettings with current values.

        Raises:
            ValueError: If settings not initialized (call ensure_defaults first).
        """
        row = await self._db.fetch_one(
            "SELECT * FROM server_settings WHERE id = 1"
        )
        if row is None:
            raise ValueError("Server settings not initialized. Call ensure_defaults() first.")
        return self._row_to_settings(row)

    async def update_server_settings(self, updates: dict) -> ServerSettings:
        """Update server settings.

        Args:
            updates: Dictionary of field names to new values.

        Returns:
            Updated ServerSettings.

        Raises:
            ValueError: If invalid field names provided.
        """
        valid_fields = {
            "log_retention_days",
            "log_retention_max_events",
            "trace_retention_days",
            "checkpoint_retention_days",
            "checkpoint_path",
            "websocket_idle_timeout_seconds",
            "workflow_start_timeout_seconds",
            "max_concurrent",
            "stream_tool_results",
        }
        invalid = set(updates.keys()) - valid_fields
        if invalid:
            raise ValueError(f"Invalid settings fields: {invalid}")

        if not updates:
            return await self.get_server_settings()

        # Build UPDATE statement
        set_clauses = [f"{k} = ?" for k in updates.keys()]
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values = list(updates.values())

        await self._db.execute(
            f"UPDATE server_settings SET {', '.join(set_clauses)} WHERE id = 1",
            values,
        )
        return await self.get_server_settings()

    def _row_to_settings(self, row) -> ServerSettings:
        """Convert database row to ServerSettings.

        Args:
            row: Database row from server_settings table.

        Returns:
            ServerSettings instance.
        """
        return ServerSettings(
            log_retention_days=row["log_retention_days"],
            log_retention_max_events=row["log_retention_max_events"],
            trace_retention_days=row["trace_retention_days"],
            checkpoint_retention_days=row["checkpoint_retention_days"],
            checkpoint_path=row["checkpoint_path"],
            websocket_idle_timeout_seconds=row["websocket_idle_timeout_seconds"],
            workflow_start_timeout_seconds=row["workflow_start_timeout_seconds"],
            max_concurrent=row["max_concurrent"],
            stream_tool_results=bool(row["stream_tool_results"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_settings_repository.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/settings_repository.py tests/unit/server/test_settings_repository.py
git commit -m "$(cat <<'EOF'
feat(db): add SettingsRepository for server settings

CRUD operations for server_settings singleton table:
- ensure_defaults: idempotent initialization
- get_server_settings: fetch current values
- update_server_settings: partial updates

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.3: Create ProfileRepository

**Files:**
- Create: `amelia/server/database/profile_repository.py`
- Test: `tests/unit/server/test_profile_repository.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_profile_repository.py
"""Tests for ProfileRepository."""
import pytest
from pathlib import Path
import tempfile

from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRepository, ProfileRecord


@pytest.fixture
async def db():
    """Create an in-memory database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")
        await db.connect()
        await db.ensure_schema()
        yield db
        await db.close()


@pytest.fixture
def repo(db: Database):
    """Create a ProfileRepository instance."""
    return ProfileRepository(db)


class TestProfileRepository:
    """Tests for ProfileRepository CRUD operations."""

    async def test_create_profile(self, repo: ProfileRepository):
        """Verify profile creation."""
        profile = await repo.create_profile(ProfileRecord(
            id="dev",
            driver="cli:claude",
            model="opus",
            validator_model="haiku",
            tracker="noop",
            working_dir="/path/to/repo",
        ))
        assert profile.id == "dev"
        assert profile.driver == "cli:claude"
        assert profile.is_active is False

    async def test_get_profile(self, repo: ProfileRepository):
        """Verify profile retrieval."""
        await repo.create_profile(ProfileRecord(
            id="dev",
            driver="cli:claude",
            model="opus",
            validator_model="haiku",
            tracker="noop",
            working_dir="/path/to/repo",
        ))
        profile = await repo.get_profile("dev")
        assert profile is not None
        assert profile.model == "opus"

    async def test_get_profile_not_found(self, repo: ProfileRepository):
        """Verify None returned for missing profile."""
        profile = await repo.get_profile("nonexistent")
        assert profile is None

    async def test_list_profiles(self, repo: ProfileRepository):
        """Verify listing all profiles."""
        await repo.create_profile(ProfileRecord(
            id="dev", driver="cli:claude", model="opus",
            validator_model="haiku", tracker="noop", working_dir="/repo1",
        ))
        await repo.create_profile(ProfileRecord(
            id="prod", driver="api:openrouter", model="gpt-4",
            validator_model="haiku", tracker="jira", working_dir="/repo2",
        ))
        profiles = await repo.list_profiles()
        assert len(profiles) == 2
        ids = {p.id for p in profiles}
        assert ids == {"dev", "prod"}

    async def test_update_profile(self, repo: ProfileRepository):
        """Verify profile updates."""
        await repo.create_profile(ProfileRecord(
            id="dev", driver="cli:claude", model="opus",
            validator_model="haiku", tracker="noop", working_dir="/repo",
        ))
        updated = await repo.update_profile("dev", {"model": "sonnet"})
        assert updated.model == "sonnet"

        # Verify persistence
        fetched = await repo.get_profile("dev")
        assert fetched.model == "sonnet"

    async def test_delete_profile(self, repo: ProfileRepository):
        """Verify profile deletion."""
        await repo.create_profile(ProfileRecord(
            id="dev", driver="cli:claude", model="opus",
            validator_model="haiku", tracker="noop", working_dir="/repo",
        ))
        result = await repo.delete_profile("dev")
        assert result is True
        assert await repo.get_profile("dev") is None

    async def test_delete_profile_not_found(self, repo: ProfileRepository):
        """Verify delete returns False for missing profile."""
        result = await repo.delete_profile("nonexistent")
        assert result is False

    async def test_set_active(self, repo: ProfileRepository):
        """Verify setting active profile."""
        await repo.create_profile(ProfileRecord(
            id="dev", driver="cli:claude", model="opus",
            validator_model="haiku", tracker="noop", working_dir="/repo",
        ))
        await repo.set_active("dev")
        profile = await repo.get_profile("dev")
        assert profile.is_active is True

    async def test_set_active_deactivates_others(self, repo: ProfileRepository):
        """Verify setting active profile deactivates others."""
        await repo.create_profile(ProfileRecord(
            id="dev", driver="cli:claude", model="opus",
            validator_model="haiku", tracker="noop", working_dir="/repo1",
        ))
        await repo.create_profile(ProfileRecord(
            id="prod", driver="api:openrouter", model="gpt-4",
            validator_model="haiku", tracker="jira", working_dir="/repo2",
        ))
        await repo.set_active("dev")
        await repo.set_active("prod")

        dev = await repo.get_profile("dev")
        prod = await repo.get_profile("prod")
        assert dev.is_active is False
        assert prod.is_active is True

    async def test_get_active_profile(self, repo: ProfileRepository):
        """Verify getting the active profile."""
        await repo.create_profile(ProfileRecord(
            id="dev", driver="cli:claude", model="opus",
            validator_model="haiku", tracker="noop", working_dir="/repo",
        ))
        await repo.set_active("dev")
        active = await repo.get_active_profile()
        assert active is not None
        assert active.id == "dev"

    async def test_get_active_profile_none(self, repo: ProfileRepository):
        """Verify None when no active profile."""
        active = await repo.get_active_profile()
        assert active is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_profile_repository.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement ProfileRepository**

```python
# amelia/server/database/profile_repository.py
"""Repository for profile management."""
from dataclasses import dataclass, field
from datetime import datetime

from amelia.server.database.connection import Database


@dataclass
class ProfileRecord:
    """Profile data record for database operations.

    This is a database-level representation. Use amelia.core.types.Profile
    for application-level profile operations.
    """

    id: str
    driver: str
    model: str
    validator_model: str
    tracker: str
    working_dir: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    max_review_iterations: int = 3
    max_task_review_iterations: int = 5
    auto_approve_reviews: bool = False
    is_active: bool = False
    created_at: datetime | None = field(default=None)
    updated_at: datetime | None = field(default=None)


class ProfileRepository:
    """Repository for profile CRUD operations."""

    def __init__(self, db: Database):
        """Initialize repository with database connection.

        Args:
            db: Database connection instance.
        """
        self._db = db

    async def list_profiles(self) -> list[ProfileRecord]:
        """List all profiles.

        Returns:
            List of all profiles, ordered by id.
        """
        rows = await self._db.fetch_all(
            "SELECT * FROM profiles ORDER BY id"
        )
        return [self._row_to_profile(row) for row in rows]

    async def get_profile(self, profile_id: str) -> ProfileRecord | None:
        """Get a profile by ID.

        Args:
            profile_id: Profile identifier.

        Returns:
            Profile if found, None otherwise.
        """
        row = await self._db.fetch_one(
            "SELECT * FROM profiles WHERE id = ?",
            (profile_id,),
        )
        return self._row_to_profile(row) if row else None

    async def get_active_profile(self) -> ProfileRecord | None:
        """Get the currently active profile.

        Returns:
            Active profile if one is set, None otherwise.
        """
        row = await self._db.fetch_one(
            "SELECT * FROM profiles WHERE is_active = 1"
        )
        return self._row_to_profile(row) if row else None

    async def create_profile(self, profile: ProfileRecord) -> ProfileRecord:
        """Create a new profile.

        Args:
            profile: Profile to create.

        Returns:
            Created profile with timestamps.

        Raises:
            sqlite3.IntegrityError: If profile ID already exists.
        """
        await self._db.execute(
            """INSERT INTO profiles (
                id, driver, model, validator_model, tracker, working_dir,
                plan_output_dir, plan_path_pattern, max_review_iterations,
                max_task_review_iterations, auto_approve_reviews, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile.id,
                profile.driver,
                profile.model,
                profile.validator_model,
                profile.tracker,
                profile.working_dir,
                profile.plan_output_dir,
                profile.path_pattern,
                profile.max_review_iterations,
                profile.max_task_review_iterations,
                1 if profile.auto_approve_reviews else 0,
                1 if profile.is_active else 0,
            ),
        )
        return await self.get_profile(profile.id)

    async def update_profile(self, profile_id: str, updates: dict) -> ProfileRecord:
        """Update a profile.

        Args:
            profile_id: Profile to update.
            updates: Dictionary of field names to new values.

        Returns:
            Updated profile.

        Raises:
            ValueError: If profile not found or invalid field names.
        """
        valid_fields = {
            "driver", "model", "validator_model", "tracker", "working_dir",
            "plan_output_dir", "plan_path_pattern", "max_review_iterations",
            "max_task_review_iterations", "auto_approve_reviews",
        }
        invalid = set(updates.keys()) - valid_fields
        if invalid:
            raise ValueError(f"Invalid profile fields: {invalid}")

        if not updates:
            profile = await self.get_profile(profile_id)
            if profile is None:
                raise ValueError(f"Profile not found: {profile_id}")
            return profile

        # Convert booleans to integers for SQLite
        db_updates = {}
        for k, v in updates.items():
            if isinstance(v, bool):
                db_updates[k] = 1 if v else 0
            else:
                db_updates[k] = v

        set_clauses = [f"{k} = ?" for k in db_updates.keys()]
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values = list(db_updates.values()) + [profile_id]

        rows_affected = await self._db.execute(
            f"UPDATE profiles SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        if rows_affected == 0:
            raise ValueError(f"Profile not found: {profile_id}")

        return await self.get_profile(profile_id)

    async def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile.

        Args:
            profile_id: Profile to delete.

        Returns:
            True if deleted, False if not found.
        """
        rows_affected = await self._db.execute(
            "DELETE FROM profiles WHERE id = ?",
            (profile_id,),
        )
        return rows_affected > 0

    async def set_active(self, profile_id: str) -> None:
        """Set a profile as active.

        The database trigger ensures only one profile is active.

        Args:
            profile_id: Profile to activate.

        Raises:
            ValueError: If profile not found.
        """
        rows_affected = await self._db.execute(
            "UPDATE profiles SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (profile_id,),
        )
        if rows_affected == 0:
            raise ValueError(f"Profile not found: {profile_id}")

    def _row_to_profile(self, row) -> ProfileRecord:
        """Convert database row to ProfileRecord.

        Args:
            row: Database row from profiles table.

        Returns:
            ProfileRecord instance.
        """
        return ProfileRecord(
            id=row["id"],
            driver=row["driver"],
            model=row["model"],
            validator_model=row["validator_model"],
            tracker=row["tracker"],
            working_dir=row["working_dir"],
            plan_output_dir=row["plan_output_dir"],
            plan_path_pattern=row["plan_path_pattern"],
            max_review_iterations=row["max_review_iterations"],
            max_task_review_iterations=row["max_task_review_iterations"],
            auto_approve_reviews=bool(row["auto_approve_reviews"]),
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_profile_repository.py -v`
Expected: PASS (after fixing the `plan_path_pattern` typo in create_profile)

**Step 5: Commit**

```bash
git add amelia/server/database/profile_repository.py tests/unit/server/test_profile_repository.py
git commit -m "$(cat <<'EOF'
feat(db): add ProfileRepository for profile management

CRUD operations for profiles table:
- list_profiles, get_profile, get_active_profile
- create_profile, update_profile, delete_profile
- set_active (with auto-deactivate trigger)

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.4: Export Repositories from Database Package

**Files:**
- Modify: `amelia/server/database/__init__.py`

**Step 1: Add exports**

```python
# amelia/server/database/__init__.py
"""Database connection and repositories."""
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRecord, ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.database.settings_repository import ServerSettings, SettingsRepository

__all__ = [
    "Database",
    "ProfileRecord",
    "ProfileRepository",
    "ServerSettings",
    "SettingsRepository",
    "WorkflowRepository",
]
```

**Step 2: Run type check**

Run: `uv run mypy amelia/server/database`
Expected: PASS

**Step 3: Commit**

```bash
git add amelia/server/database/__init__.py
git commit -m "$(cat <<'EOF'
refactor(db): export new repositories from database package

Adds ProfileRepository and SettingsRepository to public API.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2: Backend Migration

### Task 2.1: Strip ServerConfig to Bootstrap Only

**Files:**
- Modify: `amelia/server/config.py`
- Test: `tests/unit/server/test_config.py` (existing)

**Step 1: Write the test for new minimal ServerConfig**

```python
# Add to tests/unit/server/test_config.py
class TestBootstrapServerConfig:
    """Tests for bootstrap-only ServerConfig."""

    def test_only_bootstrap_fields(self):
        """Verify ServerConfig only has bootstrap fields."""
        config = ServerConfig()
        # These should exist
        assert hasattr(config, "host")
        assert hasattr(config, "port")
        assert hasattr(config, "database_path")

        # These should NOT exist (moved to database)
        assert not hasattr(config, "log_retention_days")
        assert not hasattr(config, "max_concurrent")
        assert not hasattr(config, "stream_tool_results")

    def test_defaults(self):
        """Verify default values."""
        config = ServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8420
        assert config.database_path == Path.home() / ".amelia" / "amelia.db"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_config.py::TestBootstrapServerConfig -v`
Expected: FAIL because current ServerConfig has all fields

**Step 3: Strip ServerConfig to bootstrap-only**

Replace contents of `amelia/server/config.py`:

```python
"""Bootstrap server configuration.

Only settings needed before database is available.
All other settings are stored in the database.
"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Minimal bootstrap configuration.

    Only settings needed before the database is available.
    All other server settings live in the server_settings database table.
    """

    model_config = SettingsConfigDict(
        env_prefix="AMELIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(
        default="127.0.0.1",
        description="Host to bind the server to",
    )
    port: int = Field(
        default=8420,
        ge=1,
        le=65535,
        description="Port to bind the server to",
    )
    database_path: Path = Field(
        default_factory=lambda: Path.home() / ".amelia" / "amelia.db",
        description="Path to SQLite database file",
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_config.py::TestBootstrapServerConfig -v`
Expected: PASS

**Step 5: Fix broken references**

Many files reference fields that no longer exist on ServerConfig. These need to be updated to use SettingsRepository. This is a larger refactoring step.

Run: `uv run mypy amelia/server`
Note the errors and fix each file.

**Step 6: Commit**

```bash
git add amelia/server/config.py tests/unit/server/test_config.py
git commit -m "$(cat <<'EOF'
refactor(config): strip ServerConfig to bootstrap-only

ServerConfig now only contains settings needed before DB:
- host, port, database_path

All other settings moved to server_settings database table.

BREAKING: Code using ServerConfig.log_retention_days etc. must
now use SettingsRepository.get_server_settings() instead.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.2: Update Server Startup to Initialize Settings

**Files:**
- Modify: `amelia/server/lifecycle/server.py`
- Modify: `amelia/server/dependencies.py`
- Test: `tests/integration/server/test_server_startup.py` (new)

**Step 1: Write integration test**

```python
# tests/integration/server/test_server_startup.py
"""Integration tests for server startup with database settings."""
import pytest
from pathlib import Path
import tempfile

from amelia.server.database import Database, SettingsRepository


class TestServerStartupSettings:
    """Tests for settings initialization on startup."""

    async def test_ensure_defaults_called_on_startup(self):
        """Verify server_settings are initialized on startup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            await db.connect()
            await db.ensure_schema()

            repo = SettingsRepository(db)
            await repo.ensure_defaults()

            settings = await repo.get_server_settings()
            assert settings.log_retention_days == 30

            await db.close()
```

**Step 2: Run test**

Run: `uv run pytest tests/integration/server/test_server_startup.py -v`
Expected: PASS

**Step 3: Add SettingsRepository to server dependencies**

In `amelia/server/dependencies.py`, add:

```python
from amelia.server.database import SettingsRepository

# Add getter function
def get_settings_repository() -> SettingsRepository:
    """Get the settings repository instance."""
    return SettingsRepository(get_database())
```

**Step 4: Update server startup to call ensure_defaults**

In `amelia/server/lifecycle/server.py`, in the startup logic, add after `db.ensure_schema()`:

```python
from amelia.server.database import SettingsRepository

# After ensure_schema()
settings_repo = SettingsRepository(db)
await settings_repo.ensure_defaults()
```

**Step 5: Commit**

```bash
git add amelia/server/lifecycle/server.py amelia/server/dependencies.py tests/integration/server/test_server_startup.py
git commit -m "$(cat <<'EOF'
feat(server): initialize settings repository on startup

Ensures server_settings singleton row exists when server starts.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.3: Create Settings API Routes

**Files:**
- Create: `amelia/server/routes/settings.py`
- Modify: `amelia/server/main.py` (add router)
- Test: `tests/unit/server/routes/test_settings_routes.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/routes/test_settings_routes.py
"""Tests for settings API routes."""
import pytest
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI

from amelia.server.routes.settings import router
from amelia.server.database import Database, SettingsRepository, ServerSettings


@pytest.fixture
def app():
    """Create test FastAPI app with settings router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestSettingsRoutes:
    """Tests for /api/settings endpoints."""

    def test_get_server_settings(self, client, monkeypatch):
        """GET /api/settings returns current settings."""
        mock_settings = ServerSettings(
            log_retention_days=30,
            log_retention_max_events=100000,
            trace_retention_days=7,
            checkpoint_retention_days=0,
            checkpoint_path="~/.amelia/checkpoints.db",
            websocket_idle_timeout_seconds=300.0,
            workflow_start_timeout_seconds=60.0,
            max_concurrent=5,
            stream_tool_results=False,
            created_at=None,
            updated_at=None,
        )

        with patch("amelia.server.routes.settings.get_settings_repository") as mock:
            mock_repo = AsyncMock()
            mock_repo.get_server_settings.return_value = mock_settings
            mock.return_value = mock_repo

            response = client.get("/api/settings")
            assert response.status_code == 200
            data = response.json()
            assert data["log_retention_days"] == 30
            assert data["max_concurrent"] == 5

    def test_update_server_settings(self, client):
        """PUT /api/settings updates settings."""
        with patch("amelia.server.routes.settings.get_settings_repository") as mock:
            mock_repo = AsyncMock()
            # Return updated settings
            mock_repo.update_server_settings.return_value = ServerSettings(
                log_retention_days=60,
                log_retention_max_events=100000,
                trace_retention_days=7,
                checkpoint_retention_days=0,
                checkpoint_path="~/.amelia/checkpoints.db",
                websocket_idle_timeout_seconds=300.0,
                workflow_start_timeout_seconds=60.0,
                max_concurrent=10,
                stream_tool_results=False,
                created_at=None,
                updated_at=None,
            )
            mock.return_value = mock_repo

            response = client.put(
                "/api/settings",
                json={"log_retention_days": 60, "max_concurrent": 10},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["log_retention_days"] == 60
            assert data["max_concurrent"] == 10
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_settings_routes.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement settings routes**

```python
# amelia/server/routes/settings.py
"""API routes for server settings and profiles."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from amelia.server.database import (
    ProfileRecord,
    ProfileRepository,
    ServerSettings,
    SettingsRepository,
)
from amelia.server.dependencies import get_database

router = APIRouter(prefix="/api", tags=["settings"])


def get_settings_repository() -> SettingsRepository:
    """Get settings repository dependency."""
    return SettingsRepository(get_database())


def get_profile_repository() -> ProfileRepository:
    """Get profile repository dependency."""
    return ProfileRepository(get_database())


# Response models
class ServerSettingsResponse(BaseModel):
    """Server settings API response."""

    log_retention_days: int
    log_retention_max_events: int
    trace_retention_days: int
    checkpoint_retention_days: int
    checkpoint_path: str
    websocket_idle_timeout_seconds: float
    workflow_start_timeout_seconds: float
    max_concurrent: int
    stream_tool_results: bool


class ServerSettingsUpdate(BaseModel):
    """Server settings update request."""

    log_retention_days: int | None = None
    log_retention_max_events: int | None = None
    trace_retention_days: int | None = None
    checkpoint_retention_days: int | None = None
    checkpoint_path: str | None = None
    websocket_idle_timeout_seconds: float | None = None
    workflow_start_timeout_seconds: float | None = None
    max_concurrent: int | None = None
    stream_tool_results: bool | None = None


class ProfileResponse(BaseModel):
    """Profile API response."""

    id: str
    driver: str
    model: str
    validator_model: str
    tracker: str
    working_dir: str
    plan_output_dir: str
    plan_path_pattern: str
    max_review_iterations: int
    max_task_review_iterations: int
    auto_approve_reviews: bool
    is_active: bool


class ProfileCreate(BaseModel):
    """Profile creation request."""

    id: str
    driver: str
    model: str
    validator_model: str
    tracker: str = "noop"
    working_dir: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    max_review_iterations: int = 3
    max_task_review_iterations: int = 5
    auto_approve_reviews: bool = False


class ProfileUpdate(BaseModel):
    """Profile update request."""

    driver: str | None = None
    model: str | None = None
    validator_model: str | None = None
    tracker: str | None = None
    working_dir: str | None = None
    plan_output_dir: str | None = None
    plan_path_pattern: str | None = None
    max_review_iterations: int | None = None
    max_task_review_iterations: int | None = None
    auto_approve_reviews: bool | None = None


# Server settings endpoints
@router.get("/settings", response_model=ServerSettingsResponse)
async def get_server_settings(
    repo: SettingsRepository = Depends(get_settings_repository),
) -> ServerSettingsResponse:
    """Get current server settings."""
    settings = await repo.get_server_settings()
    return ServerSettingsResponse(
        log_retention_days=settings.log_retention_days,
        log_retention_max_events=settings.log_retention_max_events,
        trace_retention_days=settings.trace_retention_days,
        checkpoint_retention_days=settings.checkpoint_retention_days,
        checkpoint_path=settings.checkpoint_path,
        websocket_idle_timeout_seconds=settings.websocket_idle_timeout_seconds,
        workflow_start_timeout_seconds=settings.workflow_start_timeout_seconds,
        max_concurrent=settings.max_concurrent,
        stream_tool_results=settings.stream_tool_results,
    )


@router.put("/settings", response_model=ServerSettingsResponse)
async def update_server_settings(
    updates: ServerSettingsUpdate,
    repo: SettingsRepository = Depends(get_settings_repository),
) -> ServerSettingsResponse:
    """Update server settings."""
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    settings = await repo.update_server_settings(update_dict)
    return ServerSettingsResponse(
        log_retention_days=settings.log_retention_days,
        log_retention_max_events=settings.log_retention_max_events,
        trace_retention_days=settings.trace_retention_days,
        checkpoint_retention_days=settings.checkpoint_retention_days,
        checkpoint_path=settings.checkpoint_path,
        websocket_idle_timeout_seconds=settings.websocket_idle_timeout_seconds,
        workflow_start_timeout_seconds=settings.workflow_start_timeout_seconds,
        max_concurrent=settings.max_concurrent,
        stream_tool_results=settings.stream_tool_results,
    )


# Profile endpoints
@router.get("/profiles", response_model=list[ProfileResponse])
async def list_profiles(
    repo: ProfileRepository = Depends(get_profile_repository),
) -> list[ProfileResponse]:
    """List all profiles."""
    profiles = await repo.list_profiles()
    return [_profile_to_response(p) for p in profiles]


@router.post("/profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(
    profile: ProfileCreate,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Create a new profile."""
    record = ProfileRecord(
        id=profile.id,
        driver=profile.driver,
        model=profile.model,
        validator_model=profile.validator_model,
        tracker=profile.tracker,
        working_dir=profile.working_dir,
        plan_output_dir=profile.plan_output_dir,
        plan_path_pattern=profile.plan_path_pattern,
        max_review_iterations=profile.max_review_iterations,
        max_task_review_iterations=profile.max_task_review_iterations,
        auto_approve_reviews=profile.auto_approve_reviews,
    )
    created = await repo.create_profile(record)
    return _profile_to_response(created)


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Get a profile by ID."""
    profile = await repo.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profile_to_response(profile)


@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    updates: ProfileUpdate,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Update a profile."""
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    try:
        updated = await repo.update_profile(profile_id, update_dict)
        return _profile_to_response(updated)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> None:
    """Delete a profile."""
    deleted = await repo.delete_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")


@router.post("/profiles/{profile_id}/activate", response_model=ProfileResponse)
async def activate_profile(
    profile_id: str,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Set a profile as active."""
    try:
        await repo.set_active(profile_id)
        profile = await repo.get_profile(profile_id)
        return _profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _profile_to_response(profile: ProfileRecord) -> ProfileResponse:
    """Convert ProfileRecord to API response."""
    return ProfileResponse(
        id=profile.id,
        driver=profile.driver,
        model=profile.model,
        validator_model=profile.validator_model,
        tracker=profile.tracker,
        working_dir=profile.working_dir,
        plan_output_dir=profile.plan_output_dir,
        plan_path_pattern=profile.plan_path_pattern,
        max_review_iterations=profile.max_review_iterations,
        max_task_review_iterations=profile.max_task_review_iterations,
        auto_approve_reviews=profile.auto_approve_reviews,
        is_active=profile.is_active,
    )
```

**Step 4: Add router to main.py**

In `amelia/server/main.py`, add:

```python
from amelia.server.routes.settings import router as settings_router

# In create_app() or wherever routers are included:
app.include_router(settings_router)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_settings_routes.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/routes/settings.py amelia/server/main.py tests/unit/server/routes/test_settings_routes.py
git commit -m "$(cat <<'EOF'
feat(api): add settings and profiles API routes

New endpoints:
- GET/PUT /api/settings - server settings
- GET/POST /api/profiles - list/create profiles
- GET/PUT/DELETE /api/profiles/{id} - profile CRUD
- POST /api/profiles/{id}/activate - set active

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.4: Update Orchestrator to Use ProfileRepository

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Test: `tests/unit/test_orchestrator_profile.py`

**Step 1: Write test for new profile loading**

```python
# tests/unit/test_orchestrator_profile.py
"""Tests for orchestrator profile loading from database."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.database import ProfileRecord


class TestOrchestratorProfileLoading:
    """Tests for profile loading in orchestrator."""

    async def test_get_profile_from_database(self):
        """Verify profile is loaded from database."""
        mock_profile_repo = AsyncMock()
        mock_profile_repo.get_profile.return_value = ProfileRecord(
            id="dev",
            driver="cli:claude",
            model="opus",
            validator_model="haiku",
            tracker="noop",
            working_dir="/repo",
        )

        # Test that orchestrator uses ProfileRepository
        # This is a behavioral test - implementation details in next step
        profile = await mock_profile_repo.get_profile("dev")
        assert profile is not None
        assert profile.driver == "cli:claude"
```

**Step 2: Update OrchestratorService**

In `amelia/server/orchestrator/service.py`:

1. Add ProfileRepository to `__init__`
2. Replace `_load_settings_for_worktree` with database lookup
3. Update `_get_profile_or_fail` to use ProfileRepository

Key changes:

```python
from amelia.server.database import ProfileRepository

class OrchestratorService:
    def __init__(self, ...):
        # Add
        self._profile_repo = ProfileRepository(db)

    async def _get_profile_or_fail(self, profile_name: str | None) -> Profile:
        """Get profile from database."""
        if profile_name:
            record = await self._profile_repo.get_profile(profile_name)
        else:
            record = await self._profile_repo.get_active_profile()

        if record is None:
            if profile_name:
                raise ValueError(f"Profile not found: {profile_name}")
            raise ValueError("No active profile set")

        return self._record_to_profile(record)

    def _record_to_profile(self, record: ProfileRecord) -> Profile:
        """Convert database record to Profile."""
        return Profile(
            name=record.id,
            driver=record.driver,
            model=record.model,
            validator_model=record.validator_model,
            tracker=record.tracker,
            working_dir=record.working_dir,
            plan_output_dir=record.plan_output_dir,
            plan_path_pattern=record.plan_path_pattern,
            max_review_iterations=record.max_review_iterations,
            max_task_review_iterations=record.max_task_review_iterations,
            auto_approve_reviews=record.auto_approve_reviews,
        )
```

**Step 3: Delete _load_settings_for_worktree method**

Remove the entire method and its usages.

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_orchestrator_profile.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/test_orchestrator_profile.py
git commit -m "$(cat <<'EOF'
refactor(orchestrator): load profiles from database

Replaces YAML-based _load_settings_for_worktree with
ProfileRepository database lookup.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.5: Delete YAML Configuration Files

**Files:**
- Delete: `amelia/config.py`
- Delete: `settings.amelia.yaml.example`

**Step 1: Verify no remaining references**

Run: `uv run grep -r "load_settings\|settings.amelia.yaml" amelia/`
Expected: No matches (or only comments)

**Step 2: Delete files**

```bash
rm amelia/config.py settings.amelia.yaml.example
```

**Step 3: Fix any import errors**

Run: `uv run mypy amelia`
Fix any remaining import errors.

**Step 4: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: remove YAML configuration system

Deletes amelia/config.py and settings.amelia.yaml.example.
All configuration now lives in the database.

BREAKING: Users must recreate profiles via CLI or dashboard.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3: CLI Commands

### Task 3.1: Add Config CLI Subcommand

**Files:**
- Create: `amelia/cli/config.py`
- Modify: `amelia/cli/__init__.py` or main CLI entry
- Test: `tests/unit/cli/test_config_cli.py`

**Step 1: Write the failing test**

```python
# tests/unit/cli/test_config_cli.py
"""Tests for amelia config CLI commands."""
import pytest
from typer.testing import CliRunner
from unittest.mock import AsyncMock, patch

from amelia.cli.config import config_app


runner = CliRunner()


class TestConfigProfileList:
    """Tests for profile list command."""

    def test_profile_list_empty(self):
        """Verify empty profile list output."""
        with patch("amelia.cli.config.get_profile_repository") as mock:
            mock_repo = AsyncMock()
            mock_repo.list_profiles.return_value = []
            mock.return_value = mock_repo

            result = runner.invoke(config_app, ["profile", "list"])
            assert result.exit_code == 0
            assert "No profiles configured" in result.output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/cli/test_config_cli.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement config CLI**

```python
# amelia/cli/config.py
"""Configuration management CLI commands."""
import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from amelia.server.database import Database, ProfileRecord, ProfileRepository, SettingsRepository
from amelia.server.config import ServerConfig

console = Console()
config_app = typer.Typer(name="config", help="Configuration management")
profile_app = typer.Typer(name="profile", help="Profile management")
server_app = typer.Typer(name="server", help="Server settings management")

config_app.add_typer(profile_app)
config_app.add_typer(server_app)


def get_database() -> Database:
    """Get database connection."""
    config = ServerConfig()
    db = Database(config.database_path)
    return db


async def _get_profile_repository() -> ProfileRepository:
    """Get profile repository with connected database."""
    db = get_database()
    await db.connect()
    await db.ensure_schema()
    return ProfileRepository(db)


def get_profile_repository() -> ProfileRepository:
    """Sync wrapper for getting profile repository."""
    return asyncio.run(_get_profile_repository())


@profile_app.command("list")
def profile_list():
    """List all profiles."""
    async def _list():
        repo = await _get_profile_repository()
        profiles = await repo.list_profiles()

        if not profiles:
            console.print("[yellow]No profiles configured[/yellow]")
            console.print("Create one with: amelia config profile create")
            return

        table = Table(title="Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Driver")
        table.add_column("Model")
        table.add_column("Working Dir")
        table.add_column("Active", style="green")

        for p in profiles:
            table.add_row(
                p.id,
                p.driver,
                p.model,
                p.working_dir,
                "✓" if p.is_active else "",
            )

        console.print(table)

    asyncio.run(_list())


@profile_app.command("show")
def profile_show(name: Annotated[str, typer.Argument(help="Profile name")]):
    """Show profile details."""
    async def _show():
        repo = await _get_profile_repository()
        profile = await repo.get_profile(name)

        if profile is None:
            console.print(f"[red]Profile not found: {name}[/red]")
            raise typer.Exit(1)

        console.print(f"[bold]Profile: {profile.id}[/bold]")
        console.print(f"  Driver: {profile.driver}")
        console.print(f"  Model: {profile.model}")
        console.print(f"  Validator: {profile.validator_model}")
        console.print(f"  Tracker: {profile.tracker}")
        console.print(f"  Working Dir: {profile.working_dir}")
        console.print(f"  Active: {'Yes' if profile.is_active else 'No'}")

    asyncio.run(_show())


@profile_app.command("create")
def profile_create(
    name: Annotated[str | None, typer.Option("--name", "-n", help="Profile name")] = None,
    driver: Annotated[str | None, typer.Option("--driver", "-d", help="Driver (cli:claude or api:openrouter)")] = None,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Model name")] = None,
    working_dir: Annotated[str | None, typer.Option("--working-dir", "-w", help="Working directory")] = None,
):
    """Create a new profile (interactive if no options provided)."""
    async def _create():
        # Interactive mode if no options
        if not all([name, driver, model, working_dir]):
            console.print("[bold]Create new profile[/bold]\n")
            _name = name or typer.prompt("Profile name", default="dev")
            _driver = driver or typer.prompt("Driver (cli:claude, api:openrouter)", default="cli:claude")
            _model = model or typer.prompt("Model", default="opus")
            _working_dir = working_dir or typer.prompt("Working directory", default=str(Path.cwd()))
        else:
            _name, _driver, _model, _working_dir = name, driver, model, working_dir

        repo = await _get_profile_repository()

        record = ProfileRecord(
            id=_name,
            driver=_driver,
            model=_model,
            validator_model="haiku",  # Default
            tracker="noop",
            working_dir=_working_dir,
        )

        await repo.create_profile(record)
        console.print(f"[green]✓ Profile '{_name}' created[/green]")

    asyncio.run(_create())


@profile_app.command("delete")
def profile_delete(name: Annotated[str, typer.Argument(help="Profile name")]):
    """Delete a profile."""
    async def _delete():
        repo = await _get_profile_repository()
        deleted = await repo.delete_profile(name)

        if not deleted:
            console.print(f"[red]Profile not found: {name}[/red]")
            raise typer.Exit(1)

        console.print(f"[green]✓ Profile '{name}' deleted[/green]")

    asyncio.run(_delete())


@profile_app.command("activate")
def profile_activate(name: Annotated[str, typer.Argument(help="Profile name")]):
    """Set a profile as active."""
    async def _activate():
        repo = await _get_profile_repository()
        try:
            await repo.set_active(name)
            console.print(f"[green]✓ Profile '{name}' is now active[/green]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

    asyncio.run(_activate())


@server_app.command("show")
def server_show():
    """Show server settings."""
    async def _show():
        db = get_database()
        await db.connect()
        await db.ensure_schema()
        repo = SettingsRepository(db)
        await repo.ensure_defaults()
        settings = await repo.get_server_settings()

        console.print("[bold]Server Settings[/bold]\n")
        console.print(f"  Log Retention: {settings.log_retention_days} days")
        console.print(f"  Trace Retention: {settings.trace_retention_days} days")
        console.print(f"  Max Concurrent: {settings.max_concurrent}")
        console.print(f"  Stream Tool Results: {settings.stream_tool_results}")

    asyncio.run(_show())


@server_app.command("set")
def server_set(
    key: Annotated[str, typer.Argument(help="Setting key")],
    value: Annotated[str, typer.Argument(help="Setting value")],
):
    """Set a server setting."""
    async def _set():
        db = get_database()
        await db.connect()
        await db.ensure_schema()
        repo = SettingsRepository(db)
        await repo.ensure_defaults()

        # Convert value to appropriate type
        parsed_value: int | float | bool | str = value
        if value.lower() in ("true", "false"):
            parsed_value = value.lower() == "true"
        elif value.isdigit():
            parsed_value = int(value)
        elif "." in value:
            try:
                parsed_value = float(value)
            except ValueError:
                pass

        try:
            await repo.update_server_settings({key: parsed_value})
            console.print(f"[green]✓ Set {key} = {parsed_value}[/green]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

    asyncio.run(_set())
```

**Step 4: Add to main CLI**

In main CLI file, add:

```python
from amelia.cli.config import config_app

app.add_typer(config_app)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/cli/test_config_cli.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/cli/config.py tests/unit/cli/test_config_cli.py
git commit -m "$(cat <<'EOF'
feat(cli): add amelia config subcommand

New commands:
- amelia config profile list/show/create/delete/activate
- amelia config server show/set

Interactive profile creation when no options provided.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.2: Add First-Run Interactive Setup

**Files:**
- Modify: `amelia/cli/config.py`
- Modify: `amelia/server/cli.py` (dev/start commands)
- Test: `tests/unit/cli/test_first_run.py`

**Step 1: Write the test**

```python
# tests/unit/cli/test_first_run.py
"""Tests for first-run interactive setup."""
import pytest
from unittest.mock import AsyncMock, patch

from amelia.cli.config import check_first_run


class TestFirstRun:
    """Tests for first-run detection and setup."""

    async def test_first_run_detected_when_no_profiles(self):
        """Verify first run is detected when no profiles exist."""
        mock_repo = AsyncMock()
        mock_repo.list_profiles.return_value = []

        is_first_run = len(await mock_repo.list_profiles()) == 0
        assert is_first_run is True

    async def test_not_first_run_when_profiles_exist(self):
        """Verify first run is not detected when profiles exist."""
        mock_repo = AsyncMock()
        mock_repo.list_profiles.return_value = [AsyncMock()]

        is_first_run = len(await mock_repo.list_profiles()) == 0
        assert is_first_run is False
```

**Step 2: Implement first-run check**

Add to `amelia/cli/config.py`:

```python
async def check_and_run_first_time_setup() -> bool:
    """Check if this is first run and prompt for profile creation.

    Returns:
        True if setup completed or not needed, False if user cancelled.
    """
    repo = await _get_profile_repository()
    profiles = await repo.list_profiles()

    if profiles:
        return True  # Not first run

    console.print("[yellow]No profiles configured. Let's create your first profile.[/yellow]\n")

    name = typer.prompt("Profile name", default="dev")
    driver = typer.prompt("Driver (cli:claude, api:openrouter)", default="cli:claude")
    model = typer.prompt("Model", default="opus")
    working_dir = typer.prompt("Working directory", default=str(Path.cwd()))

    record = ProfileRecord(
        id=name,
        driver=driver,
        model=model,
        validator_model="haiku",
        tracker="noop",
        working_dir=working_dir,
    )

    await repo.create_profile(record)
    await repo.set_active(name)

    console.print(f"\n[green]✓ Profile '{name}' created and set as active.[/green]")
    return True
```

**Step 3: Add to dev/start commands**

In `amelia/server/cli.py`, at the start of `dev` and `start` commands:

```python
from amelia.cli.config import check_and_run_first_time_setup

# At start of command
if not asyncio.run(check_and_run_first_time_setup()):
    raise typer.Exit(1)
```

**Step 4: Commit**

```bash
git add amelia/cli/config.py amelia/server/cli.py tests/unit/cli/test_first_run.py
git commit -m "$(cat <<'EOF'
feat(cli): add first-run interactive profile setup

Prompts user to create initial profile when no profiles exist.
Triggered by amelia dev/start commands.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4: Dashboard UI

### Task 4.1: Add Settings API Client

**Files:**
- Create: `dashboard/src/api/settings.ts`
- Test: `dashboard/src/api/__tests__/settings.test.ts`

**Step 1: Write the test**

```typescript
// dashboard/src/api/__tests__/settings.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getServerSettings, updateServerSettings, getProfiles, createProfile, deleteProfile, activateProfile } from '../settings';

describe('Settings API', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    global.fetch = vi.fn();
  });

  describe('getServerSettings', () => {
    it('fetches server settings', async () => {
      const mockSettings = { log_retention_days: 30, max_concurrent: 5 };
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSettings),
      });

      const result = await getServerSettings();
      expect(result).toEqual(mockSettings);
      expect(fetch).toHaveBeenCalledWith('/api/settings');
    });
  });

  describe('getProfiles', () => {
    it('fetches all profiles', async () => {
      const mockProfiles = [{ id: 'dev', driver: 'cli:claude', is_active: true }];
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProfiles),
      });

      const result = await getProfiles();
      expect(result).toEqual(mockProfiles);
      expect(fetch).toHaveBeenCalledWith('/api/profiles');
    });
  });
});
```

**Step 2: Implement API client**

```typescript
// dashboard/src/api/settings.ts
/**
 * API client for settings and profiles endpoints.
 */

export interface ServerSettings {
  log_retention_days: number;
  log_retention_max_events: number;
  trace_retention_days: number;
  checkpoint_retention_days: number;
  checkpoint_path: string;
  websocket_idle_timeout_seconds: number;
  workflow_start_timeout_seconds: number;
  max_concurrent: number;
  stream_tool_results: boolean;
}

export interface Profile {
  id: string;
  driver: string;
  model: string;
  validator_model: string;
  tracker: string;
  working_dir: string;
  plan_output_dir: string;
  plan_path_pattern: string;
  max_review_iterations: number;
  max_task_review_iterations: number;
  auto_approve_reviews: boolean;
  is_active: boolean;
}

export interface ProfileCreate {
  id: string;
  driver: string;
  model: string;
  validator_model: string;
  tracker?: string;
  working_dir: string;
  plan_output_dir?: string;
  plan_path_pattern?: string;
  max_review_iterations?: number;
  max_task_review_iterations?: number;
  auto_approve_reviews?: boolean;
}

export interface ProfileUpdate {
  driver?: string;
  model?: string;
  validator_model?: string;
  tracker?: string;
  working_dir?: string;
  plan_output_dir?: string;
  plan_path_pattern?: string;
  max_review_iterations?: number;
  max_task_review_iterations?: number;
  auto_approve_reviews?: boolean;
}

// Server settings
export async function getServerSettings(): Promise<ServerSettings> {
  const response = await fetch('/api/settings');
  if (!response.ok) {
    throw new Error(`Failed to fetch settings: ${response.statusText}`);
  }
  return response.json();
}

export async function updateServerSettings(updates: Partial<ServerSettings>): Promise<ServerSettings> {
  const response = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!response.ok) {
    throw new Error(`Failed to update settings: ${response.statusText}`);
  }
  return response.json();
}

// Profiles
export async function getProfiles(): Promise<Profile[]> {
  const response = await fetch('/api/profiles');
  if (!response.ok) {
    throw new Error(`Failed to fetch profiles: ${response.statusText}`);
  }
  return response.json();
}

export async function getProfile(id: string): Promise<Profile> {
  const response = await fetch(`/api/profiles/${encodeURIComponent(id)}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch profile: ${response.statusText}`);
  }
  return response.json();
}

export async function createProfile(profile: ProfileCreate): Promise<Profile> {
  const response = await fetch('/api/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
  if (!response.ok) {
    throw new Error(`Failed to create profile: ${response.statusText}`);
  }
  return response.json();
}

export async function updateProfile(id: string, updates: ProfileUpdate): Promise<Profile> {
  const response = await fetch(`/api/profiles/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!response.ok) {
    throw new Error(`Failed to update profile: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteProfile(id: string): Promise<void> {
  const response = await fetch(`/api/profiles/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(`Failed to delete profile: ${response.statusText}`);
  }
}

export async function activateProfile(id: string): Promise<Profile> {
  const response = await fetch(`/api/profiles/${encodeURIComponent(id)}/activate`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to activate profile: ${response.statusText}`);
  }
  return response.json();
}
```

**Step 3: Run tests**

Run: `cd dashboard && pnpm test:run src/api/__tests__/settings.test.ts`
Expected: PASS

**Step 4: Commit**

```bash
git add dashboard/src/api/settings.ts dashboard/src/api/__tests__/settings.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): add settings API client

Client functions for settings and profiles endpoints.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.2: Create Settings Loader

**Files:**
- Create: `dashboard/src/loaders/settings.ts`
- Modify: `dashboard/src/loaders/index.ts`

**Step 1: Implement loader**

```typescript
// dashboard/src/loaders/settings.ts
/**
 * React Router loaders for settings pages.
 */
import { getServerSettings, getProfiles } from '@/api/settings';
import type { ServerSettings, Profile } from '@/api/settings';

export interface SettingsLoaderData {
  serverSettings: ServerSettings;
  profiles: Profile[];
}

export async function settingsLoader(): Promise<SettingsLoaderData> {
  const [serverSettings, profiles] = await Promise.all([
    getServerSettings(),
    getProfiles(),
  ]);
  return { serverSettings, profiles };
}

export async function profilesLoader(): Promise<{ profiles: Profile[] }> {
  const profiles = await getProfiles();
  return { profiles };
}

export async function serverSettingsLoader(): Promise<{ serverSettings: ServerSettings }> {
  const serverSettings = await getServerSettings();
  return { serverSettings };
}
```

**Step 2: Export from index**

In `dashboard/src/loaders/index.ts`, add:

```typescript
export { settingsLoader, profilesLoader, serverSettingsLoader } from './settings';
```

**Step 3: Commit**

```bash
git add dashboard/src/loaders/settings.ts dashboard/src/loaders/index.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): add settings loaders

React Router loaders for settings and profiles data.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.3: Create SettingsProfilesPage

**Files:**
- Create: `dashboard/src/pages/SettingsProfilesPage.tsx`
- Create: `dashboard/src/components/settings/ProfileCard.tsx`
- Test: `dashboard/src/pages/__tests__/SettingsProfilesPage.test.tsx`

**Step 1: Create ProfileCard component**

```tsx
// dashboard/src/components/settings/ProfileCard.tsx
/**
 * Card component displaying a profile with actions.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { MoreHorizontal, Pencil, Trash2, Star } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { Profile } from '@/api/settings';

interface ProfileCardProps {
  profile: Profile;
  onEdit: (profile: Profile) => void;
  onDelete: (profile: Profile) => void;
  onActivate: (profile: Profile) => void;
}

export function ProfileCard({ profile, onEdit, onDelete, onActivate }: ProfileCardProps) {
  const driverColor = profile.driver.startsWith('cli:') ? 'bg-yellow-500/10 text-yellow-500' : 'bg-blue-500/10 text-blue-500';

  return (
    <Card className={profile.is_active ? 'border-primary' : ''}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">{profile.id}</CardTitle>
          {profile.is_active && (
            <Badge variant="secondary" className="text-xs">
              <Star className="mr-1 h-3 w-3" /> Active
            </Badge>
          )}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 p-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit(profile)}>
              <Pencil className="mr-2 h-4 w-4" /> Edit
            </DropdownMenuItem>
            {!profile.is_active && (
              <DropdownMenuItem onClick={() => onActivate(profile)}>
                <Star className="mr-2 h-4 w-4" /> Set Active
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              onClick={() => onDelete(profile)}
              className="text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardHeader>
      <CardContent>
        <div className="space-y-1 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={driverColor}>
              {profile.driver}
            </Badge>
            <span>{profile.model}</span>
          </div>
          <div className="truncate">{profile.working_dir}</div>
        </div>
      </CardContent>
    </Card>
  );
}
```

**Step 2: Create SettingsProfilesPage**

```tsx
// dashboard/src/pages/SettingsProfilesPage.tsx
/**
 * Settings page for managing profiles.
 */
import { useState } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Plus, Search } from 'lucide-react';
import { ProfileCard } from '@/components/settings/ProfileCard';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { deleteProfile, activateProfile } from '@/api/settings';
import type { Profile } from '@/api/settings';
import { useToast } from '@/hooks/use-toast';

interface LoaderData {
  profiles: Profile[];
}

type DriverFilter = 'all' | 'api' | 'cli';

export default function SettingsProfilesPage() {
  const { profiles } = useLoaderData() as LoaderData;
  const { revalidate } = useRevalidator();
  const { toast } = useToast();

  const [search, setSearch] = useState('');
  const [driverFilter, setDriverFilter] = useState<DriverFilter>('all');

  // Filter profiles
  const filteredProfiles = profiles.filter((p) => {
    if (search && !p.id.toLowerCase().includes(search.toLowerCase())) {
      return false;
    }
    if (driverFilter === 'api' && !p.driver.startsWith('api:')) {
      return false;
    }
    if (driverFilter === 'cli' && !p.driver.startsWith('cli:')) {
      return false;
    }
    return true;
  });

  // Sort: active first, then by name
  const sortedProfiles = [...filteredProfiles].sort((a, b) => {
    if (a.is_active && !b.is_active) return -1;
    if (!a.is_active && b.is_active) return 1;
    return a.id.localeCompare(b.id);
  });

  const handleEdit = (profile: Profile) => {
    // TODO: Open edit modal
    console.log('Edit', profile);
  };

  const handleDelete = async (profile: Profile) => {
    if (!confirm(`Delete profile "${profile.id}"?`)) return;
    try {
      await deleteProfile(profile.id);
      toast({ title: 'Profile deleted' });
      revalidate();
    } catch (e) {
      toast({ title: 'Failed to delete profile', variant: 'destructive' });
    }
  };

  const handleActivate = async (profile: Profile) => {
    try {
      await activateProfile(profile.id);
      toast({ title: `Profile "${profile.id}" is now active` });
      revalidate();
    } catch (e) {
      toast({ title: 'Failed to activate profile', variant: 'destructive' });
    }
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Profiles</h1>
        <Button>
          <Plus className="mr-2 h-4 w-4" /> Create Profile
        </Button>
      </div>

      <div className="flex items-center gap-4">
        <Tabs value={driverFilter} onValueChange={(v) => setDriverFilter(v as DriverFilter)}>
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="api">API</TabsTrigger>
            <TabsTrigger value="cli">CLI</TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search profiles..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
      </div>

      {sortedProfiles.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          {profiles.length === 0 ? (
            <p>No profiles configured. Create one to get started.</p>
          ) : (
            <p>No profiles match your search.</p>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {sortedProfiles.map((profile) => (
            <ProfileCard
              key={profile.id}
              profile={profile}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onActivate={handleActivate}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 3: Write test**

```tsx
// dashboard/src/pages/__tests__/SettingsProfilesPage.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import SettingsProfilesPage from '../SettingsProfilesPage';

const mockProfiles = [
  { id: 'dev', driver: 'cli:claude', model: 'opus', is_active: true, working_dir: '/repo' },
  { id: 'prod', driver: 'api:openrouter', model: 'gpt-4', is_active: false, working_dir: '/prod' },
];

describe('SettingsProfilesPage', () => {
  it('renders profile cards', async () => {
    const router = createMemoryRouter([
      {
        path: '/',
        element: <SettingsProfilesPage />,
        loader: () => ({ profiles: mockProfiles }),
      },
    ]);

    render(<RouterProvider router={router} />);

    expect(await screen.findByText('dev')).toBeInTheDocument();
    expect(screen.getByText('prod')).toBeInTheDocument();
  });

  it('shows active badge on active profile', async () => {
    const router = createMemoryRouter([
      {
        path: '/',
        element: <SettingsProfilesPage />,
        loader: () => ({ profiles: mockProfiles }),
      },
    ]);

    render(<RouterProvider router={router} />);

    expect(await screen.findByText('Active')).toBeInTheDocument();
  });
});
```

**Step 4: Run tests**

Run: `cd dashboard && pnpm test:run src/pages/__tests__/SettingsProfilesPage.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/pages/SettingsProfilesPage.tsx dashboard/src/components/settings/ProfileCard.tsx dashboard/src/pages/__tests__/SettingsProfilesPage.test.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): add profiles settings page

Profile management UI with:
- Card grid layout
- Active profile highlighting
- Filter by driver type
- Search by name
- Delete and activate actions

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.4: Create SettingsServerPage

**Files:**
- Create: `dashboard/src/pages/SettingsServerPage.tsx`
- Create: `dashboard/src/components/settings/ServerSettingsForm.tsx`

**Step 1: Create ServerSettingsForm**

```tsx
// dashboard/src/components/settings/ServerSettingsForm.tsx
/**
 * Form component for editing server settings.
 */
import { useState, useEffect } from 'react';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import type { ServerSettings } from '@/api/settings';

interface ServerSettingsFormProps {
  settings: ServerSettings;
  onSave: (updates: Partial<ServerSettings>) => Promise<void>;
  isSaving: boolean;
}

const RETENTION_OPTIONS = [7, 14, 30, 60, 90];
const CONCURRENT_OPTIONS = [1, 3, 5, 10, 20];

export function ServerSettingsForm({ settings, onSave, isSaving }: ServerSettingsFormProps) {
  const [formData, setFormData] = useState(settings);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setFormData(settings);
    setHasChanges(false);
  }, [settings]);

  const handleChange = <K extends keyof ServerSettings>(key: K, value: ServerSettings[K]) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleReset = () => {
    setFormData(settings);
    setHasChanges(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const updates: Partial<ServerSettings> = {};
    for (const key of Object.keys(formData) as (keyof ServerSettings)[]) {
      if (formData[key] !== settings[key]) {
        updates[key] = formData[key];
      }
    }
    await onSave(updates);
    setHasChanges(false);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {/* Retention Policies */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Retention Policies</h3>
          <p className="text-sm text-muted-foreground">
            Configure how long to keep logs, traces, and checkpoints.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="log_retention_days">Log Retention</Label>
            <Select
              value={String(formData.log_retention_days)}
              onValueChange={(v) => handleChange('log_retention_days', Number(v))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RETENTION_OPTIONS.map((days) => (
                  <SelectItem key={days} value={String(days)}>
                    {days} days
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="trace_retention_days">Trace Retention</Label>
            <Select
              value={String(formData.trace_retention_days)}
              onValueChange={(v) => handleChange('trace_retention_days', Number(v))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">Disabled</SelectItem>
                {RETENTION_OPTIONS.map((days) => (
                  <SelectItem key={days} value={String(days)}>
                    {days} days
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </section>

      {/* Execution Limits */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Execution Limits</h3>
          <p className="text-sm text-muted-foreground">
            Control concurrent workflow execution.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="max_concurrent">Max Concurrent Workflows</Label>
          <Select
            value={String(formData.max_concurrent)}
            onValueChange={(v) => handleChange('max_concurrent', Number(v))}
          >
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CONCURRENT_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </section>

      {/* Debugging */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Debugging</h3>
          <p className="text-sm text-muted-foreground">
            Options for debugging workflow execution.
          </p>
        </div>

        <div className="flex items-center justify-between rounded-lg border p-4">
          <div className="space-y-0.5">
            <Label htmlFor="stream_tool_results">Stream Tool Results</Label>
            <p className="text-sm text-muted-foreground">
              Enable streaming of tool results to dashboard WebSocket.
            </p>
          </div>
          <Switch
            id="stream_tool_results"
            checked={formData.stream_tool_results}
            onCheckedChange={(checked) => handleChange('stream_tool_results', checked)}
          />
        </div>
      </section>

      {/* Footer */}
      {hasChanges && (
        <div className="sticky bottom-0 flex items-center justify-between border-t bg-background pt-4">
          <p className="text-sm text-muted-foreground">You have unsaved changes</p>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={handleReset}>
              Reset
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </div>
      )}
    </form>
  );
}
```

**Step 2: Create SettingsServerPage**

```tsx
// dashboard/src/pages/SettingsServerPage.tsx
/**
 * Settings page for server configuration.
 */
import { useState } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { ServerSettingsForm } from '@/components/settings/ServerSettingsForm';
import { updateServerSettings } from '@/api/settings';
import type { ServerSettings } from '@/api/settings';
import { useToast } from '@/hooks/use-toast';

interface LoaderData {
  serverSettings: ServerSettings;
}

export default function SettingsServerPage() {
  const { serverSettings } = useLoaderData() as LoaderData;
  const { revalidate } = useRevalidator();
  const { toast } = useToast();
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async (updates: Partial<ServerSettings>) => {
    setIsSaving(true);
    try {
      await updateServerSettings(updates);
      toast({ title: 'Settings saved' });
      revalidate();
    } catch (e) {
      toast({ title: 'Failed to save settings', variant: 'destructive' });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="container mx-auto py-6 max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Server Settings</h1>
      <ServerSettingsForm
        settings={serverSettings}
        onSave={handleSave}
        isSaving={isSaving}
      />
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add dashboard/src/pages/SettingsServerPage.tsx dashboard/src/components/settings/ServerSettingsForm.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): add server settings page

Server configuration UI with:
- Retention policy dropdowns
- Max concurrent workflows
- Debug toggle for tool streaming
- Unsaved changes indicator

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.5: Add Settings Routes to Router

**Files:**
- Modify: `dashboard/src/router.tsx`
- Create: `dashboard/src/components/settings/SettingsLayout.tsx`

**Step 1: Create SettingsLayout with tab navigation**

```tsx
// dashboard/src/components/settings/SettingsLayout.tsx
/**
 * Layout with tab navigation for settings pages.
 */
import { NavLink, Outlet } from 'react-router-dom';
import { cn } from '@/lib/utils';

const tabs = [
  { to: '/settings/profiles', label: 'Profiles' },
  { to: '/settings/server', label: 'Server' },
];

export function SettingsLayout() {
  return (
    <div>
      <div className="border-b">
        <nav className="container flex gap-4">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                cn(
                  'py-4 text-sm font-medium border-b-2 -mb-px',
                  isActive
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <Outlet />
    </div>
  );
}
```

**Step 2: Add routes to router.tsx**

In `dashboard/src/router.tsx`, add:

```tsx
import { profilesLoader, serverSettingsLoader } from '@/loaders/settings';

// In the children array, add:
{
  path: 'settings',
  lazy: async () => {
    const { SettingsLayout } = await import('@/components/settings/SettingsLayout');
    return { Component: SettingsLayout };
  },
  children: [
    {
      index: true,
      element: <Navigate to="/settings/profiles" replace />,
    },
    {
      path: 'profiles',
      loader: profilesLoader,
      lazy: async () => {
        const { default: Component } = await import('@/pages/SettingsProfilesPage');
        return { Component };
      },
    },
    {
      path: 'server',
      loader: serverSettingsLoader,
      lazy: async () => {
        const { default: Component } = await import('@/pages/SettingsServerPage');
        return { Component };
      },
    },
  ],
},
```

**Step 3: Add Settings link to sidebar**

In `dashboard/src/components/DashboardSidebar.tsx`, add a Settings nav item.

**Step 4: Commit**

```bash
git add dashboard/src/router.tsx dashboard/src/components/settings/SettingsLayout.tsx dashboard/src/components/DashboardSidebar.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): add settings routes with tab navigation

Routes:
- /settings → redirects to /settings/profiles
- /settings/profiles → profile management
- /settings/server → server configuration

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.6: Create Profile Edit Modal

**Files:**
- Create: `dashboard/src/components/settings/ProfileEditModal.tsx`
- Modify: `dashboard/src/pages/SettingsProfilesPage.tsx`

**Step 1: Create ProfileEditModal**

```tsx
// dashboard/src/components/settings/ProfileEditModal.tsx
/**
 * Modal for creating and editing profiles.
 */
import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { ChevronDown } from 'lucide-react';
import { WorktreePathField } from '@/components/WorktreePathField';
import type { Profile, ProfileCreate, ProfileUpdate } from '@/api/settings';

interface ProfileEditModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profile: Profile | null; // null = create mode
  onSave: (profile: ProfileCreate | ProfileUpdate, id?: string) => Promise<void>;
}

const DRIVER_OPTIONS = [
  { value: 'cli:claude', label: 'CLI: Claude' },
  { value: 'api:openrouter', label: 'API: OpenRouter' },
];

const TRACKER_OPTIONS = [
  { value: 'noop', label: 'None' },
  { value: 'github', label: 'GitHub' },
  { value: 'jira', label: 'Jira' },
];

export function ProfileEditModal({ open, onOpenChange, profile, onSave }: ProfileEditModalProps) {
  const isEdit = profile !== null;
  const [isSaving, setIsSaving] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const [formData, setFormData] = useState<ProfileCreate>({
    id: '',
    driver: 'cli:claude',
    model: 'opus',
    validator_model: 'haiku',
    tracker: 'noop',
    working_dir: '',
    plan_output_dir: 'docs/plans',
    plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
    max_review_iterations: 3,
    max_task_review_iterations: 5,
    auto_approve_reviews: false,
  });

  useEffect(() => {
    if (profile) {
      setFormData({
        id: profile.id,
        driver: profile.driver,
        model: profile.model,
        validator_model: profile.validator_model,
        tracker: profile.tracker,
        working_dir: profile.working_dir,
        plan_output_dir: profile.plan_output_dir,
        plan_path_pattern: profile.plan_path_pattern,
        max_review_iterations: profile.max_review_iterations,
        max_task_review_iterations: profile.max_task_review_iterations,
        auto_approve_reviews: profile.auto_approve_reviews,
      });
    } else {
      setFormData({
        id: '',
        driver: 'cli:claude',
        model: 'opus',
        validator_model: 'haiku',
        tracker: 'noop',
        working_dir: '',
      });
    }
  }, [profile, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      if (isEdit) {
        const { id, ...updates } = formData;
        await onSave(updates, profile.id);
      } else {
        await onSave(formData);
      }
      onOpenChange(false);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? 'Edit Profile' : 'Create Profile'}</DialogTitle>
            <DialogDescription>
              {isEdit ? 'Modify profile settings.' : 'Create a new execution profile.'}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* Basic Settings */}
            <div className="grid gap-2">
              <Label htmlFor="id">Name</Label>
              <Input
                id="id"
                value={formData.id}
                onChange={(e) => setFormData((p) => ({ ...p, id: e.target.value }))}
                disabled={isEdit}
                placeholder="dev"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="driver">Driver</Label>
              <Select
                value={formData.driver}
                onValueChange={(v) => setFormData((p) => ({ ...p, driver: v }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DRIVER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="model">Model</Label>
              <Input
                id="model"
                value={formData.model}
                onChange={(e) => setFormData((p) => ({ ...p, model: e.target.value }))}
                placeholder="opus"
              />
            </div>

            <div className="grid gap-2">
              <Label>Working Directory</Label>
              <WorktreePathField
                value={formData.working_dir}
                onChange={(v) => setFormData((p) => ({ ...p, working_dir: v }))}
              />
            </div>

            {/* Advanced Settings */}
            <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" className="w-full justify-between">
                  Advanced Settings
                  <ChevronDown className={`h-4 w-4 transition-transform ${advancedOpen ? 'rotate-180' : ''}`} />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-4 pt-4">
                <div className="grid gap-2">
                  <Label htmlFor="validator_model">Validator Model</Label>
                  <Input
                    id="validator_model"
                    value={formData.validator_model}
                    onChange={(e) => setFormData((p) => ({ ...p, validator_model: e.target.value }))}
                  />
                </div>

                <div className="grid gap-2">
                  <Label htmlFor="tracker">Tracker</Label>
                  <Select
                    value={formData.tracker}
                    onValueChange={(v) => setFormData((p) => ({ ...p, tracker: v }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TRACKER_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center justify-between">
                  <Label htmlFor="auto_approve">Auto-approve Reviews</Label>
                  <Switch
                    id="auto_approve"
                    checked={formData.auto_approve_reviews}
                    onCheckedChange={(checked) =>
                      setFormData((p) => ({ ...p, auto_approve_reviews: checked }))
                    }
                  />
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving || !formData.id || !formData.working_dir}>
              {isSaving ? 'Saving...' : isEdit ? 'Save Changes' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

**Step 2: Integrate modal into SettingsProfilesPage**

Update `SettingsProfilesPage.tsx` to add modal state and handlers.

**Step 3: Commit**

```bash
git add dashboard/src/components/settings/ProfileEditModal.tsx dashboard/src/pages/SettingsProfilesPage.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): add profile create/edit modal

Modal with:
- Basic settings: name, driver, model, working_dir
- Collapsible advanced section
- Reuses WorktreePathField component

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5: Cleanup

### Task 5.1: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update documentation**

Remove YAML configuration references and update env var table to bootstrap-only:

```markdown
### Server Configuration

Bootstrap settings via environment variables (prefix `AMELIA_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `AMELIA_HOST` | `127.0.0.1` | Host to bind the server to |
| `AMELIA_PORT` | `8420` | Port to bind the server to |
| `AMELIA_DATABASE_PATH` | `~/.amelia/amelia.db` | Path to SQLite database |

All other settings are managed via CLI or dashboard:

```bash
# Profile management
amelia config profile list
amelia config profile create
amelia config profile activate <name>

# Server settings
amelia config server show
amelia config server set <key> <value>
```
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: update CLAUDE.md for database config

- Remove YAML configuration references
- Update env var table to bootstrap-only
- Add amelia config command reference

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5.2: Delete Old Test Files

**Files:**
- Delete or update: `tests/unit/test_config.py`

**Step 1: Update tests**

Remove tests for deleted `load_settings` function. Keep any still-relevant tests.

**Step 2: Commit**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
test: clean up config tests for database migration

Removes tests for deleted YAML loading.

Part of #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5.3: Run Full Test Suite

**Step 1: Run Python tests**

Run: `uv run pytest`
Expected: All tests pass

**Step 2: Run type checks**

Run: `uv run mypy amelia`
Expected: No errors

**Step 3: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No errors

**Step 4: Run dashboard tests**

Run: `cd dashboard && pnpm test:run && pnpm lint && pnpm type-check`
Expected: All pass

**Step 5: Final commit**

```bash
git commit --allow-empty -m "$(cat <<'EOF'
chore: all tests pass for unified database config

Closes #307

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements the unified database configuration in 5 phases with ~20 tasks:

1. **Database Foundation** - Schema + repositories
2. **Backend Migration** - ServerConfig strip + API routes + orchestrator update
3. **CLI Commands** - `amelia config` with first-run setup
4. **Dashboard UI** - Settings pages with profile/server management
5. **Cleanup** - Docs + test updates

Each task follows TDD with explicit test→implement→commit steps.

---

Plan complete and saved to `docs/plans/2026-01-21-unified-database-config-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
