"""Repository for profile management."""

import json
from datetime import datetime

import aiosqlite
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
            "SELECT * FROM profiles WHERE id = ?",
            (profile_id,),
        )
        return self._row_to_profile(row) if row else None

    async def get_active_profile(self) -> Profile | None:
        """Get the currently active profile.

        Returns:
            Active profile if one is set, None otherwise.
        """
        row = await self._db.fetch_one("SELECT * FROM profiles WHERE is_active = 1")
        return self._row_to_profile(row) if row else None

    async def create_profile(self, profile: Profile) -> Profile:
        """Create a new profile in the database.

        Args:
            profile: Profile to create.

        Returns:
            Created profile.

        Raises:
            sqlite3.IntegrityError: If profile name already exists.
        """
        agents_json = json.dumps({
            name: {
                "driver": config.driver,
                "model": config.model,
                "options": config.options,
            }
            for name, config in profile.agents.items()
        })

        await self._db.execute(
            """INSERT INTO profiles (
                id, tracker, working_dir, plan_output_dir, plan_path_pattern,
                agents, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                profile.name,
                profile.tracker,
                profile.working_dir,
                profile.plan_output_dir,
                profile.plan_path_pattern,
                agents_json,
                0,
            ),
        )
        result = await self.get_profile(profile.name)
        # Result should never be None since we just inserted it
        assert result is not None
        return result

    async def update_profile(
        self, profile_id: str, updates: dict[str, str | int | bool]
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

        # Convert booleans to integers for SQLite
        db_updates: dict[str, str | int] = {}
        for k, v in updates.items():
            if isinstance(v, bool):
                db_updates[k] = 1 if v else 0
            else:
                db_updates[k] = v

        set_clauses = [f"{k} = ?" for k in db_updates]
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values: list[str | int] = list(db_updates.values())
        values.append(profile_id)

        rows_affected = await self._db.execute(
            f"UPDATE profiles SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        if rows_affected == 0:
            raise ValueError(f"Profile not found: {profile_id}")

        result = await self.get_profile(profile_id)
        # Result should never be None since we just updated it
        assert result is not None
        return result

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

    def _row_to_profile(self, row: aiosqlite.Row) -> Profile:
        """Convert a database row to a Profile object.

        Args:
            row: Database row from profiles table.

        Returns:
            Profile instance.
        """
        agents_data = json.loads(row["agents"])
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
