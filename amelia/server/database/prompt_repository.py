# amelia/server/database/prompt_repository.py
"""Repository for prompt configuration persistence.

Provides CRUD operations for prompts, versions, and workflow linking.
"""
import uuid
from datetime import UTC, datetime

from amelia.agents.prompts.models import (
    Prompt,
    PromptVersion,
    WorkflowPromptVersion,
)
from amelia.server.database.connection import Database


class PromptRepository:
    """Repository for prompt configuration database operations.

    Attributes:
        _db: Database connection wrapper.
    """

    def __init__(self, db: Database) -> None:
        """Initialize repository with database connection.

        Args:
            db: Database connection wrapper.
        """
        self._db = db

    # Prompt CRUD

    async def create_prompt(self, prompt: Prompt) -> None:
        """Create a new prompt definition.

        Args:
            prompt: The prompt to create.
        """
        await self._db.execute(
            """INSERT INTO prompts (id, agent, name, description, current_version_id)
               VALUES (?, ?, ?, ?, ?)""",
            (prompt.id, prompt.agent, prompt.name, prompt.description, prompt.current_version_id),
        )

    async def list_prompts(self) -> list[Prompt]:
        """List all prompt definitions.

        Returns:
            List of all prompts.
        """
        rows = await self._db.fetch_all("SELECT * FROM prompts ORDER BY agent, name")
        return [
            Prompt(
                id=row["id"],
                agent=row["agent"],
                name=row["name"],
                description=row["description"],
                current_version_id=row["current_version_id"],
            )
            for row in rows
        ]

    async def get_prompt(self, prompt_id: str) -> Prompt | None:
        """Get a prompt by ID.

        Args:
            prompt_id: The prompt identifier.

        Returns:
            The prompt if found, None otherwise.
        """
        row = await self._db.fetch_one(
            "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
        )
        if not row:
            return None
        return Prompt(
            id=row["id"],
            agent=row["agent"],
            name=row["name"],
            description=row["description"],
            current_version_id=row["current_version_id"],
        )

    # Version management

    async def get_versions(self, prompt_id: str) -> list[PromptVersion]:
        """Get all versions for a prompt, newest first.

        Args:
            prompt_id: The prompt identifier.

        Returns:
            List of versions ordered by version_number descending.
        """
        rows = await self._db.fetch_all(
            """SELECT * FROM prompt_versions
               WHERE prompt_id = ?
               ORDER BY version_number DESC""",
            (prompt_id,),
        )
        return [
            PromptVersion(
                id=row["id"],
                prompt_id=row["prompt_id"],
                version_number=row["version_number"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(UTC),
                change_note=row["change_note"],
            )
            for row in rows
        ]

    async def get_version(self, version_id: str) -> PromptVersion | None:
        """Get a specific version by ID.

        Args:
            version_id: The version identifier.

        Returns:
            The version if found, None otherwise.
        """
        row = await self._db.fetch_one(
            "SELECT * FROM prompt_versions WHERE id = ?", (version_id,)
        )
        if not row:
            return None
        return PromptVersion(
            id=row["id"],
            prompt_id=row["prompt_id"],
            version_number=row["version_number"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(UTC),
            change_note=row["change_note"],
        )

    async def create_version(
        self,
        prompt_id: str,
        content: str,
        change_note: str | None,
    ) -> PromptVersion:
        """Create a new version and set it as active.

        Args:
            prompt_id: The prompt identifier.
            content: The prompt content.
            change_note: Optional note describing the change.

        Returns:
            The created version.
        """
        # Get next version number
        row = await self._db.fetch_one(
            "SELECT MAX(version_number) as max_version FROM prompt_versions WHERE prompt_id = ?",
            (prompt_id,),
        )
        next_version = (row["max_version"] or 0) + 1 if row else 1

        # Create version
        version_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        await self._db.execute(
            """INSERT INTO prompt_versions (id, prompt_id, version_number, content, created_at, change_note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (version_id, prompt_id, next_version, content, now.isoformat(), change_note),
        )

        # Set as active
        await self._db.execute(
            "UPDATE prompts SET current_version_id = ? WHERE id = ?",
            (version_id, prompt_id),
        )

        return PromptVersion(
            id=version_id,
            prompt_id=prompt_id,
            version_number=next_version,
            content=content,
            created_at=now,
            change_note=change_note,
        )

    async def set_active_version(self, prompt_id: str, version_id: str) -> None:
        """Set the active version for a prompt.

        Args:
            prompt_id: The prompt identifier.
            version_id: The version to make active.
        """
        await self._db.execute(
            "UPDATE prompts SET current_version_id = ? WHERE id = ?",
            (version_id, prompt_id),
        )

    async def reset_to_default(self, prompt_id: str) -> None:
        """Reset prompt to use hardcoded default.

        Args:
            prompt_id: The prompt identifier.
        """
        await self._db.execute(
            "UPDATE prompts SET current_version_id = NULL WHERE id = ?",
            (prompt_id,),
        )

    # Workflow linking

    async def record_workflow_prompt(
        self,
        workflow_id: str,
        prompt_id: str,
        version_id: str,
    ) -> None:
        """Record which prompt version a workflow used.

        Args:
            workflow_id: The workflow identifier.
            prompt_id: The prompt identifier.
            version_id: The version identifier.
        """
        await self._db.execute(
            """INSERT OR REPLACE INTO workflow_prompt_versions (workflow_id, prompt_id, version_id)
               VALUES (?, ?, ?)""",
            (workflow_id, prompt_id, version_id),
        )

    async def get_workflow_prompts(self, workflow_id: str) -> list[WorkflowPromptVersion]:
        """Get all prompt versions used by a workflow.

        Args:
            workflow_id: The workflow identifier.

        Returns:
            List of workflow-prompt-version links.
        """
        rows = await self._db.fetch_all(
            "SELECT * FROM workflow_prompt_versions WHERE workflow_id = ?",
            (workflow_id,),
        )
        return [
            WorkflowPromptVersion(
                workflow_id=row["workflow_id"],
                prompt_id=row["prompt_id"],
                version_id=row["version_id"],
            )
            for row in rows
        ]
