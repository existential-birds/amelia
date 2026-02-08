"""Repository for brainstorming session operations.

Handles persistence and retrieval of brainstorming sessions,
messages, and artifacts.
"""

import asyncpg

from amelia.server.database.connection import Database
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    MessagePart,
    MessageUsage,
    SessionStatus,
    SessionUsageSummary,
)


class BrainstormRepository:
    """Repository for brainstorming CRUD operations.

    Handles persistence and retrieval of brainstorming sessions,
    messages, and artifacts.

    Attributes:
        _db: Database connection.
    """

    def __init__(self, db: Database) -> None:
        """Initialize repository.

        Args:
            db: Database connection.
        """
        self._db = db

    # =========================================================================
    # Session Operations
    # =========================================================================

    async def create_session(self, session: BrainstormingSession) -> None:
        """Create a new brainstorming session.

        Args:
            session: Session to create.
        """
        await self._db.execute(
            """
            INSERT INTO brainstorm_sessions (
                id, profile_id, driver_session_id, driver_type, status, topic,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            session.id,
            session.profile_id,
            session.driver_session_id,
            session.driver_type,
            session.status,
            session.topic,
            session.created_at,
            session.updated_at,
        )

    async def get_session(self, session_id: str) -> BrainstormingSession | None:
        """Get session by ID.

        Args:
            session_id: Session identifier.

        Returns:
            Session or None if not found.
        """
        row = await self._db.fetch_one(
            """
            SELECT id, profile_id, driver_session_id, driver_type, status, topic,
                   created_at, updated_at
            FROM brainstorm_sessions WHERE id = $1
            """,
            session_id,
        )
        if row is None:
            return None
        return self._row_to_session(row)

    async def update_session(self, session: BrainstormingSession) -> None:
        """Update session.

        Args:
            session: Updated session.
        """
        await self._db.execute(
            """
            UPDATE brainstorm_sessions SET
                driver_session_id = $1,
                driver_type = $2,
                status = $3,
                topic = $4,
                updated_at = $5
            WHERE id = $6
            """,
            session.driver_session_id,
            session.driver_type,
            session.status,
            session.topic,
            session.updated_at,
            session.id,
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete session.

        Args:
            session_id: Session to delete.
        """
        await self._db.execute(
            "DELETE FROM brainstorm_sessions WHERE id = $1",
            session_id,
        )

    async def list_sessions(
        self,
        profile_id: str | None = None,
        status: SessionStatus | None = None,
        limit: int = 50,
    ) -> list[BrainstormingSession]:
        """List sessions with optional filters.

        Args:
            profile_id: Filter by profile.
            status: Filter by status.
            limit: Maximum sessions to return.

        Returns:
            List of sessions.
        """
        conditions = []
        params: list[str | int] = []
        param_idx = 1

        if profile_id:
            conditions.append(f"profile_id = ${param_idx}")
            params.append(profile_id)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        rows = await self._db.fetch_all(
            f"""
            SELECT id, profile_id, driver_session_id, driver_type, status, topic,
                   created_at, updated_at
            FROM brainstorm_sessions
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT ${param_idx}
            """,
            *params,
        )
        return [self._row_to_session(row) for row in rows]

    def _row_to_session(self, row: asyncpg.Record) -> BrainstormingSession:
        """Convert database row to BrainstormingSession.

        Args:
            row: Database row.

        Returns:
            BrainstormingSession instance.
        """
        return BrainstormingSession(
            id=row["id"],
            profile_id=row["profile_id"],
            driver_session_id=row["driver_session_id"],
            driver_type=row["driver_type"],
            status=row["status"],
            topic=row["topic"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # =========================================================================
    # Message Operations
    # =========================================================================

    async def save_message(self, message: Message) -> None:
        """Save a message.

        Args:
            message: Message to save.
        """
        parts_data = None
        if message.parts:
            parts_data = [p.model_dump() for p in message.parts]

        # Extract usage fields if present
        input_tokens = message.usage.input_tokens if message.usage else None
        output_tokens = message.usage.output_tokens if message.usage else None
        cost_usd = message.usage.cost_usd if message.usage else None

        await self._db.execute(
            """
            INSERT INTO brainstorm_messages (
                id, session_id, sequence, role, content, parts, created_at,
                input_tokens, output_tokens, cost_usd
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            message.id,
            message.session_id,
            message.sequence,
            message.role,
            message.content,
            parts_data,
            message.created_at,
            input_tokens,
            output_tokens,
            cost_usd,
        )

    async def get_messages(
        self, session_id: str, limit: int = 100
    ) -> list[Message]:
        """Get messages for a session.

        Args:
            session_id: Session to get messages for.
            limit: Maximum messages to return.

        Returns:
            List of messages in sequence order.
        """
        rows = await self._db.fetch_all(
            """
            SELECT id, session_id, sequence, role, content, parts, created_at,
                   input_tokens, output_tokens, cost_usd
            FROM brainstorm_messages
            WHERE session_id = $1
            ORDER BY sequence ASC
            LIMIT $2
            """,
            session_id,
            limit,
        )
        return [self._row_to_message(row) for row in rows]

    async def get_max_sequence(self, session_id: str) -> int:
        """Get maximum message sequence for a session.

        Args:
            session_id: Session ID.

        Returns:
            Maximum sequence number, or 0 if no messages.
        """
        result = await self._db.fetch_scalar(
            "SELECT COALESCE(MAX(sequence), 0) FROM brainstorm_messages WHERE session_id = $1",
            session_id,
        )
        return result if isinstance(result, int) else 0

    def _row_to_message(self, row: asyncpg.Record) -> Message:
        """Convert database row to Message.

        Args:
            row: Database row.

        Returns:
            Message instance.
        """
        parts = None
        if row["parts"]:
            # JSONB codec returns list directly
            parts = [MessagePart(**p) for p in row["parts"]]

        # Load usage if present
        usage = None
        if row["input_tokens"] is not None:
            usage = MessageUsage(
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"] or 0,
                cost_usd=float(row["cost_usd"]) if row["cost_usd"] else 0.0,
            )

        return Message(
            id=row["id"],
            session_id=row["session_id"],
            sequence=row["sequence"],
            role=row["role"],
            content=row["content"],
            parts=parts,
            usage=usage,
            created_at=row["created_at"],
        )

    # =========================================================================
    # Artifact Operations
    # =========================================================================

    async def save_artifact(self, artifact: Artifact) -> None:
        """Save an artifact.

        Args:
            artifact: Artifact to save.
        """
        await self._db.execute(
            """
            INSERT INTO brainstorm_artifacts (
                id, session_id, type, path, title, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            artifact.id, artifact.session_id, artifact.type, artifact.path, artifact.title, artifact.created_at,
        )

    async def get_artifacts(self, session_id: str) -> list[Artifact]:
        """Get artifacts for a session.

        Args:
            session_id: Session ID.

        Returns:
            List of artifacts.
        """
        rows = await self._db.fetch_all(
            """
            SELECT id, session_id, type, path, title, created_at
            FROM brainstorm_artifacts
            WHERE session_id = $1
            ORDER BY created_at ASC
            """,
            session_id,
        )
        return [self._row_to_artifact(row) for row in rows]

    def _row_to_artifact(self, row: asyncpg.Record) -> Artifact:
        """Convert database row to Artifact.

        Args:
            row: Database row.

        Returns:
            Artifact instance.
        """
        return Artifact(
            id=row["id"],
            session_id=row["session_id"],
            type=row["type"],
            path=row["path"],
            title=row["title"],
            created_at=row["created_at"],
        )

    # =========================================================================
    # Usage Aggregation
    # =========================================================================

    async def get_session_usage(self, session_id: str) -> SessionUsageSummary | None:
        """Aggregate token usage for all messages in a brainstorm session.

        Args:
            session_id: Session to aggregate usage for.

        Returns:
            SessionUsageSummary with totals, or None if no messages have usage data.
        """
        row = await self._db.fetch_one(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(cost_usd), 0.0) as total_cost_usd,
                COUNT(*) as message_count
            FROM brainstorm_messages
            WHERE session_id = $1 AND input_tokens IS NOT NULL
            """,
            session_id,
        )

        if row is None or row["message_count"] == 0:
            return None

        return SessionUsageSummary(
            total_input_tokens=row["total_input_tokens"],
            total_output_tokens=row["total_output_tokens"],
            total_cost_usd=row["total_cost_usd"],
            message_count=row["message_count"],
        )
