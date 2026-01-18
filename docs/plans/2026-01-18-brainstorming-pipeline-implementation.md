# Brainstorming Pipeline Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the backend for a chat-based brainstorming system where users collaborate with an AI agent to produce design documents.

**Architecture:** Direct chat sessions with Claude CLI driver using session continuity (NOT LangGraph). FastAPI endpoints for session management, WebSocket for streaming via existing `/ws/events` infrastructure, SQLite for persistence.

**Tech Stack:** FastAPI (endpoints), WebSocket (streaming), Claude CLI driver (`execute_agentic` with `session_id`), SQLite (new tables), Pydantic (models).

---

## Phase 2a: Backend Foundation

### Task 1: Add Brainstorming Event Types

**Files:**
- Modify: `amelia/server/models/events.py:23-97` (EventType class)

**Step 1: Write the failing test**

Create `tests/unit/server/models/test_brainstorm_events.py`:

```python
"""Tests for brainstorming event types."""

import pytest

from amelia.server.models.events import EventType


class TestBrainstormEventTypes:
    """Test brainstorming event types exist."""

    def test_brainstorm_session_created_exists(self) -> None:
        """EventType should include BRAINSTORM_SESSION_CREATED."""
        assert hasattr(EventType, "BRAINSTORM_SESSION_CREATED")
        assert EventType.BRAINSTORM_SESSION_CREATED == "brainstorm_session_created"

    def test_brainstorm_reasoning_exists(self) -> None:
        """EventType should include BRAINSTORM_REASONING."""
        assert hasattr(EventType, "BRAINSTORM_REASONING")
        assert EventType.BRAINSTORM_REASONING == "brainstorm_reasoning"

    def test_brainstorm_tool_call_exists(self) -> None:
        """EventType should include BRAINSTORM_TOOL_CALL."""
        assert hasattr(EventType, "BRAINSTORM_TOOL_CALL")
        assert EventType.BRAINSTORM_TOOL_CALL == "brainstorm_tool_call"

    def test_brainstorm_tool_result_exists(self) -> None:
        """EventType should include BRAINSTORM_TOOL_RESULT."""
        assert hasattr(EventType, "BRAINSTORM_TOOL_RESULT")
        assert EventType.BRAINSTORM_TOOL_RESULT == "brainstorm_tool_result"

    def test_brainstorm_text_exists(self) -> None:
        """EventType should include BRAINSTORM_TEXT."""
        assert hasattr(EventType, "BRAINSTORM_TEXT")
        assert EventType.BRAINSTORM_TEXT == "brainstorm_text"

    def test_brainstorm_message_complete_exists(self) -> None:
        """EventType should include BRAINSTORM_MESSAGE_COMPLETE."""
        assert hasattr(EventType, "BRAINSTORM_MESSAGE_COMPLETE")
        assert EventType.BRAINSTORM_MESSAGE_COMPLETE == "brainstorm_message_complete"

    def test_brainstorm_artifact_created_exists(self) -> None:
        """EventType should include BRAINSTORM_ARTIFACT_CREATED."""
        assert hasattr(EventType, "BRAINSTORM_ARTIFACT_CREATED")
        assert EventType.BRAINSTORM_ARTIFACT_CREATED == "brainstorm_artifact_created"

    def test_brainstorm_session_completed_exists(self) -> None:
        """EventType should include BRAINSTORM_SESSION_COMPLETED."""
        assert hasattr(EventType, "BRAINSTORM_SESSION_COMPLETED")
        assert EventType.BRAINSTORM_SESSION_COMPLETED == "brainstorm_session_completed"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_brainstorm_events.py -v`
Expected: FAIL with "AttributeError: type object 'EventType' has no attribute 'BRAINSTORM_SESSION_CREATED'"

**Step 3: Write minimal implementation**

In `amelia/server/models/events.py`, add to the `EventType` class after the existing `AGENT_OUTPUT` line:

```python
    # Brainstorming (chat-based design sessions)
    BRAINSTORM_SESSION_CREATED = "brainstorm_session_created"
    BRAINSTORM_REASONING = "brainstorm_reasoning"
    BRAINSTORM_TOOL_CALL = "brainstorm_tool_call"
    BRAINSTORM_TOOL_RESULT = "brainstorm_tool_result"
    BRAINSTORM_TEXT = "brainstorm_text"
    BRAINSTORM_MESSAGE_COMPLETE = "brainstorm_message_complete"
    BRAINSTORM_ARTIFACT_CREATED = "brainstorm_artifact_created"
    BRAINSTORM_SESSION_COMPLETED = "brainstorm_session_completed"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_brainstorm_events.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/events.py tests/unit/server/models/test_brainstorm_events.py
git commit -m "feat(brainstorm): add brainstorming event types"
```

---

### Task 2: Create Pydantic Models

**Files:**
- Create: `amelia/server/models/brainstorm.py`
- Modify: `amelia/server/models/__init__.py`

**Step 1: Write the failing test**

Create `tests/unit/server/models/test_brainstorm_models.py`:

