"""Tests for ProfileRepository."""

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRecord, ProfileRepository


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
            ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/path/to/repo",
            )
        )
        assert profile.id == "dev"
        assert profile.driver == "cli:claude"
        assert profile.is_active is False

    async def test_get_profile(self, repo: ProfileRepository):
        """Verify profile retrieval."""
        await repo.create_profile(
            ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/path/to/repo",
            )
        )
        profile = await repo.get_profile("dev")
        assert profile is not None
        assert profile.model == "opus"

    async def test_get_profile_not_found(self, repo: ProfileRepository):
        """Verify None returned for missing profile."""
        profile = await repo.get_profile("nonexistent")
        assert profile is None

    async def test_list_profiles(self, repo: ProfileRepository):
        """Verify listing all profiles."""
        await repo.create_profile(
            ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/repo1",
            )
        )
        await repo.create_profile(
            ProfileRecord(
                id="prod",
                driver="api:openrouter",
                model="gpt-4",
                validator_model="haiku",
                tracker="jira",
                working_dir="/repo2",
            )
        )
        profiles = await repo.list_profiles()
        assert len(profiles) == 2
        ids = {p.id for p in profiles}
        assert ids == {"dev", "prod"}

    async def test_update_profile(self, repo: ProfileRepository):
        """Verify profile updates."""
        await repo.create_profile(
            ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/repo",
            )
        )
        updated = await repo.update_profile("dev", {"model": "sonnet"})
        assert updated.model == "sonnet"

        # Verify persistence
        fetched = await repo.get_profile("dev")
        assert fetched.model == "sonnet"

    async def test_delete_profile(self, repo: ProfileRepository):
        """Verify profile deletion."""
        await repo.create_profile(
            ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/repo",
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
            ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/repo",
            )
        )
        await repo.set_active("dev")
        profile = await repo.get_profile("dev")
        assert profile.is_active is True

    async def test_set_active_deactivates_others(self, repo: ProfileRepository):
        """Verify setting active profile deactivates others."""
        await repo.create_profile(
            ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/repo1",
            )
        )
        await repo.create_profile(
            ProfileRecord(
                id="prod",
                driver="api:openrouter",
                model="gpt-4",
                validator_model="haiku",
                tracker="jira",
                working_dir="/repo2",
            )
        )
        await repo.set_active("dev")
        await repo.set_active("prod")

        dev = await repo.get_profile("dev")
        prod = await repo.get_profile("prod")
        assert dev.is_active is False
        assert prod.is_active is True

    async def test_get_active_profile(self, repo: ProfileRepository):
        """Verify getting the active profile."""
        await repo.create_profile(
            ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/repo",
            )
        )
        await repo.set_active("dev")
        active = await repo.get_active_profile()
        assert active is not None
        assert active.id == "dev"

    async def test_get_active_profile_none(self, repo: ProfileRepository):
        """Verify None when no active profile."""
        active = await repo.get_active_profile()
        assert active is None
