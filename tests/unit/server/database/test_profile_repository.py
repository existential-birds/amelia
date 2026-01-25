"""Tests for ProfileRepository."""

import json

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRecord, ProfileRepository


def _make_agents_json(
    driver: str = "cli",
    model: str = "opus",
    validator_model: str = "haiku",
) -> str:
    """Create agents JSON blob for tests."""
    return json.dumps({
        "architect": {"driver": driver, "model": model, "options": {}},
        "developer": {"driver": driver, "model": model, "options": {}},
        "reviewer": {"driver": driver, "model": validator_model, "options": {}},
    })


def _make_agents(
    driver: str = "cli",
    model: str = "opus",
    validator_model: str = "haiku",
) -> dict[str, AgentConfig]:
    """Create agents dict for Profile."""
    return {
        "architect": AgentConfig(driver=driver, model=model),
        "developer": AgentConfig(driver=driver, model=model),
        "reviewer": AgentConfig(driver=driver, model=validator_model),
    }


def test_profile_record_with_agents_json():
    """ProfileRecord should store agents as JSON."""
    agents = {
        "architect": {"driver": "cli", "model": "opus", "options": {}},
        "developer": {"driver": "cli", "model": "sonnet", "options": {}},
    }

    record = ProfileRecord(
        id="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents=json.dumps(agents),
    )

    assert record.agents is not None
    parsed = json.loads(record.agents)
    assert parsed["architect"]["model"] == "opus"


def test_row_to_profile_parses_agents_json():
    """_row_to_profile should parse agents JSON into AgentConfig dict."""
    agents_json = json.dumps({
        "architect": {"driver": "cli", "model": "opus", "options": {}},
        "developer": {"driver": "cli", "model": "sonnet", "options": {}},
    })

    mock_row = {
        "id": "test",
        "tracker": "noop",
        "working_dir": "/tmp/test",
        "plan_output_dir": "docs/plans",
        "plan_path_pattern": "docs/plans/{date}-{issue_key}.md",
        "auto_approve_reviews": 0,
        "agents": agents_json,
        "is_active": 1,
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }

    repo = ProfileRepository.__new__(ProfileRepository)  # Skip __init__
    profile = repo._row_to_profile(mock_row)

    assert isinstance(profile, Profile)
    assert "architect" in profile.agents
    assert profile.agents["architect"].model == "opus"
    assert isinstance(profile.agents["architect"], AgentConfig)


@pytest.mark.asyncio
async def test_create_profile_stores_agents_json(temp_db_path):
    """create_profile should serialize agents dict to JSON."""
    async with Database(temp_db_path) as db:
        await db.ensure_schema()
        repo = ProfileRepository(db)

        profile = Profile(
            name="test_agents",
            tracker="noop",
            working_dir="/tmp/test",
            agents={
                "architect": AgentConfig(driver="cli", model="opus"),
                "developer": AgentConfig(driver="api", model="anthropic/claude-sonnet-4"),
            },
        )

        await repo.create_profile(profile)

        # Retrieve and verify
        retrieved = await repo.get_profile("test_agents")
        assert retrieved is not None
        assert retrieved.agents["architect"].model == "opus"
        assert retrieved.agents["developer"].driver == "api"