```python
"""Tests for brainstorming Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    MessagePart,
    SessionStatus,
)


class TestSessionStatus:
    """Test SessionStatus literal type."""

    def test_valid_statuses(self) -> None:
        """SessionStatus should accept valid status values."""
        session = BrainstormingSession(
            id="test-id",
            profile_id="test-profile",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert session.status == "active"

        session.status = "ready_for_handoff"
        assert session.status == "ready_for_handoff"


class TestBrainstormingSession:
    """Test BrainstormingSession model."""

    def test_minimal_session(self) -> None:
        """Session should be created with minimal required fields."""
        now = datetime.now(UTC)
        session = BrainstormingSession(
            id="session-123",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )
        assert session.id == "session-123"
        assert session.profile_id == "work"
        assert session.status == "active"
        assert session.driver_session_id is None
        assert session.topic is None

    def test_full_session(self) -> None:
        """Session should be created with all fields."""
        now = datetime.now(UTC)
        session = BrainstormingSession(
            id="session-123",
            profile_id="work",
            driver_session_id="claude-sess-456",
            status="ready_for_handoff",
            topic="Design a caching layer",
            created_at=now,
            updated_at=now,
        )
        assert session.driver_session_id == "claude-sess-456"
        assert session.topic == "Design a caching layer"

    def test_invalid_status_rejected(self) -> None:
        """Invalid status should raise ValidationError."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            BrainstormingSession(
                id="session-123",
                profile_id="work",
                status="invalid_status",  # type: ignore[arg-type]
                created_at=now,
                updated_at=now,
            )


class TestMessagePart:
    """Test MessagePart model."""

    def test_text_part(self) -> None:
        """Text part should store text content."""
        part = MessagePart(type="text", text="Hello world")
        assert part.type == "text"
        assert part.text == "Hello world"

    def test_tool_call_part(self) -> None:
        """Tool call part should store tool details."""
        part = MessagePart(
            type="tool-call",
            tool_call_id="call-123",
            tool_name="read_file",
            args={"path": "/tmp/file.txt"},
        )
        assert part.type == "tool-call"
        assert part.tool_call_id == "call-123"
        assert part.tool_name == "read_file"
        assert part.args == {"path": "/tmp/file.txt"}

    def test_tool_result_part(self) -> None:
        """Tool result part should store result details."""
        part = MessagePart(
            type="tool-result",
            tool_call_id="call-123",
            result="file contents here",
        )
        assert part.type == "tool-result"
        assert part.tool_call_id == "call-123"
        assert part.result == "file contents here"

    def test_reasoning_part(self) -> None:
        """Reasoning part should store thinking content."""
        part = MessagePart(type="reasoning", text="Let me think about this...")
        assert part.type == "reasoning"
        assert part.text == "Let me think about this..."


class TestMessage:
    """Test Message model."""

    def test_user_message(self) -> None:
        """User message should be created correctly."""
        msg = Message(
            id="msg-123",
            session_id="session-456",
            sequence=1,
            role="user",
            content="Design a caching layer",
            created_at=datetime.now(UTC),
        )
        assert msg.role == "user"
        assert msg.content == "Design a caching layer"
        assert msg.parts is None

    def test_assistant_message_with_parts(self) -> None:
        """Assistant message should support parts."""
        msg = Message(
            id="msg-124",
            session_id="session-456",
            sequence=2,
            role="assistant",
            content="Here's my analysis...",
            parts=[
                MessagePart(type="reasoning", text="First, let me understand..."),
                MessagePart(type="text", text="Here's my analysis..."),
            ],
            created_at=datetime.now(UTC),
        )
        assert msg.role == "assistant"
        assert len(msg.parts) == 2
        assert msg.parts[0].type == "reasoning"


class TestArtifact:
    """Test Artifact model."""

    def test_artifact_creation(self) -> None:
        """Artifact should be created with all fields."""
        artifact = Artifact(
            id="art-123",
            session_id="session-456",
            type="design",
            path="docs/plans/2026-01-18-caching-design.md",
            title="Caching Layer Design",
            created_at=datetime.now(UTC),
        )
        assert artifact.id == "art-123"
        assert artifact.type == "design"
        assert artifact.path == "docs/plans/2026-01-18-caching-design.md"
        assert artifact.title == "Caching Layer Design"

    def test_artifact_without_title(self) -> None:
        """Artifact title should be optional."""
        artifact = Artifact(
            id="art-123",
            session_id="session-456",
            type="spec",
            path="docs/specs/feature.md",
            created_at=datetime.now(UTC),
        )
        assert artifact.title is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_brainstorm_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.server.models.brainstorm'"

**Step 3: Write minimal implementation**

Create `amelia/server/models/brainstorm.py`:

```python
"""Pydantic models for brainstorming sessions.

These models support the chat-based brainstorming system where users
collaborate with an AI agent to produce design documents.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

SessionStatus = Literal["active", "ready_for_handoff", "completed", "failed"]


class BrainstormingSession(BaseModel):
    """Tracks a brainstorming chat session.

    Attributes:
        id: Unique session identifier (UUID).
        profile_id: Which profile/project this session belongs to.
        driver_session_id: Claude driver session for conversation continuity.
        status: Current session status.
        topic: Optional initial topic for the session.
        created_at: When the session was created.
        updated_at: When the session was last updated.
    """

    id: str
    profile_id: str
    driver_session_id: str | None = None
    status: SessionStatus
    topic: str | None = None
    created_at: datetime
    updated_at: datetime


class MessagePart(BaseModel):
    """Single part of a message (AI SDK UIMessage compatible).

    Supports text, tool calls, tool results, and reasoning blocks.

    Attributes:
        type: Type of message part.
        text: Text content (for text and reasoning types).
        tool_call_id: Unique ID for tool call/result correlation.
        tool_name: Name of the tool being called.
        args: Arguments passed to the tool.
        result: Result returned from tool execution.
    """

    type: Literal["text", "tool-call", "tool-result", "reasoning"]
    text: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    args: dict[str, Any] | None = None
    result: str | None = None


class Message(BaseModel):
    """Single message in a brainstorming session (AI SDK UIMessage compatible).

    Attributes:
        id: Unique message identifier.
        session_id: Session this message belongs to.
        sequence: Order of message within session (1-based).
        role: Who sent the message (user or assistant).
        content: Text content of the message.
        parts: Optional structured parts (tool calls, reasoning, etc.).
        created_at: When the message was created.
    """

    id: str
    session_id: str
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    parts: list[MessagePart] | None = None
    created_at: datetime


class Artifact(BaseModel):
    """Document produced by a brainstorming session.

    Attributes:
        id: Unique artifact identifier.
        session_id: Session that produced this artifact.
        type: Type of artifact (design, adr, spec, readme, etc.).
        path: File path where artifact is saved.
        title: Optional human-readable title.
        created_at: When the artifact was created.
    """

    id: str
    session_id: str
    type: str
    path: str
    title: str | None = None
    created_at: datetime
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_brainstorm_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/brainstorm.py tests/unit/server/models/test_brainstorm_models.py
git commit -m "feat(brainstorm): add Pydantic models for sessions, messages, artifacts"
```

---

### Task 3: Create Database Schema

**Files:**
- Modify: `amelia/server/database/connection.py` (add schema in `ensure_schema`)

**Step 1: Write the failing test**

Create `tests/unit/server/database/test_brainstorm_schema.py`:

```python
"""Tests for brainstorming database schema."""

import pytest

from amelia.server.database.connection import Database


class TestBrainstormSchema:
    """Test brainstorming tables are created."""

    @pytest.fixture
    async def db_with_schema(self, temp_db_path) -> Database:
        """Create database with schema initialized."""
        async with Database(temp_db_path) as db:
            await db.ensure_schema()
            yield db

    async def test_brainstorm_sessions_table_exists(
        self, db_with_schema: Database
    ) -> None:
        """brainstorm_sessions table should exist after ensure_schema."""
        result = await db_with_schema.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brainstorm_sessions'"
        )
        assert result is not None
        assert result[0] == "brainstorm_sessions"

    async def test_brainstorm_messages_table_exists(
        self, db_with_schema: Database
    ) -> None:
        """brainstorm_messages table should exist after ensure_schema."""
        result = await db_with_schema.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brainstorm_messages'"
        )
        assert result is not None
        assert result[0] == "brainstorm_messages"

    async def test_brainstorm_artifacts_table_exists(
        self, db_with_schema: Database
    ) -> None:
        """brainstorm_artifacts table should exist after ensure_schema."""
        result = await db_with_schema.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brainstorm_artifacts'"
        )
        assert result is not None
        assert result[0] == "brainstorm_artifacts"

    async def test_sessions_has_expected_columns(
        self, db_with_schema: Database
    ) -> None:
        """brainstorm_sessions should have expected columns."""
        rows = await db_with_schema.fetch_all("PRAGMA table_info(brainstorm_sessions)")
        columns = {row[1] for row in rows}  # row[1] is column name
        expected = {
            "id",
            "profile_id",
            "driver_session_id",
            "status",
            "topic",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)

    async def test_messages_has_expected_columns(
        self, db_with_schema: Database
    ) -> None:
        """brainstorm_messages should have expected columns."""
        rows = await db_with_schema.fetch_all("PRAGMA table_info(brainstorm_messages)")
        columns = {row[1] for row in rows}
        expected = {
            "id",
            "session_id",
            "sequence",
            "role",
            "content",
            "parts_json",
            "created_at",
        }
        assert expected.issubset(columns)

    async def test_artifacts_has_expected_columns(
        self, db_with_schema: Database
    ) -> None:
        """brainstorm_artifacts should have expected columns."""
        rows = await db_with_schema.fetch_all("PRAGMA table_info(brainstorm_artifacts)")
        columns = {row[1] for row in rows}
        expected = {"id", "session_id", "type", "path", "title", "created_at"}
        assert expected.issubset(columns)

    async def test_sessions_profile_index_exists(
        self, db_with_schema: Database
    ) -> None:
        """Index on profile_id should exist."""
        result = await db_with_schema.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_brainstorm_sessions_profile'"
        )
        assert result is not None

    async def test_sessions_status_index_exists(
        self, db_with_schema: Database
    ) -> None:
        """Index on status should exist."""
        result = await db_with_schema.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_brainstorm_sessions_status'"
        )
        assert result is not None

    async def test_messages_session_index_exists(
        self, db_with_schema: Database
    ) -> None:
        """Index on session_id, sequence should exist."""
        result = await db_with_schema.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_brainstorm_messages_session'"
        )
        assert result is not None

    async def test_artifacts_session_index_exists(
        self, db_with_schema: Database
    ) -> None:
        """Index on session_id should exist."""
        result = await db_with_schema.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_brainstorm_artifacts_session'"
        )
        assert result is not None

    async def test_messages_unique_constraint(
        self, db_with_schema: Database
    ) -> None:
        """session_id + sequence should be unique."""
        # Insert first message
        await db_with_schema.execute(
            """
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('sess-1', 'profile-1', 'active', datetime('now'), datetime('now'))
            """
        )
        await db_with_schema.execute(
            """
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('msg-1', 'sess-1', 1, 'user', 'Hello', datetime('now'))
            """
        )
        # Try to insert duplicate sequence - should fail
        with pytest.raises(Exception):  # IntegrityError
            await db_with_schema.execute(
                """
                INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
                VALUES ('msg-2', 'sess-1', 1, 'assistant', 'Hi', datetime('now'))
                """
            )

    async def test_messages_cascade_delete(
        self, db_with_schema: Database
    ) -> None:
        """Deleting session should cascade to messages."""
        # Create session and message
        await db_with_schema.execute(
            """
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('sess-2', 'profile-1', 'active', datetime('now'), datetime('now'))
            """
        )
        await db_with_schema.execute(
            """
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('msg-3', 'sess-2', 1, 'user', 'Test', datetime('now'))
            """
        )
        # Delete session
        await db_with_schema.execute(
            "DELETE FROM brainstorm_sessions WHERE id = 'sess-2'"
        )
        # Message should be deleted too
        result = await db_with_schema.fetch_one(
            "SELECT id FROM brainstorm_messages WHERE id = 'msg-3'"
        )
        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_brainstorm_schema.py -v`
Expected: FAIL with assertion errors (tables don't exist)

**Step 3: Write minimal implementation**

In `amelia/server/database/connection.py`, add the following SQL to the `ensure_schema` method after the existing table creation statements:

```python
        # Brainstorming tables
        await self.execute("""
            CREATE TABLE IF NOT EXISTS brainstorm_sessions (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                driver_session_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                topic TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """)

        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_brainstorm_sessions_profile
            ON brainstorm_sessions(profile_id)
        """)

        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_brainstorm_sessions_status
            ON brainstorm_sessions(status)
        """)

        await self.execute("""
            CREATE TABLE IF NOT EXISTS brainstorm_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
                sequence INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                parts_json TEXT,
                created_at TIMESTAMP NOT NULL,
                UNIQUE(session_id, sequence)
            )
        """)

        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_brainstorm_messages_session
            ON brainstorm_messages(session_id, sequence)
        """)

        await self.execute("""
            CREATE TABLE IF NOT EXISTS brainstorm_artifacts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                path TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMP NOT NULL
            )
        """)

        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_brainstorm_artifacts_session
            ON brainstorm_artifacts(session_id)
        """)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_brainstorm_schema.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/connection.py tests/unit/server/database/test_brainstorm_schema.py
git commit -m "feat(brainstorm): add database schema for sessions, messages, artifacts"
```

---

### Task 4: Create BrainstormRepository

**Files:**
- Create: `amelia/server/database/brainstorm_repository.py`

**Step 1: Write the failing test**

Create `tests/unit/server/database/test_brainstorm_repository.py`:

```python
"""Tests for BrainstormRepository."""

import json
from datetime import UTC, datetime

import pytest

from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    MessagePart,
)


class TestBrainstormRepository:
    """Test BrainstormRepository CRUD operations."""

    @pytest.fixture
    async def db(self, temp_db_path) -> Database:
        """Create database with schema."""
        async with Database(temp_db_path) as db:
            await db.ensure_schema()
            yield db

    @pytest.fixture
    def repository(self, db: Database) -> BrainstormRepository:
        """Create repository instance."""
        return BrainstormRepository(db)

    @pytest.fixture
    def sample_session(self) -> BrainstormingSession:
        """Create a sample session for testing."""
        now = datetime.now(UTC)
        return BrainstormingSession(
            id="sess-test-123",
            profile_id="work",
            status="active",
            topic="Design a caching layer",
            created_at=now,
            updated_at=now,
        )


class TestSessionCRUD(TestBrainstormRepository):
    """Test session CRUD operations."""

    async def test_create_session(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should create a new session."""
        await repository.create_session(sample_session)

        result = await repository.get_session(sample_session.id)
        assert result is not None
        assert result.id == sample_session.id
        assert result.profile_id == "work"
        assert result.status == "active"
        assert result.topic == "Design a caching layer"

    async def test_get_session_not_found(
        self, repository: BrainstormRepository
    ) -> None:
        """Should return None for non-existent session."""
        result = await repository.get_session("nonexistent")
        assert result is None

    async def test_update_session(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should update session fields."""
        await repository.create_session(sample_session)

        sample_session.status = "ready_for_handoff"
        sample_session.driver_session_id = "claude-sess-456"
        sample_session.updated_at = datetime.now(UTC)

        await repository.update_session(sample_session)

        result = await repository.get_session(sample_session.id)
        assert result is not None
        assert result.status == "ready_for_handoff"
        assert result.driver_session_id == "claude-sess-456"

    async def test_delete_session(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should delete session."""
        await repository.create_session(sample_session)
        await repository.delete_session(sample_session.id)

        result = await repository.get_session(sample_session.id)
        assert result is None

    async def test_list_sessions_by_profile(
        self, repository: BrainstormRepository
    ) -> None:
        """Should list sessions filtered by profile."""
        now = datetime.now(UTC)
        session1 = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        session2 = BrainstormingSession(
            id="sess-2", profile_id="personal", status="active",
            created_at=now, updated_at=now,
        )
        await repository.create_session(session1)
        await repository.create_session(session2)

        work_sessions = await repository.list_sessions(profile_id="work")
        assert len(work_sessions) == 1
        assert work_sessions[0].id == "sess-1"

    async def test_list_sessions_by_status(
        self, repository: BrainstormRepository
    ) -> None:
        """Should list sessions filtered by status."""
        now = datetime.now(UTC)
        session1 = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        session2 = BrainstormingSession(
            id="sess-2", profile_id="work", status="completed",
            created_at=now, updated_at=now,
        )
        await repository.create_session(session1)
        await repository.create_session(session2)

        active_sessions = await repository.list_sessions(status="active")
        assert len(active_sessions) == 1
        assert active_sessions[0].id == "sess-1"


class TestMessageCRUD(TestBrainstormRepository):
    """Test message CRUD operations."""

    async def test_save_message(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should save a message."""
        await repository.create_session(sample_session)

        message = Message(
            id="msg-1",
            session_id=sample_session.id,
            sequence=1,
            role="user",
            content="Design a caching layer",
            created_at=datetime.now(UTC),
        )
        await repository.save_message(message)

        messages = await repository.get_messages(sample_session.id)
        assert len(messages) == 1
        assert messages[0].content == "Design a caching layer"

    async def test_save_message_with_parts(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should save message with parts."""
        await repository.create_session(sample_session)

        message = Message(
            id="msg-2",
            session_id=sample_session.id,
            sequence=1,
            role="assistant",
            content="Here's my analysis...",
            parts=[
                MessagePart(type="reasoning", text="Let me think..."),
                MessagePart(type="text", text="Here's my analysis..."),
            ],
            created_at=datetime.now(UTC),
        )
        await repository.save_message(message)

        messages = await repository.get_messages(sample_session.id)
        assert len(messages) == 1
        assert messages[0].parts is not None
        assert len(messages[0].parts) == 2
        assert messages[0].parts[0].type == "reasoning"

    async def test_get_messages_ordered(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should return messages in sequence order."""
        await repository.create_session(sample_session)

        for i in range(3, 0, -1):  # Insert in reverse order
            msg = Message(
                id=f"msg-{i}",
                session_id=sample_session.id,
                sequence=i,
                role="user" if i % 2 else "assistant",
                content=f"Message {i}",
                created_at=datetime.now(UTC),
            )
            await repository.save_message(msg)

        messages = await repository.get_messages(sample_session.id)
        assert [m.sequence for m in messages] == [1, 2, 3]

    async def test_get_max_sequence(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should return max sequence number."""
        await repository.create_session(sample_session)

        # No messages yet
        assert await repository.get_max_sequence(sample_session.id) == 0

        # Add messages
        for i in range(1, 4):
            msg = Message(
                id=f"msg-{i}",
                session_id=sample_session.id,
                sequence=i,
                role="user",
                content=f"Message {i}",
                created_at=datetime.now(UTC),
            )
            await repository.save_message(msg)

        assert await repository.get_max_sequence(sample_session.id) == 3


class TestArtifactCRUD(TestBrainstormRepository):
    """Test artifact CRUD operations."""

    async def test_save_artifact(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should save an artifact."""
        await repository.create_session(sample_session)

        artifact = Artifact(
            id="art-1",
            session_id=sample_session.id,
            type="design",
            path="docs/plans/design.md",
            title="Caching Design",
            created_at=datetime.now(UTC),
        )
        await repository.save_artifact(artifact)

        artifacts = await repository.get_artifacts(sample_session.id)
        assert len(artifacts) == 1
        assert artifacts[0].path == "docs/plans/design.md"

    async def test_get_artifacts_empty(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should return empty list for session with no artifacts."""
        await repository.create_session(sample_session)
        artifacts = await repository.get_artifacts(sample_session.id)
        assert artifacts == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_brainstorm_repository.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.server.database.brainstorm_repository'"

**Step 3: Write minimal implementation**

Create `amelia/server/database/brainstorm_repository.py`:

```python
"""Repository for brainstorming session operations.

Handles persistence and retrieval of brainstorming sessions,
messages, and artifacts.
"""

import json
from datetime import datetime

from amelia.server.database.connection import Database
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    MessagePart,
    SessionStatus,
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
                id, profile_id, driver_session_id, status, topic,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.profile_id,
                session.driver_session_id,
                session.status,
                session.topic,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
            ),
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
            SELECT id, profile_id, driver_session_id, status, topic,
                   created_at, updated_at
            FROM brainstorm_sessions WHERE id = ?
            """,
            (session_id,),
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
                driver_session_id = ?,
                status = ?,
                topic = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                session.driver_session_id,
                session.status,
                session.topic,
                session.updated_at.isoformat(),
                session.id,
            ),
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete session.

        Args:
            session_id: Session to delete.
        """
        await self._db.execute(
            "DELETE FROM brainstorm_sessions WHERE id = ?",
            (session_id,),
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

        if profile_id:
            conditions.append("profile_id = ?")
            params.append(profile_id)

        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        rows = await self._db.fetch_all(
            f"""
            SELECT id, profile_id, driver_session_id, status, topic,
                   created_at, updated_at
            FROM brainstorm_sessions
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            params,
        )
        return [self._row_to_session(row) for row in rows]

    def _row_to_session(self, row) -> BrainstormingSession:
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
            status=row["status"],
            topic=row["topic"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # =========================================================================
    # Message Operations
    # =========================================================================

    async def save_message(self, message: Message) -> None:
        """Save a message.

        Args:
            message: Message to save.
        """
        parts_json = None
        if message.parts:
            parts_json = json.dumps([p.model_dump() for p in message.parts])

        await self._db.execute(
            """
            INSERT INTO brainstorm_messages (
                id, session_id, sequence, role, content, parts_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.session_id,
                message.sequence,
                message.role,
                message.content,
                parts_json,
                message.created_at.isoformat(),
            ),
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
            SELECT id, session_id, sequence, role, content, parts_json, created_at
            FROM brainstorm_messages
            WHERE session_id = ?
            ORDER BY sequence ASC
            LIMIT ?
            """,
            (session_id, limit),
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
            "SELECT COALESCE(MAX(sequence), 0) FROM brainstorm_messages WHERE session_id = ?",
            (session_id,),
        )
        return result if isinstance(result, int) else 0

    def _row_to_message(self, row) -> Message:
        """Convert database row to Message.

        Args:
            row: Database row.

        Returns:
            Message instance.
        """
        parts = None
        if row["parts_json"]:
            parts_data = json.loads(row["parts_json"])
            parts = [MessagePart(**p) for p in parts_data]

        return Message(
            id=row["id"],
            session_id=row["session_id"],
            sequence=row["sequence"],
            role=row["role"],
            content=row["content"],
            parts=parts,
            created_at=datetime.fromisoformat(row["created_at"]),
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
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.id,
                artifact.session_id,
                artifact.type,
                artifact.path,
                artifact.title,
                artifact.created_at.isoformat(),
            ),
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
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        return [self._row_to_artifact(row) for row in rows]

    def _row_to_artifact(self, row) -> Artifact:
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
            created_at=datetime.fromisoformat(row["created_at"]),
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_brainstorm_repository.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/brainstorm_repository.py tests/unit/server/database/test_brainstorm_repository.py
git commit -m "feat(brainstorm): add BrainstormRepository for session/message/artifact CRUD"
```

---

### Task 5: Create BrainstormService

**Files:**
- Create: `amelia/server/services/brainstorm.py`

**Step 1: Write the failing test**

Create `tests/unit/server/services/test_brainstorm_service.py`:

```python
"""Tests for BrainstormService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.server.models.brainstorm import BrainstormingSession, Message
from amelia.server.services.brainstorm import BrainstormService


class TestBrainstormService:
    """Test BrainstormService operations."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        repo = MagicMock()
        repo.create_session = AsyncMock()
        repo.get_session = AsyncMock(return_value=None)
        repo.update_session = AsyncMock()
        repo.delete_session = AsyncMock()
        repo.list_sessions = AsyncMock(return_value=[])
        repo.save_message = AsyncMock()
        repo.get_messages = AsyncMock(return_value=[])
        repo.get_max_sequence = AsyncMock(return_value=0)
        repo.save_artifact = AsyncMock()
        repo.get_artifacts = AsyncMock(return_value=[])
        return repo

    @pytest.fixture
    def mock_event_bus(self) -> MagicMock:
        """Create mock event bus."""
        bus = MagicMock()
        bus.emit = MagicMock()
        return bus

    @pytest.fixture
    def service(
        self, mock_repository: MagicMock, mock_event_bus: MagicMock
    ) -> BrainstormService:
        """Create service instance."""
        return BrainstormService(mock_repository, mock_event_bus)


class TestCreateSession(TestBrainstormService):
    """Test session creation."""

    async def test_create_session_generates_id(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should generate UUID for new session."""
        session = await service.create_session(
            profile_id="work", topic="Design a cache"
        )

        assert session.id is not None
        assert len(session.id) == 36  # UUID format
        mock_repository.create_session.assert_called_once()

    async def test_create_session_sets_defaults(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should set default status and timestamps."""
        session = await service.create_session(profile_id="work")

        assert session.status == "active"
        assert session.created_at is not None
        assert session.updated_at is not None

    async def test_create_session_emits_event(
        self, service: BrainstormService, mock_event_bus: MagicMock
    ) -> None:
        """Should emit session created event."""
        await service.create_session(profile_id="work")

        mock_event_bus.emit.assert_called_once()
        event = mock_event_bus.emit.call_args[0][0]
        assert event.event_type.value == "brainstorm_session_created"


class TestGetSession(TestBrainstormService):
    """Test session retrieval."""

    async def test_get_session_returns_session_with_messages(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should return session with messages and artifacts."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_messages.return_value = [
            Message(
                id="msg-1", session_id="sess-1", sequence=1,
                role="user", content="Hello", created_at=now,
            )
        ]
        mock_repository.get_artifacts.return_value = []

        result = await service.get_session_with_history("sess-1")

        assert result is not None
        assert result["session"].id == "sess-1"
        assert len(result["messages"]) == 1
        assert result["artifacts"] == []

    async def test_get_session_not_found(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should return None for non-existent session."""
        mock_repository.get_session.return_value = None

        result = await service.get_session_with_history("nonexistent")

        assert result is None


class TestDeleteSession(TestBrainstormService):
    """Test session deletion."""

    async def test_delete_session(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should delete session."""
        await service.delete_session("sess-1")
        mock_repository.delete_session.assert_called_once_with("sess-1")


class TestUpdateSessionStatus(TestBrainstormService):
    """Test session status updates."""

    async def test_update_status(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should update session status."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session

        await service.update_session_status("sess-1", "ready_for_handoff")

        mock_repository.update_session.assert_called_once()
        updated = mock_repository.update_session.call_args[0][0]
        assert updated.status == "ready_for_handoff"

    async def test_update_status_session_not_found(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should raise error if session not found."""
        mock_repository.get_session.return_value = None

        with pytest.raises(ValueError, match="Session not found"):
            await service.update_session_status("nonexistent", "completed")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.server.services'"

**Step 3: Write minimal implementation**

Create directory and file `amelia/server/services/__init__.py` (empty).

Create `amelia/server/services/brainstorm.py`:

```python
"""Service layer for brainstorming operations.

Handles business logic for brainstorming sessions, coordinating
between the repository, event bus, and Claude driver.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    SessionStatus,
)
from amelia.server.models.events import EventType, WorkflowEvent


class BrainstormService:
    """Service for brainstorming session management.

    Coordinates session lifecycle, message handling, and event emission.

    Attributes:
        _repository: Database repository for persistence.
        _event_bus: Event bus for WebSocket broadcasting.
    """

    def __init__(
        self,
        repository: BrainstormRepository,
        event_bus: EventBus,
    ) -> None:
        """Initialize service.

        Args:
            repository: Database repository.
            event_bus: Event bus for broadcasting.
        """
        self._repository = repository
        self._event_bus = event_bus

    async def create_session(
        self,
        profile_id: str,
        topic: str | None = None,
    ) -> BrainstormingSession:
        """Create a new brainstorming session.

        Args:
            profile_id: Profile/project for the session.
            topic: Optional initial topic.

        Returns:
            Created session.
        """
        now = datetime.now(UTC)
        session = BrainstormingSession(
            id=str(uuid4()),
            profile_id=profile_id,
            status="active",
            topic=topic,
            created_at=now,
            updated_at=now,
        )

        await self._repository.create_session(session)

        # Emit session created event
        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session.id,  # Use session_id as workflow_id for events
            sequence=0,
            timestamp=now,
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_SESSION_CREATED,
            message=f"Brainstorming session created: {topic or 'No topic'}",
            data={"session_id": session.id, "profile_id": profile_id, "topic": topic},
        )
        self._event_bus.emit(event)

        return session

    async def get_session_with_history(
        self, session_id: str
    ) -> dict[str, Any] | None:
        """Get session with messages and artifacts.

        Args:
            session_id: Session to retrieve.

        Returns:
            Dict with session, messages, and artifacts, or None if not found.
        """
        session = await self._repository.get_session(session_id)
        if session is None:
            return None

        messages = await self._repository.get_messages(session_id)
        artifacts = await self._repository.get_artifacts(session_id)

        return {
            "session": session,
            "messages": messages,
            "artifacts": artifacts,
        }

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
        return await self._repository.list_sessions(
            profile_id=profile_id, status=status, limit=limit
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session.

        Args:
            session_id: Session to delete.
        """
        await self._repository.delete_session(session_id)

    async def update_session_status(
        self, session_id: str, status: SessionStatus
    ) -> BrainstormingSession:
        """Update session status.

        Args:
            session_id: Session to update.
            status: New status.

        Returns:
            Updated session.

        Raises:
            ValueError: If session not found.
        """
        session = await self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        session.status = status
        session.updated_at = datetime.now(UTC)
        await self._repository.update_session(session)

        return session

    async def update_driver_session_id(
        self, session_id: str, driver_session_id: str
    ) -> None:
        """Update the Claude driver session ID.

        Args:
            session_id: Session to update.
            driver_session_id: New driver session ID.

        Raises:
            ValueError: If session not found.
        """
        session = await self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        session.driver_session_id = driver_session_id
        session.updated_at = datetime.now(UTC)
        await self._repository.update_session(session)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/services/__init__.py amelia/server/services/brainstorm.py tests/unit/server/services/test_brainstorm_service.py
git commit -m "feat(brainstorm): add BrainstormService for session management"
```

---

## Phase 2b: Chat Endpoint

### Task 6: Create Brainstorm API Routes (Session CRUD)

**Files:**
- Create: `amelia/server/routes/brainstorm.py`
- Modify: `amelia/server/main.py` (register router)

**Step 1: Write the failing test**

Create `tests/unit/server/routes/test_brainstorm_routes.py`:

```python
"""Tests for brainstorming API routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.models.brainstorm import BrainstormingSession
from amelia.server.routes.brainstorm import router


class TestBrainstormRoutes:
    """Test brainstorming API endpoints."""

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        """Create mock BrainstormService."""
        service = MagicMock()
        service.create_session = AsyncMock()
        service.get_session_with_history = AsyncMock()
        service.list_sessions = AsyncMock(return_value=[])
        service.delete_session = AsyncMock()
        return service

    @pytest.fixture
    def app(self, mock_service: MagicMock) -> FastAPI:
        """Create test app with mocked dependencies."""
        app = FastAPI()
        app.include_router(router, prefix="/api/brainstorm")

        # Override dependency
        from amelia.server.routes.brainstorm import get_brainstorm_service
        app.dependency_overrides[get_brainstorm_service] = lambda: mock_service

        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)


class TestCreateSession(TestBrainstormRoutes):
    """Test POST /api/brainstorm/sessions."""

    def test_create_session_minimal(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should create session with minimal fields."""
        now = datetime.now(UTC)
        mock_service.create_session.return_value = BrainstormingSession(
            id="sess-123",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )

        response = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "work"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "sess-123"
        assert data["status"] == "active"

    def test_create_session_with_topic(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should create session with topic."""
        now = datetime.now(UTC)
        mock_service.create_session.return_value = BrainstormingSession(
            id="sess-123",
            profile_id="work",
            status="active",
            topic="Design a cache",
            created_at=now,
            updated_at=now,
        )

        response = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "work", "topic": "Design a cache"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["topic"] == "Design a cache"


class TestListSessions(TestBrainstormRoutes):
    """Test GET /api/brainstorm/sessions."""

    def test_list_sessions_empty(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return empty list when no sessions."""
        response = client.get("/api/brainstorm/sessions")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_sessions_with_filter(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should pass filters to service."""
        now = datetime.now(UTC)
        mock_service.list_sessions.return_value = [
            BrainstormingSession(
                id="sess-1", profile_id="work", status="active",
                created_at=now, updated_at=now,
            )
        ]

        response = client.get(
            "/api/brainstorm/sessions",
            params={"profile_id": "work", "status": "active"},
        )

        assert response.status_code == 200
        mock_service.list_sessions.assert_called_once_with(
            profile_id="work", status="active", limit=50
        )


class TestGetSession(TestBrainstormRoutes):
    """Test GET /api/brainstorm/sessions/{id}."""

    def test_get_session_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return session with history."""
        now = datetime.now(UTC)
        mock_service.get_session_with_history.return_value = {
            "session": BrainstormingSession(
                id="sess-123", profile_id="work", status="active",
                created_at=now, updated_at=now,
            ),
            "messages": [],
            "artifacts": [],
        }

        response = client.get("/api/brainstorm/sessions/sess-123")

        assert response.status_code == 200
        data = response.json()
        assert data["session"]["id"] == "sess-123"

    def test_get_session_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return 404 for non-existent session."""
        mock_service.get_session_with_history.return_value = None

        response = client.get("/api/brainstorm/sessions/nonexistent")

        assert response.status_code == 404


class TestDeleteSession(TestBrainstormRoutes):
    """Test DELETE /api/brainstorm/sessions/{id}."""

    def test_delete_session(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should delete session."""
        response = client.delete("/api/brainstorm/sessions/sess-123")

        assert response.status_code == 204
        mock_service.delete_session.assert_called_once_with("sess-123")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_routes.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.server.routes.brainstorm'"

**Step 3: Write minimal implementation**

Create `amelia/server/routes/brainstorm.py`:

```python
"""API routes for brainstorming sessions.

Provides endpoints for session lifecycle management and chat functionality.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    SessionStatus,
)
from amelia.server.services.brainstorm import BrainstormService

router = APIRouter(tags=["brainstorm"])


# Dependency placeholder - will be properly wired in main.py
def get_brainstorm_service() -> BrainstormService:
    """Get BrainstormService dependency.

    Returns:
        BrainstormService instance.

    Raises:
        RuntimeError: If service not initialized.
    """
    raise RuntimeError("BrainstormService not initialized")


# Request/Response Models
class CreateSessionRequest(BaseModel):
    """Request to create a new brainstorming session."""

    profile_id: str
    topic: str | None = None


class SessionWithHistoryResponse(BaseModel):
    """Response containing session with messages and artifacts."""

    session: BrainstormingSession
    messages: list[Message]
    artifacts: list[Artifact]


# Session Lifecycle Endpoints
@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=BrainstormingSession,
)
async def create_session(
    request: CreateSessionRequest,
    service: BrainstormService = Depends(get_brainstorm_service),
) -> BrainstormingSession:
    """Create a new brainstorming session.

    Args:
        request: Session creation request.
        service: Brainstorm service dependency.

    Returns:
        Created session.
    """
    return await service.create_session(
        profile_id=request.profile_id,
        topic=request.topic,
    )


@router.get("/sessions", response_model=list[BrainstormingSession])
async def list_sessions(
    profile_id: Annotated[str | None, Query()] = None,
    status: Annotated[SessionStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    service: BrainstormService = Depends(get_brainstorm_service),
) -> list[BrainstormingSession]:
    """List brainstorming sessions.

    Args:
        profile_id: Filter by profile.
        status: Filter by status.
        limit: Maximum sessions to return.
        service: Brainstorm service dependency.

    Returns:
        List of sessions.
    """
    return await service.list_sessions(
        profile_id=profile_id, status=status, limit=limit
    )


@router.get("/sessions/{session_id}", response_model=SessionWithHistoryResponse)
async def get_session(
    session_id: str,
    service: BrainstormService = Depends(get_brainstorm_service),
) -> SessionWithHistoryResponse:
    """Get session with messages and artifacts.

    Args:
        session_id: Session to retrieve.
        service: Brainstorm service dependency.

    Returns:
        Session with history.

    Raises:
        HTTPException: 404 if session not found.
    """
    result = await service.get_session_with_history(session_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    return SessionWithHistoryResponse(**result)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    service: BrainstormService = Depends(get_brainstorm_service),
) -> None:
    """Delete a brainstorming session.

    Args:
        session_id: Session to delete.
        service: Brainstorm service dependency.
    """
    await service.delete_session(session_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_routes.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/brainstorm.py tests/unit/server/routes/test_brainstorm_routes.py
git commit -m "feat(brainstorm): add session CRUD API endpoints"
```

---

### Task 7: Add Message Endpoint with Driver Integration

**Files:**
- Modify: `amelia/server/services/brainstorm.py` (add send_message method)
- Modify: `amelia/server/routes/brainstorm.py` (add message endpoint)

**Step 1: Write the failing test**

Add to `tests/unit/server/services/test_brainstorm_service.py`:

```python
class TestSendMessage(TestBrainstormService):
    """Test message sending with driver integration."""

    @pytest.fixture
    def mock_driver(self) -> MagicMock:
        """Create mock driver."""
        driver = MagicMock()
        # execute_agentic returns an async iterator
        async def mock_execute_agentic(*args, **kwargs):
            from amelia.drivers.base import AgenticMessage, AgenticMessageType
            yield AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Let me think about this...",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Here's my response",
                session_id="claude-sess-789",
            )
        driver.execute_agentic = mock_execute_agentic
        return driver

    async def test_send_message_saves_user_message(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_driver: MagicMock,
    ) -> None:
        """Should save user message to database."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        # Consume the async generator
        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Design a cache",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify user message was saved
        save_calls = mock_repository.save_message.call_args_list
        user_msg_call = save_calls[0][0][0]
        assert user_msg_call.role == "user"
        assert user_msg_call.content == "Design a cache"
        assert user_msg_call.sequence == 1

    async def test_send_message_emits_events(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver: MagicMock,
    ) -> None:
        """Should emit events for driver messages."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Design a cache",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify events were emitted (thinking + result + message_complete)
        assert mock_event_bus.emit.call_count >= 2

    async def test_send_message_updates_driver_session_id(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_driver: MagicMock,
    ) -> None:
        """Should update driver_session_id from result."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Hello",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify session was updated with driver session ID
        update_calls = mock_repository.update_session.call_args_list
        assert len(update_calls) > 0
        # Find the call that updated driver_session_id
        updated_session = update_calls[-1][0][0]
        assert updated_session.driver_session_id == "claude-sess-789"

    async def test_send_message_session_not_found(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_driver: MagicMock,
    ) -> None:
        """Should raise error if session not found."""
        mock_repository.get_session.return_value = None

        with pytest.raises(ValueError, match="Session not found"):
            async for _ in service.send_message(
                session_id="nonexistent",
                content="Hello",
                driver=mock_driver,
                cwd="/tmp/project",
            ):
                pass
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestSendMessage -v`
Expected: FAIL with "AttributeError: 'BrainstormService' object has no attribute 'send_message'"

**Step 3: Write minimal implementation**

Add to `amelia/server/services/brainstorm.py`:

```python
from collections.abc import AsyncIterator
from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverInterface

# Add BRAINSTORMER_SYSTEM_PROMPT constant at module level
BRAINSTORMER_SYSTEM_PROMPT = """You help turn ideas into fully formed designs through collaborative dialogue.

## Your Process

### Phase 1: Understanding
- First, explore the codebase to understand existing patterns (use Oracle if needed)
- Ask questions ONE AT A TIME to clarify the idea
- Prefer multiple choice questions when possible
- Focus on: purpose, constraints, success criteria

### Phase 2: Exploring Approaches
- Propose 2-3 different approaches with trade-offs
- Lead with your recommendation and explain why
- Let the user choose before proceeding

### Phase 3: Presenting the Design
- Present the design in sections (200-300 words each)
- After each section ask: "Does this look right so far?"
- Cover: architecture, components, data flow, error handling, testing
- Be ready to revise based on feedback

### Phase 4: Documentation
- When all sections are validated, ask: "Ready to write the document?"
- If confirmed, write the design doc to `docs/plans/YYYY-MM-DD-<topic>-design.md`
- Use clear, concise prose (active voice, no jargon, omit needless words)

## Tools Available
- **Oracle**: For researching the codebase, exploring patterns, getting expert guidance
- **File tools**: For reading existing code and writing the final document

## Key Principles
- One question at a time — don't overwhelm
- YAGNI ruthlessly — remove unnecessary features
- Validate incrementally — don't present everything at once
- Be flexible — go back and clarify when needed
"""


class BrainstormService:
    # ... existing methods ...

    async def send_message(
        self,
        session_id: str,
        content: str,
        driver: DriverInterface,
        cwd: str,
    ) -> AsyncIterator[AgenticMessage]:
        """Send a message and stream the response.

        Args:
            session_id: Session to send message to.
            content: User message content.
            driver: Claude driver for execution.
            cwd: Working directory for tool execution.

        Yields:
            AgenticMessage for each event during execution.

        Raises:
            ValueError: If session not found.
        """
        session = await self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Get next sequence number and save user message
        sequence = await self._repository.get_max_sequence(session_id) + 1
        user_message = Message(
            id=str(uuid4()),
            session_id=session_id,
            sequence=sequence,
            role="user",
            content=content,
            created_at=datetime.now(UTC),
        )
        await self._repository.save_message(user_message)

        # Prepare for assistant response
        assistant_parts: list[MessagePart] = []
        assistant_content = ""
        driver_session_id: str | None = session.driver_session_id

        # Execute with driver
        async for msg in driver.execute_agentic(
            prompt=content,
            cwd=cwd,
            session_id=driver_session_id,
            instructions=BRAINSTORMER_SYSTEM_PROMPT,
        ):
            # Emit event for each message
            event = self._agentic_message_to_event(msg, session_id)
            self._event_bus.emit(event)

            # Collect parts for saving
            if msg.type == AgenticMessageType.THINKING:
                assistant_parts.append(
                    MessagePart(type="reasoning", text=msg.content)
                )
            elif msg.type == AgenticMessageType.TOOL_CALL:
                assistant_parts.append(
                    MessagePart(
                        type="tool-call",
                        tool_call_id=msg.tool_call_id,
                        tool_name=msg.tool_name,
                        args=msg.tool_input,
                    )
                )
            elif msg.type == AgenticMessageType.TOOL_RESULT:
                assistant_parts.append(
                    MessagePart(
                        type="tool-result",
                        tool_call_id=msg.tool_call_id,
                        result=msg.tool_output,
                    )
                )
            elif msg.type == AgenticMessageType.RESULT:
                assistant_content = msg.content or ""
                assistant_parts.append(
                    MessagePart(type="text", text=assistant_content)
                )
                if msg.session_id:
                    driver_session_id = msg.session_id

            yield msg

        # Save assistant message
        assistant_message = Message(
            id=str(uuid4()),
            session_id=session_id,
            sequence=sequence + 1,
            role="assistant",
            content=assistant_content,
            parts=assistant_parts if assistant_parts else None,
            created_at=datetime.now(UTC),
        )
        await self._repository.save_message(assistant_message)

        # Update session with driver session ID if changed
        if driver_session_id and driver_session_id != session.driver_session_id:
            session.driver_session_id = driver_session_id
            session.updated_at = datetime.now(UTC)
            await self._repository.update_session(session)

        # Emit message complete event
        complete_event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_MESSAGE_COMPLETE,
            message="Assistant response complete",
            data={"message_id": assistant_message.id},
        )
        self._event_bus.emit(complete_event)

    def _agentic_message_to_event(
        self, msg: AgenticMessage, session_id: str
    ) -> WorkflowEvent:
        """Convert AgenticMessage to WorkflowEvent.

        Args:
            msg: Agentic message from driver.
            session_id: Session ID for the event.

        Returns:
            WorkflowEvent for broadcasting.
        """
        type_mapping = {
            AgenticMessageType.THINKING: EventType.BRAINSTORM_REASONING,
            AgenticMessageType.TOOL_CALL: EventType.BRAINSTORM_TOOL_CALL,
            AgenticMessageType.TOOL_RESULT: EventType.BRAINSTORM_TOOL_RESULT,
            AgenticMessageType.RESULT: EventType.BRAINSTORM_TEXT,
        }

        event_type = type_mapping.get(msg.type, EventType.BRAINSTORM_TEXT)

        return WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=event_type,
            message=msg.content or "",
            tool_name=msg.tool_name,
            tool_input=msg.tool_input,
            is_error=msg.is_error,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestSendMessage -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/services/brainstorm.py tests/unit/server/services/test_brainstorm_service.py
git commit -m "feat(brainstorm): add send_message with driver integration and event streaming"
```

---

### Task 8: Add Message Route Endpoint

**Files:**
- Modify: `amelia/server/routes/brainstorm.py` (add POST /sessions/{id}/message)

**Step 1: Write the failing test**

Add to `tests/unit/server/routes/test_brainstorm_routes.py`:

```python
class TestSendMessage(TestBrainstormRoutes):
    """Test POST /api/brainstorm/sessions/{id}/message."""

    def test_send_message_returns_message_id(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return message_id on success."""
        # Mock send_message as async generator
        async def mock_send_message(*args, **kwargs):
            from amelia.drivers.base import AgenticMessage, AgenticMessageType
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response",
            )
        mock_service.send_message = mock_send_message

        # Also need to mock the repository's get_session
        now = datetime.now(UTC)
        mock_service._repository = MagicMock()
        mock_service._repository.get_session = AsyncMock(
            return_value=BrainstormingSession(
                id="sess-123", profile_id="work", status="active",
                created_at=now, updated_at=now,
            )
        )

        response = client.post(
            "/api/brainstorm/sessions/sess-123/message",
            json={"content": "Design a cache"},
        )

        assert response.status_code == 202
        data = response.json()
        assert "message_id" in data
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_routes.py::TestSendMessage -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Write minimal implementation**

Add to `amelia/server/routes/brainstorm.py`:

```python
class SendMessageRequest(BaseModel):
    """Request to send a message in a session."""

    content: str


class SendMessageResponse(BaseModel):
    """Response after sending a message."""

    message_id: str


# Placeholder for driver dependency - will be wired in main.py
def get_driver() -> "DriverInterface":
    """Get driver dependency."""
    raise RuntimeError("Driver not initialized")


def get_cwd() -> str:
    """Get current working directory."""
    import os
    return os.getcwd()


@router.post(
    "/sessions/{session_id}/message",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SendMessageResponse,
)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    service: BrainstormService = Depends(get_brainstorm_service),
    driver: "DriverInterface" = Depends(get_driver),
    cwd: str = Depends(get_cwd),
) -> SendMessageResponse:
    """Send a message in a brainstorming session.

    Streaming happens via WebSocket (/ws/events), this endpoint
    just initiates the message and returns a message ID.

    Args:
        session_id: Session to send message to.
        request: Message content.
        service: Brainstorm service dependency.
        driver: Claude driver dependency.
        cwd: Working directory.

    Returns:
        Message ID for tracking.

    Raises:
        HTTPException: 404 if session not found.
    """
    from uuid import uuid4

    message_id = str(uuid4())

    try:
        # Consume the async generator to execute the message
        async for _ in service.send_message(
            session_id=session_id,
            content=request.content,
            driver=driver,
            cwd=cwd,
        ):
            pass  # Events are emitted via EventBus -> WebSocket
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        raise

    return SendMessageResponse(message_id=message_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_routes.py::TestSendMessage -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/brainstorm.py tests/unit/server/routes/test_brainstorm_routes.py
git commit -m "feat(brainstorm): add POST /sessions/{id}/message endpoint"
```

---

### Task 9: Detect Artifact Creation from Tool Results

**Files:**
- Modify: `amelia/server/services/brainstorm.py` (detect write_file calls)

**Step 1: Write the failing test**

Add to `tests/unit/server/services/test_brainstorm_service.py`:

```python
class TestArtifactDetection(TestBrainstormService):
    """Test artifact detection from tool results."""

    @pytest.fixture
    def mock_driver_with_write(self) -> MagicMock:
        """Create mock driver that writes a file."""
        driver = MagicMock()
        async def mock_execute_agentic(*args, **kwargs):
            from amelia.drivers.base import AgenticMessage, AgenticMessageType
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_file",
                tool_input={"path": "docs/plans/2026-01-18-cache-design.md"},
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="write_file",
                tool_output="File written successfully",
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I've written the design document.",
                session_id="claude-sess-789",
            )
        driver.execute_agentic = mock_execute_agentic
        return driver

    async def test_detects_artifact_from_write_file(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver_with_write: MagicMock,
    ) -> None:
        """Should save artifact when write_file tool is used."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Write the design doc",
            driver=mock_driver_with_write,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify artifact was saved
        mock_repository.save_artifact.assert_called_once()
        artifact = mock_repository.save_artifact.call_args[0][0]
        assert artifact.path == "docs/plans/2026-01-18-cache-design.md"
        assert artifact.type == "design"  # Inferred from path

    async def test_emits_artifact_created_event(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver_with_write: MagicMock,
    ) -> None:
        """Should emit BRAINSTORM_ARTIFACT_CREATED event."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Write the design doc",
            driver=mock_driver_with_write,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Find artifact created event
        artifact_events = [
            call[0][0] for call in mock_event_bus.emit.call_args_list
            if call[0][0].event_type == EventType.BRAINSTORM_ARTIFACT_CREATED
        ]
        assert len(artifact_events) == 1
        assert artifact_events[0].data["path"] == "docs/plans/2026-01-18-cache-design.md"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestArtifactDetection -v`
Expected: FAIL (save_artifact not called)

**Step 3: Write minimal implementation**

Update the `send_message` method in `amelia/server/services/brainstorm.py` to detect and save artifacts:

```python
    async def send_message(
        self,
        session_id: str,
        content: str,
        driver: DriverInterface,
        cwd: str,
    ) -> AsyncIterator[AgenticMessage]:
        """Send a message and stream the response.

        ... existing docstring ...
        """
        session = await self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Get next sequence number and save user message
        sequence = await self._repository.get_max_sequence(session_id) + 1
        user_message = Message(
            id=str(uuid4()),
            session_id=session_id,
            sequence=sequence,
            role="user",
            content=content,
            created_at=datetime.now(UTC),
        )
        await self._repository.save_message(user_message)

        # Prepare for assistant response
        assistant_parts: list[MessagePart] = []
        assistant_content = ""
        driver_session_id: str | None = session.driver_session_id

        # Track pending write_file calls for artifact detection
        pending_write_files: dict[str, str] = {}  # tool_call_id -> path

        # Execute with driver
        async for msg in driver.execute_agentic(
            prompt=content,
            cwd=cwd,
            session_id=driver_session_id,
            instructions=BRAINSTORMER_SYSTEM_PROMPT,
        ):
            # Emit event for each message
            event = self._agentic_message_to_event(msg, session_id)
            self._event_bus.emit(event)

            # Collect parts for saving
            if msg.type == AgenticMessageType.THINKING:
                assistant_parts.append(
                    MessagePart(type="reasoning", text=msg.content)
                )
            elif msg.type == AgenticMessageType.TOOL_CALL:
                assistant_parts.append(
                    MessagePart(
                        type="tool-call",
                        tool_call_id=msg.tool_call_id,
                        tool_name=msg.tool_name,
                        args=msg.tool_input,
                    )
                )
                # Track write_file calls
                if msg.tool_name == "write_file" and msg.tool_input and msg.tool_call_id:
                    path = msg.tool_input.get("path", "")
                    if path:
                        pending_write_files[msg.tool_call_id] = path

            elif msg.type == AgenticMessageType.TOOL_RESULT:
                assistant_parts.append(
                    MessagePart(
                        type="tool-result",
                        tool_call_id=msg.tool_call_id,
                        result=msg.tool_output,
                    )
                )
                # Check for successful write_file results
                if msg.tool_call_id and msg.tool_call_id in pending_write_files and not msg.is_error:
                    path = pending_write_files.pop(msg.tool_call_id)
                    await self._create_artifact_from_path(session_id, path)

            elif msg.type == AgenticMessageType.RESULT:
                assistant_content = msg.content or ""
                assistant_parts.append(
                    MessagePart(type="text", text=assistant_content)
                )
                if msg.session_id:
                    driver_session_id = msg.session_id

            yield msg

        # Save assistant message
        assistant_message = Message(
            id=str(uuid4()),
            session_id=session_id,
            sequence=sequence + 1,
            role="assistant",
            content=assistant_content,
            parts=assistant_parts if assistant_parts else None,
            created_at=datetime.now(UTC),
        )
        await self._repository.save_message(assistant_message)

        # Update session with driver session ID if changed
        if driver_session_id and driver_session_id != session.driver_session_id:
            session.driver_session_id = driver_session_id
            session.updated_at = datetime.now(UTC)
            await self._repository.update_session(session)

        # Emit message complete event
        complete_event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_MESSAGE_COMPLETE,
            message="Assistant response complete",
            data={"message_id": assistant_message.id},
        )
        self._event_bus.emit(complete_event)

    async def _create_artifact_from_path(self, session_id: str, path: str) -> None:
        """Create and save an artifact from a file path.

        Args:
            session_id: Session that created the artifact.
            path: Path to the created file.
        """
        # Infer type from path
        artifact_type = self._infer_artifact_type(path)

        artifact = Artifact(
            id=str(uuid4()),
            session_id=session_id,
            type=artifact_type,
            path=path,
            title=None,  # Could extract from file content later
            created_at=datetime.now(UTC),
        )
        await self._repository.save_artifact(artifact)

        # Emit artifact created event
        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_ARTIFACT_CREATED,
            message=f"Artifact created: {path}",
            data={"artifact_id": artifact.id, "path": path, "type": artifact_type},
        )
        self._event_bus.emit(event)

    def _infer_artifact_type(self, path: str) -> str:
        """Infer artifact type from file path.

        Args:
            path: File path.

        Returns:
            Artifact type string.
        """
        path_lower = path.lower()
        if "design" in path_lower or "plans" in path_lower:
            return "design"
        elif "adr" in path_lower:
            return "adr"
        elif "spec" in path_lower:
            return "spec"
        elif "readme" in path_lower:
            return "readme"
        else:
            return "document"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestArtifactDetection -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/services/brainstorm.py tests/unit/server/services/test_brainstorm_service.py
git commit -m "feat(brainstorm): detect artifact creation from write_file tool calls"
```

---

## Phase 2c: Session Lifecycle

### Task 10: Add Handoff Endpoint

**Files:**
- Modify: `amelia/server/services/brainstorm.py` (add handoff_to_implementation)
- Modify: `amelia/server/routes/brainstorm.py` (add POST /sessions/{id}/handoff)

**Step 1: Write the failing test**

Add to `tests/unit/server/services/test_brainstorm_service.py`:

```python
class TestHandoff(TestBrainstormService):
    """Test handoff to implementation pipeline."""

    async def test_handoff_updates_session_status(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should update session status to completed."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="ready_for_handoff",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id="art-1", session_id="sess-1", type="design",
                path="docs/plans/design.md", created_at=now,
            )
        ]

        result = await service.handoff_to_implementation(
            session_id="sess-1",
            artifact_path="docs/plans/design.md",
        )

        assert result is not None
        # Session should be updated to completed
        update_calls = mock_repository.update_session.call_args_list
        updated_session = update_calls[-1][0][0]
        assert updated_session.status == "completed"

    async def test_handoff_returns_workflow_id(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should return a new workflow ID."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="ready_for_handoff",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id="art-1", session_id="sess-1", type="design",
                path="docs/plans/design.md", created_at=now,
            )
        ]

        result = await service.handoff_to_implementation(
            session_id="sess-1",
            artifact_path="docs/plans/design.md",
        )

        assert "workflow_id" in result
        assert len(result["workflow_id"]) == 36  # UUID

    async def test_handoff_artifact_not_found(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should raise error if artifact not found."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="ready_for_handoff",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = []  # No artifacts

        with pytest.raises(ValueError, match="Artifact not found"):
            await service.handoff_to_implementation(
                session_id="sess-1",
                artifact_path="docs/plans/design.md",
            )

    async def test_handoff_session_not_found(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should raise error if session not found."""
        mock_repository.get_session.return_value = None

        with pytest.raises(ValueError, match="Session not found"):
            await service.handoff_to_implementation(
                session_id="nonexistent",
                artifact_path="docs/plans/design.md",
            )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestHandoff -v`
Expected: FAIL with "AttributeError: 'BrainstormService' object has no attribute 'handoff_to_implementation'"

**Step 3: Write minimal implementation**

Add to `amelia/server/services/brainstorm.py`:

```python
    async def handoff_to_implementation(
        self,
        session_id: str,
        artifact_path: str,
        issue_title: str | None = None,
        issue_description: str | None = None,
    ) -> dict[str, str]:
        """Hand off brainstorming session to implementation pipeline.

        Args:
            session_id: Session to hand off.
            artifact_path: Path to the design artifact.
            issue_title: Optional title for the implementation issue.
            issue_description: Optional description for the implementation issue.

        Returns:
            Dict with workflow_id for the implementation pipeline.

        Raises:
            ValueError: If session or artifact not found.
        """
        session = await self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Validate artifact exists
        artifacts = await self._repository.get_artifacts(session_id)
        artifact = next((a for a in artifacts if a.path == artifact_path), None)
        if artifact is None:
            raise ValueError(f"Artifact not found: {artifact_path}")

        # Generate a workflow ID for the implementation
        # In the full implementation, this would create an actual workflow
        workflow_id = str(uuid4())

        # Update session status to completed
        session.status = "completed"
        session.updated_at = datetime.now(UTC)
        await self._repository.update_session(session)

        # Emit session completed event
        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_SESSION_COMPLETED,
            message=f"Session completed, handed off to implementation {workflow_id}",
            data={
                "session_id": session_id,
                "workflow_id": workflow_id,
                "artifact_path": artifact_path,
            },
        )
        self._event_bus.emit(event)

        return {"workflow_id": workflow_id, "status": "created"}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestHandoff -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/services/brainstorm.py tests/unit/server/services/test_brainstorm_service.py
git commit -m "feat(brainstorm): add handoff_to_implementation for pipeline transition"
```

---

### Task 11: Add Handoff Route Endpoint

**Files:**
- Modify: `amelia/server/routes/brainstorm.py` (add POST /sessions/{id}/handoff)

**Step 1: Write the failing test**

Add to `tests/unit/server/routes/test_brainstorm_routes.py`:

```python
class TestHandoff(TestBrainstormRoutes):
    """Test POST /api/brainstorm/sessions/{id}/handoff."""

    def test_handoff_success(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return workflow_id on successful handoff."""
        mock_service.handoff_to_implementation = AsyncMock(
            return_value={"workflow_id": "impl-123", "status": "created"}
        )

        response = client.post(
            "/api/brainstorm/sessions/sess-123/handoff",
            json={"artifact_path": "docs/plans/design.md"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "impl-123"
        assert data["status"] == "created"

    def test_handoff_session_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return 404 if session not found."""
        mock_service.handoff_to_implementation = AsyncMock(
            side_effect=ValueError("Session not found: nonexistent")
        )

        response = client.post(
            "/api/brainstorm/sessions/nonexistent/handoff",
            json={"artifact_path": "docs/plans/design.md"},
        )

        assert response.status_code == 404

    def test_handoff_artifact_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return 404 if artifact not found."""
        mock_service.handoff_to_implementation = AsyncMock(
            side_effect=ValueError("Artifact not found: missing.md")
        )

        response = client.post(
            "/api/brainstorm/sessions/sess-123/handoff",
            json={"artifact_path": "missing.md"},
        )

        assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_routes.py::TestHandoff -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Write minimal implementation**

Add to `amelia/server/routes/brainstorm.py`:

```python
class HandoffRequest(BaseModel):
    """Request to hand off session to implementation."""

    artifact_path: str
    issue_title: str | None = None
    issue_description: str | None = None


class HandoffResponse(BaseModel):
    """Response from handoff request."""

    workflow_id: str
    status: str


@router.post(
    "/sessions/{session_id}/handoff",
    response_model=HandoffResponse,
)
async def handoff_to_implementation(
    session_id: str,
    request: HandoffRequest,
    service: BrainstormService = Depends(get_brainstorm_service),
) -> HandoffResponse:
    """Hand off brainstorming session to implementation pipeline.

    Creates an implementation workflow from the design artifact.

    Args:
        session_id: Session to hand off.
        request: Handoff request with artifact path.
        service: Brainstorm service dependency.

    Returns:
        Handoff response with workflow ID.

    Raises:
        HTTPException: 404 if session or artifact not found.
    """
    try:
        result = await service.handoff_to_implementation(
            session_id=session_id,
            artifact_path=request.artifact_path,
            issue_title=request.issue_title,
            issue_description=request.issue_description,
        )
        return HandoffResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_routes.py::TestHandoff -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/brainstorm.py tests/unit/server/routes/test_brainstorm_routes.py
git commit -m "feat(brainstorm): add POST /sessions/{id}/handoff endpoint"
```

---

### Task 12: Wire Up Dependencies in main.py

**Files:**
- Modify: `amelia/server/main.py` (register brainstorm router and dependencies)

**Step 1: Write the failing test**

Create `tests/integration/server/test_brainstorm_integration.py`:

```python
"""Integration tests for brainstorming endpoints."""

import pytest
from fastapi.testclient import TestClient

from amelia.server.main import create_app


class TestBrainstormIntegration:
    """Test brainstorming endpoints are wired correctly."""

    @pytest.fixture
    async def app(self, temp_db_path):
        """Create app with real database."""
        app = create_app()
        # Override database path for testing
        # This would need proper setup in create_app
        yield app

    @pytest.fixture
    def client(self, app) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_brainstorm_routes_registered(self, client: TestClient) -> None:
        """Brainstorm routes should be accessible."""
        # Just check that the endpoint exists (will return 422 without body)
        response = client.post("/api/brainstorm/sessions", json={})
        # Should be 422 (validation error) not 404 (not found)
        assert response.status_code != 404

    def test_list_sessions_endpoint(self, client: TestClient) -> None:
        """List sessions endpoint should work."""
        response = client.get("/api/brainstorm/sessions")
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/server/test_brainstorm_integration.py -v`
Expected: FAIL (routes not registered, 404)

**Step 3: Write minimal implementation**

In `amelia/server/main.py`, add the following:

1. Import the brainstorm router and service:
```python
from amelia.server.routes.brainstorm import router as brainstorm_router
from amelia.server.routes.brainstorm import get_brainstorm_service, get_driver, get_cwd
from amelia.server.services.brainstorm import BrainstormService
from amelia.server.database.brainstorm_repository import BrainstormRepository
```

2. In the `create_app` function, after registering other routers:
```python
    app.include_router(brainstorm_router, prefix="/api/brainstorm")
```

3. In the lifespan or dependency setup, wire up the service:
```python
    # Create brainstorm repository and service
    brainstorm_repo = BrainstormRepository(db)
    brainstorm_service = BrainstormService(brainstorm_repo, event_bus)

    # Override dependencies
    app.dependency_overrides[get_brainstorm_service] = lambda: brainstorm_service
    app.dependency_overrides[get_driver] = lambda: driver  # Use existing driver
    app.dependency_overrides[get_cwd] = lambda: os.getcwd()
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/server/test_brainstorm_integration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/main.py tests/integration/server/test_brainstorm_integration.py
git commit -m "feat(brainstorm): wire up brainstorm routes and dependencies in main.py"
```

---

## Summary

This plan implements Phase 2a-2c of the Brainstorming Pipeline Backend:

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add brainstorming event types | `events.py`, tests |
| 2 | Create Pydantic models | `brainstorm.py` (models), tests |
| 3 | Create database schema | `connection.py`, tests |
| 4 | Create BrainstormRepository | `brainstorm_repository.py`, tests |
| 5 | Create BrainstormService | `brainstorm.py` (service), tests |
| 6 | Session CRUD endpoints | `brainstorm.py` (routes), tests |
| 7 | Message endpoint with driver | service + routes, tests |
| 8 | Message route endpoint | routes, tests |
| 9 | Artifact detection | service, tests |
| 10 | Handoff service method | service, tests |
| 11 | Handoff route endpoint | routes, tests |
| 12 | Wire up in main.py | main.py, integration tests |

Phase 3 (Dashboard UI) would be implemented separately after this backend work is complete.
