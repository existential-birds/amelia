"""Repository for profile management."""

from datetime import datetime
from typing import Any

import asyncpg
from pydantic import BaseModel

from amelia.core.types import AgentConfig, Profile
from amelia.server.database.connection import Database


class ProfileRecord(BaseModel):
    """Profile data record for database operations.

    This is a database-level representation. Use amelia.core.types.Profile
    for application-level profile operations.
    """

    id: str
    tracker: str
    working_dir: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    agents: str  # JSON blob of dict[str, AgentConfig]
    is_active: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProfileRepository:
    """Repository for profile CRUD operations."""

    def __init__(self, db: Database):
        """Initialize repository with database connection.

        Args:
            db: Database connection instance.
        """
        self._db = db

    async def list_profiles(self) -> list[Profile]:
        """List all profiles.

        Returns:
            List of all profiles, ordered by id.
        """
        rows = await self._db.fetch_all("SELECT * FROM profiles ORDER BY id")
        return [self._row_to_profile(row) for row in rows]

    async def get_profile(self, profile_id: str) -> Profile | None:
        """Get a profile by ID.

        Args:
            profile_id: Profile identifier.

        Returns:
            Profile if found, None otherwise.
        """
        row = await self._db.fetch_one(
            "SELECT * FROM profiles WHERE id = $1",
            profile_id,
        )
        return self._row_to_profile(row) if row else None

    async def get_active_profile(self) -> Profile | None:
        """Get the currently active profile.

        Returns:
            Active profile if one is set, None otherwise.
        """
        row = await self._db.fetch_one(
            "SELECT * FROM profiles WHERE is_active = TRUE"
        )
        return self._row_to_profile(row) if row else None

    async def create_profile(self, profile: Profile) -> Profile:
        """Create a new profile in the database.

        Args:
            profile: Profile to create.

        Returns:
            Created profile.

        Raises:
            asyncpg.UniqueViolationError: If profile name already exists.
        """
        agents_data = {
            name: {
                "driver": config.driver,
                "model": config.model,
                "options": config.options,
            }
            for name, config in profile.agents.items()
        }

        await self._db.execute(
            """INSERT INTO profiles (
                id, tracker, working_dir, plan_output_dir, plan_path_pattern,
                agents, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            profile.name,
            profile.tracker,
            profile.working_dir,
            profile.plan_output_dir,
            profile.plan_path_pattern,
            agents_data,
            False,
        )
        result = await self.get_profile(profile.name)
        if result is None:
            raise RuntimeError(f"Profile {profile.name} not found after insert")
        return result

    async def update_profile(
        self, profile_id: str, updates: dict[str, str | int | bool | dict[str, Any]]
    ) -> Profile:
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
            "tracker",
            "working_dir",
            "plan_output_dir",
            "plan_path_pattern",
            "agents",
        }
        invalid = set(updates.keys()) - valid_fields
        if invalid:
            raise ValueError(f"Invalid profile fields: {invalid}")

        if not updates:
            profile = await self.get_profile(profile_id)
            if profile is None:
                raise ValueError(f"Profile not found: {profile_id}")
            return profile

        set_clauses: list[str] = []
        values: list[str | int | bool | dict[str, Any]] = []
        for i, (k, v) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{k} = ${i}")
            values.append(v)
        set_clauses.append("updated_at = NOW()")

        id_param = len(values) + 1
        rows_affected = await self._db.execute(
            f"UPDATE profiles SET {', '.join(set_clauses)} WHERE id = ${id_param}",
            *values,
            profile_id,
        )
        if rows_affected == 0:
            raise ValueError(f"Profile not found: {profile_id}")

        result = await self.get_profile(profile_id)
        if result is None:
            raise RuntimeError(f"Profile {profile_id} not found after update")
        return result

    async def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile.

        Args:
            profile_id: Profile to delete.

        Returns:
            True if deleted, False if not found.
        """
        rows_affected = await self._db.execute(
            "DELETE FROM profiles WHERE id = $1",
            profile_id,
        )
        return rows_affected > 0

    async def set_active(self, profile_id: str) -> None:
        """Set a profile as active, deactivating all others.

        Uses a transaction to atomically deactivate all profiles
        and activate the target profile.

        Args:
            profile_id: Profile to activate.

        Raises:
            ValueError: If profile not found.
        """
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE profiles SET is_active = FALSE WHERE is_active = TRUE"
            )
            result = await conn.execute(
                "UPDATE profiles SET is_active = TRUE, updated_at = NOW() WHERE id = $1",
                profile_id,
            )
            try:
                rows_affected = int(result.split()[-1])
            except (ValueError, IndexError, AttributeError):
                rows_affected = 0
            if rows_affected == 0:
                raise ValueError(f"Profile not found: {profile_id}")

    def _row_to_profile(self, row: asyncpg.Record) -> Profile:
        """Convert a database row to a Profile object.

        Args:
            row: Database row from profiles table.

        Returns:
            Profile instance.
        """
        # JSONB codec returns dict directly
        agents_data = row["agents"]
        agents = {
            name: AgentConfig(**config) for name, config in agents_data.items()
        }

        return Profile(
            name=row["id"],
            tracker=row["tracker"],
            working_dir=row["working_dir"],
            plan_output_dir=row["plan_output_dir"],
            plan_path_pattern=row["plan_path_pattern"],
            agents=agents,
        )
