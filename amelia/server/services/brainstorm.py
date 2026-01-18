"""Service layer for brainstorming operations.

Handles business logic for brainstorming sessions, coordinating
between the repository, event bus, and Claude driver.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
)
from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    SessionStatus,
)
from amelia.server.models.events import EventType, WorkflowEvent


BRAINSTORMER_SYSTEM_PROMPT = """You are a collaborative design partner helping the user brainstorm and refine software designs.

Your role:
- Ask clarifying questions to understand requirements
- Suggest design patterns and architectural approaches
- Help identify edge cases and potential issues
- Produce clear, actionable design documents when ready

Keep responses focused and conversational. When the design is ready, offer to produce a formal document."""


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
        self._session_locks: dict[str, asyncio.Lock] = {}

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for a session.

        Args:
            session_id: Session to get lock for.

        Returns:
            Lock for the session.
        """
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

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

    async def get_session(self, session_id: str) -> BrainstormingSession | None:
        """Get a session by ID.

        Args:
            session_id: Session to retrieve.

        Returns:
            The session if found, None otherwise.
        """
        return await self._repository.get_session(session_id)

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
        # Clean up session lock to prevent memory leak
        self._session_locks.pop(session_id, None)

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

    async def send_message(
        self,
        session_id: str,
        content: str,
        driver: DriverInterface,
        cwd: str,
        assistant_message_id: str | None = None,
    ) -> AsyncIterator[WorkflowEvent]:
        """Send a message in a brainstorming session.

        Saves the user message, invokes the driver, streams events,
        and saves the assistant response.

        Uses a session-level lock to prevent race conditions when
        computing sequence numbers for concurrent sends.

        Args:
            session_id: Session to send message in.
            content: User message content.
            driver: LLM driver for generating response.
            cwd: Working directory for driver execution.
            assistant_message_id: Optional ID for the assistant message.
                If not provided, a UUID will be generated.

        Yields:
            WorkflowEvent for each driver message.

        Raises:
            ValueError: If session not found.
        """
        # Validate session exists
        session = await self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Acquire session lock to prevent sequence collisions under concurrent sends
        lock = self._get_session_lock(session_id)
        await lock.acquire()

        try:
            # Get next sequence number and save user message
            max_seq = await self._repository.get_max_sequence(session_id)
            user_sequence = max_seq + 1

            now = datetime.now(UTC)
            user_message = Message(
                id=str(uuid4()),
                session_id=session_id,
                sequence=user_sequence,
                role="user",
                content=content,
                created_at=now,
            )
            await self._repository.save_message(user_message)

            # Invoke driver and stream events
            assistant_content_parts: list[str] = []
            driver_session_id: str | None = None
            pending_write_files: dict[str, str] = {}  # tool_call_id -> path

            async for agentic_msg in driver.execute_agentic(
                prompt=content,
                cwd=cwd,
                session_id=session.driver_session_id,
                instructions=BRAINSTORMER_SYSTEM_PROMPT,
            ):
                # Convert to event and emit
                event = self._agentic_message_to_event(agentic_msg, session_id)
                self._event_bus.emit(event)
                yield event

                # Track write_file tool calls for artifact detection
                if (
                    agentic_msg.type == AgenticMessageType.TOOL_CALL
                    and agentic_msg.tool_name == "write_file"
                    and agentic_msg.tool_call_id
                    and agentic_msg.tool_input
                ):
                    path = agentic_msg.tool_input.get("path")
                    if path:
                        pending_write_files[agentic_msg.tool_call_id] = path

                # Detect successful write_file completions and create artifacts
                if (
                    agentic_msg.type == AgenticMessageType.TOOL_RESULT
                    and agentic_msg.tool_call_id in pending_write_files
                    and not agentic_msg.is_error
                ):
                    path = pending_write_files.pop(agentic_msg.tool_call_id)
                    artifact_event = await self._create_artifact_from_path(
                        session_id, path
                    )
                    yield artifact_event

                # Collect result content and session ID
                if agentic_msg.type == AgenticMessageType.RESULT:
                    if agentic_msg.content:
                        assistant_content_parts.append(agentic_msg.content)
                    if agentic_msg.session_id:
                        driver_session_id = agentic_msg.session_id

            # Update driver session ID if we got one
            if driver_session_id and driver_session_id != session.driver_session_id:
                session.driver_session_id = driver_session_id
                session.updated_at = datetime.now(UTC)
                await self._repository.update_session(session)

            # Save assistant message
            assistant_sequence = user_sequence + 1
            assistant_content = "\n".join(assistant_content_parts)
            assistant_message = Message(
                id=assistant_message_id or str(uuid4()),
                session_id=session_id,
                sequence=assistant_sequence,
                role="assistant",
                content=assistant_content,
                created_at=datetime.now(UTC),
            )
            await self._repository.save_message(assistant_message)
        finally:
            lock.release()

        # Emit message complete event
        complete_event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_MESSAGE_COMPLETE,
            message="Message complete",
            data={"message_id": assistant_message.id},
        )
        self._event_bus.emit(complete_event)
        yield complete_event

    def _agentic_message_to_event(
        self,
        agentic_msg: AgenticMessage,
        session_id: str,
    ) -> WorkflowEvent:
        """Convert an AgenticMessage to a WorkflowEvent.

        Args:
            agentic_msg: The agentic message from the driver.
            session_id: Session ID for the event.

        Returns:
            WorkflowEvent for the agentic message.
        """
        # Map agentic message types to brainstorm event types
        type_mapping = {
            AgenticMessageType.THINKING: EventType.BRAINSTORM_REASONING,
            AgenticMessageType.TOOL_CALL: EventType.BRAINSTORM_TOOL_CALL,
            AgenticMessageType.TOOL_RESULT: EventType.BRAINSTORM_TOOL_RESULT,
            AgenticMessageType.RESULT: EventType.BRAINSTORM_TEXT,
        }

        event_type = type_mapping.get(agentic_msg.type, EventType.BRAINSTORM_TEXT)

        # Build message from content
        message = agentic_msg.content or ""
        if agentic_msg.type == AgenticMessageType.TOOL_CALL:
            message = f"Calling {agentic_msg.tool_name or 'tool'}"
        elif agentic_msg.type == AgenticMessageType.TOOL_RESULT:
            message = agentic_msg.tool_output or f"Result from {agentic_msg.tool_name}"

        return WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=event_type,
            message=message,
            tool_name=agentic_msg.tool_name,
            tool_input=agentic_msg.tool_input,
            is_error=agentic_msg.is_error,
            model=agentic_msg.model,
        )

    async def _create_artifact_from_path(
        self, session_id: str, path: str
    ) -> WorkflowEvent:
        """Create and save an artifact from a file path.

        Args:
            session_id: Session that produced the artifact.
            path: File path of the artifact.

        Returns:
            WorkflowEvent for artifact creation.
        """
        artifact_type = self._infer_artifact_type(path)
        now = datetime.now(UTC)

        artifact = Artifact(
            id=str(uuid4()),
            session_id=session_id,
            type=artifact_type,
            path=path,
            created_at=now,
        )
        await self._repository.save_artifact(artifact)

        # Emit artifact created event
        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=now,
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_ARTIFACT_CREATED,
            message=f"Created artifact: {path}",
            data={"artifact_id": artifact.id, "path": path, "type": artifact_type},
        )
        self._event_bus.emit(event)
        return event

    def _infer_artifact_type(self, path: str) -> str:
        """Infer artifact type from file path.

        Args:
            path: File path to analyze.

        Returns:
            Artifact type (design, adr, spec, readme, document).
        """
        path_lower = path.lower()

        # Check for ADR pattern
        if "/adr/" in path_lower or "adr-" in path_lower:
            return "adr"

        # Check for spec pattern
        if "/spec/" in path_lower or "-spec" in path_lower or "_spec" in path_lower:
            return "spec"

        # Check for readme pattern
        if "readme" in path_lower:
            return "readme"

        # Check for design/plan pattern
        if (
            "/design/" in path_lower
            or "/plans/" in path_lower
            or "-design" in path_lower
            or "_design" in path_lower
        ):
            return "design"

        # Default to document
        return "document"

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
