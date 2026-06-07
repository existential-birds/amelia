"""Service layer for brainstorming operations.

Handles business logic for brainstorming sessions, coordinating
between the repository, event bus, and Claude driver.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from amelia.server.orchestrator.service import OrchestratorService
from uuid import uuid4

from loguru import logger
from pydantic import ValidationError

from amelia.core.constants import resolve_plan_path
from amelia.core.text import slugify
from amelia.core.types import AskUserQuestionPayload
from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
)
from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    MessageRole,
    MessageUsage,
    SessionStatus,
)
from amelia.server.models.events import EventDomain, EventType, WorkflowEvent
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.tokens import calculate_token_cost
from amelia.server.services.brainstormer_agent import (
    BRAINSTORMER_USER_PROMPT_TEMPLATE,
    BrainstormerFilesystemMiddleware,
    build_brainstormer_instructions,
)


# Default plan path pattern used when no profile is available
_DEFAULT_PLAN_PATH_PATTERN = "docs/plans/{date}-{issue_key}.md"


async def _build_message_usage(
    driver_usage: DriverUsage,
    fallback_model: str | None = None,
) -> MessageUsage:
    """Build MessageUsage from driver usage, computing cost if needed.

    When the driver doesn't provide cost_usd, falls back to
    calculate_token_cost using cached pricing data. Uses fallback_model
    when driver_usage.model is not set.
    """
    cost = driver_usage.cost_usd or 0.0

    # Compute cost from cached pricing if driver didn't provide it
    model = driver_usage.model or fallback_model
    if not cost and model:
        cost = await calculate_token_cost(
            model=model,
            input_tokens=driver_usage.input_tokens or 0,
            output_tokens=driver_usage.output_tokens or 0,
            cache_read_tokens=driver_usage.cache_read_tokens or 0,
            cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
        )

    return MessageUsage(
        input_tokens=driver_usage.input_tokens or 0,
        output_tokens=driver_usage.output_tokens or 0,
        cost_usd=cost,
    )


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
        driver_cleanup: Callable[[str, str], Awaitable[bool]] | None = None,
        profile_repo: ProfileRepository | None = None,
    ) -> None:
        """Initialize service.

        Args:
            repository: Database repository.
            event_bus: Event bus for broadcasting.
            driver_cleanup: Optional async callback to clean up driver sessions.
                Called with (driver_type, driver_session_id) when sessions
                are deleted or reach terminal status.
            profile_repo: Repository for profile lookup. Used to populate
                driver_type when creating sessions.
        """
        self._repository = repository
        self._event_bus = event_bus
        self._session_locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._driver_cleanup = driver_cleanup
        self._profile_repo = profile_repo

    def emit_event(self, event: WorkflowEvent) -> None:
        """Emit a workflow event to the event bus.

        Args:
            event: The event to emit.
        """
        self._event_bus.emit(event)

    def _get_session_lock(self, session_id: uuid.UUID) -> asyncio.Lock:
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
        # Look up driver type from brainstormer agent config if available
        driver_type: str | None = None
        if self._profile_repo is not None:
            profile = await self._profile_repo.get_profile(profile_id)
            if profile is not None and "brainstormer" in profile.agents:
                driver_type = profile.agents["brainstormer"].driver

        now = datetime.now(UTC)
        session = BrainstormingSession(
            id=uuid4(),
            profile_id=profile_id,
            driver_type=driver_type,
            status=SessionStatus.ACTIVE,
            topic=topic,
            created_at=now,
            updated_at=now,
        )

        await self._repository.create_session(session)

        # Emit session created event
        event = WorkflowEvent(
            id=uuid4(),
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

    async def get_session(self, session_id: uuid.UUID) -> BrainstormingSession | None:
        """Get a session by ID.

        Args:
            session_id: Session to retrieve.

        Returns:
            The session if found, None otherwise.
        """
        return await self._repository.get_session(session_id)

    async def get_session_with_history(
        self, session_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Get session with messages, artifacts, and usage summary.

        Args:
            session_id: Session to retrieve.

        Returns:
            Dict with session (including usage_summary), messages, and artifacts,
            or None if not found.
        """
        session = await self._repository.get_session(session_id)
        if session is None:
            return None

        messages = await self._repository.get_messages(session_id)
        artifacts = await self._repository.get_artifacts(session_id)

        # Fetch and attach usage summary to session
        usage_summary = await self._repository.get_session_usage(session_id)
        session.usage_summary = usage_summary

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

    async def _cleanup_driver_session(
        self, session: BrainstormingSession | None
    ) -> None:
        """Clean up a session's driver resources, if any.

        No-op unless a cleanup callback is wired and the session carries both
        driver_type and driver_session_id. Cleanup failures are logged, not
        raised, so caller flow (delete, status change) is never blocked.
        """
        if not (
            self._driver_cleanup
            and session
            and session.driver_type
            and session.driver_session_id
        ):
            return
        try:
            await self._driver_cleanup(session.driver_type, session.driver_session_id)
        except Exception as e:
            logger.warning(
                "Failed to clean up driver session",
                session_id=session.id,
                driver_session_id=session.driver_session_id,
                error=str(e),
            )

    async def delete_session(self, session_id: uuid.UUID) -> None:
        """Delete a session.

        Args:
            session_id: Session to delete.
        """
        # Fetch session first to get driver_session_id for cleanup
        session = await self._repository.get_session(session_id)
        await self._cleanup_driver_session(session)

        await self._repository.delete_session(session_id)
        # Clean up session lock to prevent memory leak
        self._session_locks.pop(session_id, None)

    async def update_session_status(
        self, session_id: uuid.UUID, status: SessionStatus
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

        # Clean up when session reaches terminal status
        if status in (SessionStatus.COMPLETED, SessionStatus.FAILED):
            self._session_locks.pop(session_id, None)
            await self._cleanup_driver_session(session)

        return session

    async def update_driver_session_id(
        self, session_id: uuid.UUID, driver_session_id: str
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
        session_id: uuid.UUID,
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

        For the first message in a session (detected via max_seq == 0),
        the prompt is wrapped with "Help me design:" template.
        BRAINSTORMER_SYSTEM_PROMPT is always passed as instructions.

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
        async with lock:
            # Get next sequence number and save user message
            max_seq = await self._repository.get_max_sequence(session_id)
            user_sequence = max_seq + 1

            # Detect first message and format prompt accordingly
            is_first_message = max_seq == 0
            if is_first_message:
                formatted_prompt = BRAINSTORMER_USER_PROMPT_TEMPLATE.format(
                    idea=content
                )
            else:
                formatted_prompt = content

            now = datetime.now(UTC)
            user_message = Message(
                id=uuid4(),
                session_id=session_id,
                sequence=user_sequence,
                role=MessageRole.USER,
                content=content,  # Store original content, not formatted prompt
                created_at=now,
            )
            await self._repository.save_message(user_message)

            # Generate assistant message ID before streaming so events can reference it
            if assistant_message_id:
                try:
                    resolved_message_id = uuid.UUID(assistant_message_id)
                except (ValueError, AttributeError) as e:
                    raise ValueError(f"Invalid assistant_message_id: {assistant_message_id!r}") from e
            else:
                resolved_message_id = uuid4()

            # Invoke driver and stream events
            assistant_content_parts: list[str] = []
            driver_session_id: str | None = None
            suppressed_tool_ids: set[str] = set()  # tool calls converted to text

            plan_path = await self._resolve_plan_path(session, is_first_message)
            instructions = build_brainstormer_instructions(plan_path)

            # Create restricted middleware for brainstormer
            # The middleware will be bound to the backend created by the driver
            brainstormer_middleware = [BrainstormerFilesystemMiddleware()]

            async for agentic_msg in driver.execute_agentic(
                prompt=formatted_prompt,
                cwd=cwd,
                session_id=session.driver_session_id,
                instructions=instructions,
                middleware=brainstormer_middleware,
            ):
                # Suppress tool_result events for converted ask_user_question calls
                if (
                    agentic_msg.type == AgenticMessageType.TOOL_RESULT
                    and agentic_msg.tool_call_id in suppressed_tool_ids
                ):
                    continue

                # Convert to event and emit
                event = self._agentic_message_to_event(
                    agentic_msg, session_id, resolved_message_id
                )

                # Only suppress tool results after successful ask_user conversion
                if (
                    agentic_msg.type == AgenticMessageType.TOOL_CALL
                    and agentic_msg.tool_name == "ask_user_question"
                    and agentic_msg.tool_call_id
                    and event.event_type == EventType.BRAINSTORM_ASK_USER
                ):
                    suppressed_tool_ids.add(agentic_msg.tool_call_id)

                self._event_bus.emit(event)
                yield event

                # Collect result content and session ID
                if agentic_msg.type == AgenticMessageType.RESULT:
                    if agentic_msg.content:
                        assistant_content_parts.append(agentic_msg.content)
                    if agentic_msg.session_id:
                        driver_session_id = agentic_msg.session_id

            # Detect artifact by checking if the agent wrote the plan file
            artifact_event = await self._detect_artifact_event(
                session_id, cwd, plan_path
            )
            if artifact_event:
                yield artifact_event

            # Update driver session ID if we got one
            if driver_session_id and driver_session_id != session.driver_session_id:
                session.driver_session_id = driver_session_id
                session.updated_at = datetime.now(UTC)
                await self._repository.update_session(session)

            # Extract token usage from driver
            message_usage: MessageUsage | None = None
            driver_usage = driver.get_usage()
            if driver_usage:
                message_usage = await _build_message_usage(
                    driver_usage,
                    fallback_model=getattr(driver, "model", None),
                )

            # Save assistant message
            assistant_sequence = user_sequence + 1
            assistant_content = "\n".join(assistant_content_parts)
            assistant_message = Message(
                id=resolved_message_id,
                session_id=session_id,
                sequence=assistant_sequence,
                role=MessageRole.ASSISTANT,
                content=assistant_content,
                usage=message_usage,
                created_at=datetime.now(UTC),
            )
            await self._repository.save_message(assistant_message)

        # Emit message complete event
        complete_event = await self._build_complete_event(
            session_id, assistant_message.id, message_usage
        )
        self._event_bus.emit(complete_event)
        yield complete_event

    async def _resolve_plan_path(
        self, session: BrainstormingSession, is_first_message: bool
    ) -> str:
        """Resolve (and persist) the design-doc output path for a session.

        On the first message—or whenever the session has no output path yet—
        builds a path from the profile's plan_path_pattern and a topic slug,
        stores it on the session, and persists. Otherwise returns the existing
        path unchanged.
        """
        plan_path_pattern = _DEFAULT_PLAN_PATH_PATTERN
        if self._profile_repo is not None:
            profile = await self._profile_repo.get_profile(session.profile_id)
            if profile is not None:
                plan_path_pattern = profile.plan_path_pattern

        if is_first_message or not session.output_artifact_path:
            sid_prefix = str(session.id)[:8]
            topic_slug = slugify(session.topic) if session.topic else ""
            topic_slug = (
                f"{topic_slug}-{sid_prefix}" if topic_slug else f"brainstorm-{sid_prefix}"
            )
            plan_path = resolve_plan_path(plan_path_pattern, topic_slug)
            session.output_artifact_path = plan_path
            session.updated_at = datetime.now(UTC)
            await self._repository.update_session(session)
        else:
            plan_path = session.output_artifact_path
        return plan_path

    async def _detect_artifact_event(
        self, session_id: uuid.UUID, cwd: str, plan_path: str
    ) -> WorkflowEvent | None:
        """Return an artifact-created event if the agent wrote the plan file.

        Returns None when no file exists at the resolved plan path, so the
        streaming caller can decide whether to yield.
        """
        abs_plan_path = Path(cwd) / plan_path
        if not abs_plan_path.is_file():
            return None
        logger.info("Artifact detected", plan_path=plan_path)
        return await self._create_artifact_from_path(session_id, plan_path)

    async def _build_complete_event(
        self,
        session_id: uuid.UUID,
        message_id: uuid.UUID,
        message_usage: MessageUsage | None,
    ) -> WorkflowEvent:
        """Assemble the BRAINSTORM_MESSAGE_COMPLETE event.

        Includes per-message usage when available plus the aggregated session
        usage summary fetched from the repository.
        """
        complete_data: dict[str, Any] = {
            "session_id": str(session_id),
            "message_id": message_id,
        }
        if message_usage:
            complete_data["usage"] = message_usage.model_dump()

        session_usage = await self._repository.get_session_usage(session_id)
        if session_usage:
            complete_data["session_usage"] = session_usage.model_dump()

        return WorkflowEvent(
            id=uuid4(),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_MESSAGE_COMPLETE,
            message="Message complete",
            data=complete_data,
            domain=EventDomain.BRAINSTORM,
        )

    @staticmethod
    def _format_ask_user_question(payload: AskUserQuestionPayload) -> str:
        """Format an AskUserQuestion tool call as readable markdown.

        Extracts question text and options from the tool input and
        formats them as a markdown list the user can read in the chat.

        Args:
            payload: The typed AskUserQuestionPayload from the tool call.

        Returns:
            Markdown-formatted question text.
        """
        parts: list[str] = []
        for q in payload.questions:
            if q.question:
                parts.append(f"**{q.question}**\n")
            for opt in q.options:
                if opt.description:
                    parts.append(f"- **{opt.label}** — {opt.description}")
                else:
                    parts.append(f"- **{opt.label}**")
        return "\n".join(parts)

    def _agentic_message_to_event(
        self,
        agentic_msg: AgenticMessage,
        session_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> WorkflowEvent:
        """Convert an AgenticMessage to a WorkflowEvent.

        Args:
            agentic_msg: The agentic message from the driver.
            session_id: Session ID for the event.
            message_id: Assistant message ID for the event.

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

        # Intercept ask_user_question tool calls and emit as interactive
        # BRAINSTORM_ASK_USER events with structured question payload.
        # Falls back to plain BRAINSTORM_TEXT if the payload is malformed.
        if (
            agentic_msg.type == AgenticMessageType.TOOL_CALL
            and agentic_msg.tool_name == "ask_user_question"
            and agentic_msg.tool_input
        ):
            try:
                payload = AskUserQuestionPayload(**agentic_msg.tool_input)
                formatted = self._format_ask_user_question(payload)
                if not formatted:
                    logger.warning(
                        "Valid ask_user_question payload produced empty output",
                        session_id=session_id,
                    )
                else:
                    logger.debug(
                        "Emitting interactive ask_user event",
                        session_id=session_id,
                    )
                    return WorkflowEvent(
                        id=uuid4(),
                        workflow_id=session_id,
                        sequence=0,
                        timestamp=datetime.now(UTC),
                        agent="brainstormer",
                        event_type=EventType.BRAINSTORM_ASK_USER,
                        message=formatted,
                        model=agentic_msg.model,
                        domain=EventDomain.BRAINSTORM,
                        data={
                            "session_id": str(session_id),
                            "message_id": str(message_id),
                            "text": formatted,
                            "questions": [q.model_dump() for q in payload.questions],
                        },
                    )
            except ValidationError:
                logger.warning(
                    "Malformed ask_user_question payload, falling back to text",
                    session_id=session_id,
                    tool_input=agentic_msg.tool_input,
                )

        # Build message from content
        message = agentic_msg.content or ""
        if agentic_msg.type == AgenticMessageType.TOOL_CALL:
            message = f"Calling {agentic_msg.tool_name or 'tool'}"
        elif agentic_msg.type == AgenticMessageType.TOOL_RESULT:
            message = agentic_msg.tool_output or f"Result from {agentic_msg.tool_name}"

        return WorkflowEvent(
            id=uuid4(),
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
            domain=EventDomain.BRAINSTORM,
            data={
                "session_id": str(session_id),
                "message_id": str(message_id),
                "text": message,
                "tool_call_id": agentic_msg.tool_call_id,
                "tool_name": agentic_msg.tool_name,
                "input": agentic_msg.tool_input,
                "output": agentic_msg.tool_output,
                "error": agentic_msg.tool_output if agentic_msg.is_error else None,
            },
        )

    async def _create_artifact_from_path(
        self, session_id: uuid.UUID, path: str
    ) -> WorkflowEvent:
        """Create an artifact record from a file path.

        Args:
            session_id: Session ID for the artifact.
            path: File path that was written.

        Returns:
            WorkflowEvent for artifact creation.
        """
        artifact_type = self._infer_artifact_type(path)
        now = datetime.now(UTC)

        artifact = Artifact(
            id=uuid4(),
            session_id=session_id,
            type=artifact_type,
            path=path,
            created_at=now,
        )
        await self._repository.save_artifact(artifact)

        # Emit artifact created event with flat fields matching BrainstormArtifact type
        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=session_id,
            sequence=0,
            timestamp=now,
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_ARTIFACT_CREATED,
            message=f"Created artifact: {path}",
            data={
                "id": artifact.id,
                "session_id": session_id,
                "type": artifact.type,
                "path": artifact.path,
                "title": artifact.title,
                "created_at": artifact.created_at.isoformat(),
            },
            domain=EventDomain.BRAINSTORM,
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
        session_id: uuid.UUID,
        artifact_path: str,
        issue_title: str | None = None,
        issue_description: str | None = None,
        orchestrator: "OrchestratorService | None" = None,
        worktree_path: str | None = None,
    ) -> dict[str, Any]:
        """Hand off brainstorming session to implementation pipeline.

        Args:
            session_id: Session to hand off.
            artifact_path: Path to the design artifact.
            issue_title: Optional title for the implementation issue.
            issue_description: Optional description for the implementation issue.
            orchestrator: Orchestrator service for creating workflows.
            worktree_path: Path to the worktree for loading settings.

        Returns:
            Dict with workflow_id for the implementation pipeline.

        Raises:
            ValueError: If session or artifact not found.
            NotImplementedError: If tracker is not noop.
        """
        session = await self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Validate artifact exists
        artifacts = await self._repository.get_artifacts(session_id)
        artifact = next((a for a in artifacts if a.path == artifact_path), None)
        if artifact is None:
            raise ValueError(f"Artifact not found: {artifact_path}")

        if orchestrator is None or worktree_path is None:
            raise ValueError(
                "orchestrator and worktree_path are required for handoff_to_implementation"
            )

        # Generate short, readable issue ID
        base_title = issue_title or session.topic or ""
        slug = slugify(base_title, max_length=15) if base_title else ""
        sid_prefix = str(session_id)[:8]
        issue_id = f"{slug}-{sid_prefix}" if slug else f"brainstorm-{sid_prefix}"

        # Queue workflow with orchestrator
        request = CreateWorkflowRequest(
            issue_id=issue_id,
            worktree_path=worktree_path,
            task_title=issue_title or f"Implement design from {artifact_path}",
            task_description=issue_description,
            start=False,  # Queue only, don't start
            artifact_path=artifact_path,
        )
        workflow_id = await orchestrator.queue_workflow(request)

        # Update session status to completed
        session.status = SessionStatus.COMPLETED
        session.updated_at = datetime.now(UTC)
        await self._repository.update_session(session)

        # Emit session completed event
        event = WorkflowEvent(
            id=uuid4(),
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