class TestProfileRepository:
    """Tests for ProfileRepository CRUD operations."""

    @pytest.fixture
    async def db(self, temp_db_path) -> Database:
        """Create database with schema."""
        async with Database(temp_db_path) as db:
            await db.ensure_schema()
            yield db

    @pytest.fixture
    def repo(self, db: Database) -> ProfileRepository:
        """Create a ProfileRepository instance."""
        return ProfileRepository(db)

    async def test_create_profile(self, repo: ProfileRepository):
        """Verify profile creation."""
        profile = await repo.create_profile(
            Profile(
                name="dev",
                tracker="noop",
                working_dir="/path/to/repo",
                agents=_make_agents(driver="cli", model="opus"),
            )
        )
        # Repository returns Profile (converted from DB)
        assert profile.name == "dev"
        assert profile.agents["architect"].driver == "cli"

    async def test_get_profile(self, repo: ProfileRepository):
        """Verify profile retrieval."""
        await repo.create_profile(
            Profile(
                name="dev",
                tracker="noop",
                working_dir="/path/to/repo",
                agents=_make_agents(model="opus"),
            )
        )
        profile = await repo.get_profile("dev")
        assert profile is not None
        assert profile.agents["architect"].model == "opus"

    async def test_get_profile_not_found(self, repo: ProfileRepository):
        """Verify None returned for missing profile."""
        profile = await repo.get_profile("nonexistent")
        assert profile is None

    async def test_list_profiles(self, repo: ProfileRepository):
        """Verify listing all profiles."""
        await repo.create_profile(
            Profile(
                name="dev",
                tracker="noop",
                working_dir="/repo1",
                agents=_make_agents(driver="cli", model="opus"),
            )
        )
        await repo.create_profile(
            Profile(
                name="prod",
                tracker="jira",
                working_dir="/repo2",
                agents=_make_agents(driver="api", model="gpt-4"),
            )
        )
        profiles = await repo.list_profiles()
        assert len(profiles) == 2
        names = {p.name for p in profiles}
        assert names == {"dev", "prod"}

    async def test_update_profile(self, repo: ProfileRepository):
        """Verify profile updates."""
        await repo.create_profile(
            Profile(
                name="dev",
                tracker="noop",
                working_dir="/repo",
                agents=_make_agents(model="opus"),
            )
        )
        # update_profile still accepts JSON string for agents
        new_agents = _make_agents_json(model="sonnet")
        updated = await repo.update_profile("dev", {"agents": new_agents})
        assert updated.agents["architect"].model == "sonnet"

        # Verify persistence
        fetched = await repo.get_profile("dev")
        assert fetched.agents["architect"].model == "sonnet"

    async def test_delete_profile(self, repo: ProfileRepository):
        """Verify profile deletion."""
        await repo.create_profile(
            Profile(
                name="dev",
                tracker="noop",
                working_dir="/repo",
                agents=_make_agents(),
            )
        )
        result = await repo.delete_profile("dev")
        assert result is True
        assert await repo.get_profile("dev") is None

    async def test_delete_profile_not_found(self, repo: ProfileRepository):
        """Verify delete returns False for missing profile."""
        result = await repo.delete_profile("nonexistent")
        assert result is False

    async def test_set_active(self, repo: ProfileRepository):
        """Verify setting active profile."""
        await repo.create_profile(
            Profile(
                name="dev",
                tracker="noop",
                working_dir="/repo",
                agents=_make_agents(),
            )
        )
        await repo.set_active("dev")
        # Note: Profile doesn't have is_active field - we verify via get_active_profile
        active = await repo.get_active_profile()
        assert active is not None
        assert active.name == "dev"

    async def test_set_active_deactivates_others(self, repo: ProfileRepository):
        """Verify setting active profile deactivates others."""
        await repo.create_profile(
            Profile(
                name="dev",
                tracker="noop",
                working_dir="/repo1",
                agents=_make_agents(driver="cli", model="opus"),
            )
        )
        await repo.create_profile(
            Profile(
                name="prod",
                tracker="jira",
                working_dir="/repo2",
                agents=_make_agents(driver="api", model="gpt-4"),
            )
        )
        await repo.set_active("dev")
        await repo.set_active("prod")

        # Only prod should be active now
        active = await repo.get_active_profile()
        assert active is not None
        assert active.name == "prod"

    async def test_get_active_profile(self, repo: ProfileRepository):
        """Verify getting the active profile."""
        await repo.create_profile(
            Profile(
                name="dev",
                tracker="noop",
                working_dir="/repo",
                agents=_make_agents(),
            )
        )
        await repo.set_active("dev")
        active = await repo.get_active_profile()
        assert active is not None
        assert active.name == "dev"

    async def test_get_active_profile_none(self, repo: ProfileRepository):
        """Verify None when no active profile."""
        active = await repo.get_active_profile()
        assert active is None
