"""Tests for PR auto-fix database persistence.

Tests profile repository pr_autofix serialization/deserialization
and server settings pr_polling_enabled field.
"""

import pytest

from amelia.core.types import (
    AgentConfig,
    AggressivenessLevel,
    PRAutoFixConfig,
    Profile,
)
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.settings_repository import ServerSettings, SettingsRepository


def _make_agents() -> dict[str, AgentConfig]:
    """Create minimal agents dict for Profile."""
    return {
        "architect": AgentConfig(driver="claude", model="opus"),
        "developer": AgentConfig(driver="claude", model="opus"),
        "reviewer": AgentConfig(driver="claude", model="haiku"),
    }


def _make_mock_row(pr_autofix: dict | None = None) -> dict:
    return {
        "id": "test",
        "tracker": "noop",
        "repo_root": "/tmp/test",
        "plan_output_dir": "docs/plans",
        "plan_path_pattern": "docs/plans/{date}-{issue_key}.md",
        "agents": {
            "architect": {"driver": "claude", "model": "opus", "options": {}},
            "developer": {"driver": "claude", "model": "opus", "options": {}},
            "reviewer": {"driver": "claude", "model": "haiku", "options": {}},
        },
        "pr_autofix": pr_autofix,
        "is_active": False,
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }


def _make_profile(**overrides) -> Profile:
    defaults = {
        "tracker": "noop",
        "repo_root": "/tmp/test",
        "agents": _make_agents(),
    }
    return Profile(**(defaults | overrides))


# --- Unit tests (no database required) ---


def test_row_to_profile_with_pr_autofix():
    """_row_to_profile should deserialize pr_autofix JSONB."""
    mock_row = _make_mock_row(pr_autofix={
        "aggressiveness": "thorough",
        "poll_interval": 90,
        "auto_resolve": True,
        "max_iterations": 2,
        "commit_prefix": "fix(review):",
    })

    repo = ProfileRepository.__new__(ProfileRepository)
    profile = repo._row_to_profile(mock_row)
    assert profile.pr_autofix is not None
    assert profile.pr_autofix.aggressiveness == AggressivenessLevel.THOROUGH
    assert profile.pr_autofix.poll_interval == 90


def test_row_to_profile_with_null_pr_autofix():
    """_row_to_profile should return None for null pr_autofix."""
    mock_row = _make_mock_row()

    repo = ProfileRepository.__new__(ProfileRepository)
    profile = repo._row_to_profile(mock_row)
    assert profile.pr_autofix is None


def test_server_settings_model_has_pr_polling_enabled():
    """ServerSettings Pydantic model should include pr_polling_enabled."""
    assert "pr_polling_enabled" in ServerSettings.model_fields


# --- Integration tests (require database) ---


@pytest.fixture
async def db(db_with_schema: Database) -> Database:
    return db_with_schema


@pytest.fixture
def profile_repo(db: Database) -> ProfileRepository:
    return ProfileRepository(db)


@pytest.fixture
def settings_repo(db: Database) -> SettingsRepository:
    return SettingsRepository(db)


@pytest.mark.integration
class TestProfilePRAutoFixPersistence:
    """Tests for pr_autofix column in profiles table."""

    async def test_create_profile_without_pr_autofix(self, profile_repo: ProfileRepository):
        """Profile created without pr_autofix should have None."""
        profile = _make_profile(name="no-autofix")
        created = await profile_repo.create_profile(profile)
        assert created.pr_autofix is None

    async def test_create_profile_with_pr_autofix(self, profile_repo: ProfileRepository):
        """Profile created with pr_autofix should round-trip config."""
        config = PRAutoFixConfig(
            aggressiveness=AggressivenessLevel.THOROUGH,
            poll_interval=120,
            auto_resolve=False,
            max_iterations=5,
            commit_prefix="autofix:",
        )
        profile = _make_profile(name="with-autofix", pr_autofix=config)
        created = await profile_repo.create_profile(profile)
        assert created.pr_autofix is not None
        assert created.pr_autofix.aggressiveness == AggressivenessLevel.THOROUGH
        assert created.pr_autofix.poll_interval == 120
        assert created.pr_autofix.auto_resolve is False
        assert created.pr_autofix.max_iterations == 5
        assert created.pr_autofix.commit_prefix == "autofix:"

    async def test_create_profile_with_default_pr_autofix(self, profile_repo: ProfileRepository):
        """Profile with default PRAutoFixConfig should round-trip defaults."""
        profile = _make_profile(name="default-autofix", pr_autofix=PRAutoFixConfig())
        created = await profile_repo.create_profile(profile)
        assert created.pr_autofix is not None
        assert created.pr_autofix.aggressiveness == AggressivenessLevel.STANDARD
        assert created.pr_autofix.poll_interval == 60
        assert created.pr_autofix.auto_resolve is True
        assert created.pr_autofix.max_iterations == 3

    async def test_get_profile_round_trips_pr_autofix(self, profile_repo: ProfileRepository):
        """pr_autofix should survive create -> get round trip."""
        config = PRAutoFixConfig(aggressiveness=AggressivenessLevel.CRITICAL)
        profile = _make_profile(name="roundtrip", pr_autofix=config)
        await profile_repo.create_profile(profile)
        retrieved = await profile_repo.get_profile("roundtrip")
        assert retrieved is not None
        assert retrieved.pr_autofix is not None
        assert retrieved.pr_autofix.aggressiveness == AggressivenessLevel.CRITICAL

    async def test_update_profile_pr_autofix(self, profile_repo: ProfileRepository):
        """update_profile should accept pr_autofix in valid_fields."""
        profile = _make_profile(name="update-test")
        await profile_repo.create_profile(profile)

        config = PRAutoFixConfig(max_iterations=7)
        updated = await profile_repo.update_profile(
            "update-test",
            {"pr_autofix": config.model_dump()},
        )
        assert updated.pr_autofix is not None
        assert updated.pr_autofix.max_iterations == 7

    async def test_update_profile_pr_autofix_to_none(self, profile_repo: ProfileRepository):
        """Setting pr_autofix to None should disable it."""
        profile = _make_profile(name="disable-test", pr_autofix=PRAutoFixConfig())
        await profile_repo.create_profile(profile)

        updated = await profile_repo.update_profile(
            "disable-test",
            {"pr_autofix": None},
        )
        assert updated.pr_autofix is None


@pytest.mark.integration
class TestServerSettingsPRPollingEnabled:
    """Tests for pr_polling_enabled in server settings."""

    async def test_server_settings_has_pr_polling_enabled(self, settings_repo: SettingsRepository):
        """ServerSettings should have pr_polling_enabled field."""
        await settings_repo.ensure_defaults()
        settings = await settings_repo.get_server_settings()
        assert isinstance(settings.pr_polling_enabled, bool)
        assert settings.pr_polling_enabled is False  # default

    async def test_update_pr_polling_enabled(self, settings_repo: SettingsRepository):
        """update_server_settings should accept pr_polling_enabled."""
        await settings_repo.ensure_defaults()
        settings = await settings_repo.update_server_settings({"pr_polling_enabled": True})
        assert settings.pr_polling_enabled is True

    async def test_pr_polling_enabled_round_trip(self, settings_repo: SettingsRepository):
        """pr_polling_enabled should survive update -> get round trip."""
        await settings_repo.ensure_defaults()
        await settings_repo.update_server_settings({"pr_polling_enabled": True})
        settings = await settings_repo.get_server_settings()
        assert settings.pr_polling_enabled is True
