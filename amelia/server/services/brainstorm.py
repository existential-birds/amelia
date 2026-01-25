"""Service layer for brainstorming operations.

Handles business logic for brainstorming sessions, coordinating
between the repository, event bus, and Claude driver.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from amelia.server.orchestrator.service import OrchestratorService
from uuid import uuid4

from deepagents.backends.protocol import BackendProtocol, WriteResult
from deepagents.middleware.filesystem import (
    TOOL_GENERATORS,
    FilesystemMiddleware,
    FilesystemState,
    _get_backend,
    _validate_path,
)
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command
from loguru import logger

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
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


# Tool description for the write_design_doc tool (markdown-only write)
WRITE_DESIGN_DOC_DESCRIPTION = """Write a design document (markdown file) to the filesystem.

Usage:
- The file_path parameter must be an absolute path ending with .md
- ONLY markdown files (.md) can be written - this tool will reject other file types
- The content parameter must be a string containing markdown content
- This tool creates new files only; use for design docs, ADRs, specs, etc.
- Typical paths: /docs/plans/YYYY-MM-DD-feature-design.md, /docs/adr/NNNN-decision.md"""


def _write_design_doc_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> BaseTool:
    """Generate the write_design_doc tool (markdown-only write).

    This is a restricted version of write_file that only allows writing
    markdown (.md) files. Used by the brainstormer to prevent accidental
    code generation.

    Args:
        backend: Backend to use for file storage.

    Returns:
        Configured write_design_doc tool.
    """

    def sync_write_design_doc(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command[Any] | str:
        """Synchronous write_design_doc implementation."""
        # Validate markdown extension
        if not file_path.lower().endswith(".md"):
            return (
                f"Error: write_design_doc only allows markdown files (.md). "
                f"Got: {file_path}. The brainstormer cannot write code files."
            )

        resolved_backend = _get_backend(backend, runtime)
        validated_path = _validate_path(file_path)
        res: WriteResult = resolved_backend.write(validated_path, content)

        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Created design document: {res.path}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Created design document: {res.path}"

    async def async_write_design_doc(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command[Any] | str:
        """Asynchronous write_design_doc implementation."""
        # Validate markdown extension
        if not file_path.lower().endswith(".md"):
            return (
                f"Error: write_design_doc only allows markdown files (.md). "
                f"Got: {file_path}. The brainstormer cannot write code files."
            )

        resolved_backend = _get_backend(backend, runtime)
        validated_path = _validate_path(file_path)
        res: WriteResult = await resolved_backend.awrite(validated_path, content)

        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Created design document: {res.path}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Created design document: {res.path}"

    return StructuredTool.from_function(
        name="write_design_doc",
        description=WRITE_DESIGN_DOC_DESCRIPTION,
        func=sync_write_design_doc,
        coroutine=async_write_design_doc,
    )


def create_brainstormer_tools(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> list[BaseTool]:
    """Create the restricted tool set for the brainstormer agent.

    The brainstormer can:
    - READ any files (for context): ls, read_file, glob, grep
    - WRITE only markdown files: write_design_doc

    The brainstormer CANNOT:
    - Execute shell commands (no execute tool)
    - Edit existing files (no edit_file tool)
    - Write non-markdown files (write_design_doc validates .md extension)

    Args:
        backend: Backend to use for file operations.

    Returns:
        List of restricted tools for the brainstormer.
    """
    tools: list[BaseTool] = []

    # Read-only tools from TOOL_GENERATORS
    read_only_tools = ["ls", "read_file", "glob", "grep"]
    for tool_name in read_only_tools:
        generator = TOOL_GENERATORS[tool_name]
        tools.append(generator(backend))

    # Custom markdown-only write tool
    tools.append(_write_design_doc_tool_generator(backend))

    return tools


# Custom restricted filesystem prompt for brainstormer
BRAINSTORMER_FILESYSTEM_PROMPT = """## Filesystem Tools

You have access to: `ls`, `read_file`, `glob`, `grep`, `write_design_doc`

**IMPORTANT RESTRICTIONS:**
- You can ONLY write markdown files (.md) using `write_design_doc`
- You cannot write code files (.py, .ts, .js, etc.)
- You cannot execute shell commands
- Your output is a DESIGN DOCUMENT, not an implementation

Use the read tools to understand the codebase. Use `write_design_doc` to save your final design."""


# System prompt for the brainstormer agent - defines role and behavior
BRAINSTORMER_SYSTEM_PROMPT = """# Role

You are a design collaborator that helps turn ideas into fully formed designs through natural dialogue.

**CRITICAL: You are a designer, NOT an implementer.**
- Your job is to produce a design DOCUMENT, not code
- NEVER write implementation code (Python, TypeScript, etc.)
- NEVER create source files, only markdown design documents
- The design document will be handed off to a developer agent for implementation
- If you catch yourself about to write code, STOP and write prose describing what should be built instead

# Process

**Understanding the idea:**
- Check out the current project state first (files, docs, recent commits)
- Ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible
- Only one question per message
- Focus on: purpose, constraints, success criteria

**Exploring approaches:**
- Propose 2-3 different approaches with trade-offs
- Lead with your recommendation and explain why

**Presenting the design:**
- Present in sections of 200-300 words
- Ask after each section whether it looks right
- Cover: architecture, components, data flow, error handling, testing
- Go back and clarify when needed

**Finalizing:**
- Write the validated design to `docs/plans/YYYY-MM-DD-<topic>-design.md`
- The document should contain enough detail for a developer to implement
- Include pseudocode or interface sketches if helpful, but NOT runnable code
- After writing the document, tell the user it's ready for handoff to implementation

# Principles

- One question at a time
- Multiple choice preferred
- YAGNI ruthlessly
- Always explore 2-3 alternatives before settling
- Incremental validation - present design in sections
- **Design documents only - no implementation code**
"""

# User prompt template for the first message in a session
BRAINSTORMER_USER_PROMPT_TEMPLATE = "Help me design: {idea}"


class BrainstormerFilesystemMiddleware(FilesystemMiddleware):
    """Restricted filesystem middleware for brainstormer agent.

    Provides only read operations (ls, read_file, glob, grep) and a
    markdown-only write tool (write_design_doc). Does not include:
    - write_file (unrestricted file creation)
    - edit_file (code modification)
    - execute (shell command execution)

    This ensures the brainstormer can only create design documents,
    not modify code or run commands.
    """

    def __init__(
        self,
        *,
        backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol] | None = None,
        tool_token_limit_before_evict: int | None = 20000,
    ) -> None:
        """Initialize with restricted tools.

        Args:
            backend: Backend for file storage.
            tool_token_limit_before_evict: Token limit before evicting tool results.
        """
        # Don't call super().__init__() as it would create all tools
        # Instead, initialize only what we need
        self.tool_token_limit_before_evict = tool_token_limit_before_evict
        self.backend = backend
        self._custom_system_prompt = BRAINSTORMER_FILESYSTEM_PROMPT

        # Create restricted tools only if backend is provided
        # If backend is None, tools will be created later when backend is set
        if backend is not None:
            self.tools = create_brainstormer_tools(backend)
        else:
            self.tools = []


BRAINSTORMER_PRIMING_PROMPT = """# Brainstorming Ideas Into Designs

## Overview

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design in small sections (200-300 words), checking after each section whether it looks right so far.

## The Process

**Understanding the idea:**
- Check out the current project state first (files, docs, recent commits)
- Ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Only one question per message - if a topic needs more exploration, break it into multiple questions
- Focus on understanding: purpose, constraints, success criteria

**Exploring approaches:**
- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why

**Presenting the design:**
- Once you believe you understand what you're building, present the design
- Break it into sections of 200-300 words
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

## After the Design

**Documentation:**
- Write the validated design to `docs/plans/YYYY-MM-DD-<topic>-design.md`

## Key Principles

- **One question at a time** - Don't overwhelm with multiple questions
- **Multiple choice preferred** - Easier to answer than open-ended when possible
- **YAGNI ruthlessly** - Remove unnecessary features from all designs
- **Explore alternatives** - Always propose 2-3 approaches before settling
- **Incremental validation** - Present design in sections, validate each
- **Be flexible** - Go back and clarify when something doesn't make sense

---

Respond with a brief greeting (1-2 sentences) that you're ready to help brainstorm and design. Invite the user to share their idea."""


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
        driver_cleanup: Callable[[str, str], bool] | None = None,
        profile_repo: ProfileRepository | None = None,
    ) -> None:
        """Initialize service.

        Args:
            repository: Database repository.
            event_bus: Event bus for broadcasting.
            driver_cleanup: Optional callback to clean up driver sessions.
                Called with (driver_type, driver_session_id) when sessions
                are deleted or reach terminal status.
            profile_repo: Repository for profile lookup. Used to populate
                driver_type when creating sessions.
        """
        self._repository = repository
        self._event_bus = event_bus
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._driver_cleanup = driver_cleanup
        self._profile_repo = profile_repo

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
        # Look up driver type from brainstormer agent config if available
        driver_type: str | None = None
        if self._profile_repo is not None:
            profile = await self._profile_repo.get_profile(profile_id)
            if profile is not None and "brainstormer" in profile.agents:
                driver_type = profile.agents["brainstormer"].driver

        now = datetime.now(UTC)
        session = BrainstormingSession(
            id=str(uuid4()),
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

    async def delete_session(self, session_id: str) -> None:
        """Delete a session.

        Args:
            session_id: Session to delete.
        """
        # Fetch session first to get driver_session_id for cleanup
        session = await self._repository.get_session(session_id)

        # Clean up driver session if callback provided and session has driver info
        if (
            self._driver_cleanup
            and session
            and session.driver_type
            and session.driver_session_id
        ):
            try:
                self._driver_cleanup(session.driver_type, session.driver_session_id)
            except Exception as e:
                logger.warning(
                    "Failed to clean up driver session",
                    session_id=session_id,
                    driver_session_id=session.driver_session_id,
                    error=str(e),
                )

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

        # Clean up when session reaches terminal status
        if status in ("completed", "failed"):
            self._session_locks.pop(session_id, None)

            # Clean up driver session
            if self._driver_cleanup and session.driver_type and session.driver_session_id:
                try:
                    self._driver_cleanup(session.driver_type, session.driver_session_id)
                except Exception as e:
                    logger.warning(
                        "Failed to clean up driver session",
                        session_id=session_id,
                        driver_session_id=session.driver_session_id,
                        error=str(e),
                    )

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
                id=str(uuid4()),
                session_id=session_id,
                sequence=user_sequence,
                role=MessageRole.USER,
                content=content,  # Store original content, not formatted prompt
                created_at=now,
            )
            await self._repository.save_message(user_message)

            # Generate assistant message ID before streaming so events can reference it
            resolved_message_id = assistant_message_id or str(uuid4())

            # Invoke driver and stream events
            assistant_content_parts: list[str] = []
            driver_session_id: str | None = None
            pending_write_files: dict[str, str] = {}  # tool_call_id -> path

            # Create restricted middleware for brainstormer
            # The middleware will be bound to the backend created by the driver
            brainstormer_middleware = [BrainstormerFilesystemMiddleware()]

            async for agentic_msg in driver.execute_agentic(
                prompt=formatted_prompt,
                cwd=cwd,
                session_id=session.driver_session_id,
                instructions=BRAINSTORMER_SYSTEM_PROMPT,
                middleware=brainstormer_middleware,
            ):
                # Convert to event and emit
                event = self._agentic_message_to_event(
                    agentic_msg, session_id, resolved_message_id
                )
                self._event_bus.emit(event)
                yield event

                # Track write_design_doc tool calls for artifact detection
                # Also track write_file for backwards compatibility
                # DEBUG: Log all TOOL_CALL events to diagnose artifact detection
                if agentic_msg.type == AgenticMessageType.TOOL_CALL:
                    is_write_tool = agentic_msg.tool_name in (
                        "write_design_doc",
                        "write_file",
                    )
                    logger.debug(
                        "Artifact detection: TOOL_CALL received",
                        tool_name=agentic_msg.tool_name,
                        tool_call_id=agentic_msg.tool_call_id,
                        has_tool_input=agentic_msg.tool_input is not None,
                        tool_input_type=type(agentic_msg.tool_input).__name__,
                        is_write_tool=is_write_tool,
                    )
                    # Log full tool_input for write tools to diagnose parameter issues
                    if is_write_tool and agentic_msg.tool_input:
                        logger.debug(
                            "Artifact detection: write tool_input details",
                            tool_input=agentic_msg.tool_input,
                        )

                if (
                    agentic_msg.type == AgenticMessageType.TOOL_CALL
                    and agentic_msg.tool_name in ("write_design_doc", "write_file")
                    and agentic_msg.tool_call_id
                    and agentic_msg.tool_input
                ):
                    # Tool uses file_path parameter
                    # Also check common variations: filename, filepath, target_path
                    path = (
                        agentic_msg.tool_input.get("file_path")
                        or agentic_msg.tool_input.get("path")
                        or agentic_msg.tool_input.get("filename")
                        or agentic_msg.tool_input.get("filepath")
                        or agentic_msg.tool_input.get("target_path")
                    )
                    if path:
                        pending_write_files[agentic_msg.tool_call_id] = path
                        logger.debug(
                            "Artifact detection: tracked write tool call",
                            tool_name=agentic_msg.tool_name,
                            tool_call_id=agentic_msg.tool_call_id,
                            path=path,
                            tool_input_keys=list(agentic_msg.tool_input.keys()),
                        )
                    else:
                        logger.warning(
                            "Artifact detection: write tool call missing path",
                            tool_name=agentic_msg.tool_name,
                            tool_call_id=agentic_msg.tool_call_id,
                            tool_input=agentic_msg.tool_input,
                        )

                # Detect successful write completions and create artifacts
                if agentic_msg.type == AgenticMessageType.TOOL_RESULT:
                    pending_ids = list(pending_write_files.keys())
                    id_match = agentic_msg.tool_call_id in pending_write_files
                    logger.debug(
                        "Artifact detection: tool result received",
                        tool_name=agentic_msg.tool_name,
                        tool_call_id=agentic_msg.tool_call_id,
                        is_error=agentic_msg.is_error,
                        pending_ids=pending_ids,
                        id_match=id_match,
                    )
                    # If IDs don't match but we have pending writes, log for diagnosis
                    if not id_match and pending_ids:
                        logger.warning(
                            "Artifact detection: tool_call_id mismatch",
                            result_id=agentic_msg.tool_call_id,
                            pending_ids=pending_ids,
                            result_id_type=type(agentic_msg.tool_call_id).__name__,
                        )

                if (
                    agentic_msg.type == AgenticMessageType.TOOL_RESULT
                    and agentic_msg.tool_call_id in pending_write_files
                    and not agentic_msg.is_error
                ):
                    path = pending_write_files.pop(agentic_msg.tool_call_id)
                    logger.info(
                        "Artifact detection: creating artifact from write result",
                        tool_call_id=agentic_msg.tool_call_id,
                        path=path,
                    )
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

            # Extract token usage from driver
            message_usage: MessageUsage | None = None
            driver_usage = driver.get_usage()
            if driver_usage:
                message_usage = MessageUsage(
                    input_tokens=driver_usage.input_tokens or 0,
                    output_tokens=driver_usage.output_tokens or 0,
                    cost_usd=driver_usage.cost_usd or 0.0,
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

        # Build message complete event data with optional usage
        complete_data: dict[str, Any] = {
            "session_id": session_id,
            "message_id": assistant_message.id,
        }
        if message_usage:
            complete_data["usage"] = message_usage.model_dump()

        # Fetch and include session usage summary
        session_usage = await self._repository.get_session_usage(session_id)
        if session_usage:
            complete_data["session_usage"] = session_usage.model_dump()

        # Emit message complete event
        complete_event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_MESSAGE_COMPLETE,
            message="Message complete",
            data=complete_data,
            domain=EventDomain.BRAINSTORM,
        )
        self._event_bus.emit(complete_event)
        yield complete_event

    def _agentic_message_to_event(
        self,
        agentic_msg: AgenticMessage,
        session_id: str,
        message_id: str,
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
            domain=EventDomain.BRAINSTORM,
            data={
                "session_id": session_id,
                "message_id": message_id,
                "text": message,
                "tool_call_id": agentic_msg.tool_call_id,
                "tool_name": agentic_msg.tool_name,
                "input": agentic_msg.tool_input,
                "output": agentic_msg.tool_output,
                "error": agentic_msg.tool_output if agentic_msg.is_error else None,
            },
        )

    async def _create_artifact_from_path(
        self, session_id: str, path: str
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
            id=str(uuid4()),
            session_id=session_id,
            type=artifact_type,
            path=path,
            created_at=now,
        )
        await self._repository.save_artifact(artifact)

        # Emit artifact created event with flat fields matching BrainstormArtifact type
        event = WorkflowEvent(
            id=str(uuid4()),
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
        session_id: str,
        artifact_path: str,
        issue_title: str | None = None,
        issue_description: str | None = None,
        orchestrator: "OrchestratorService | None" = None,
        worktree_path: str | None = None,
    ) -> dict[str, str]:
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

        # Generate workflow ID - either from orchestrator or fallback
        if orchestrator is not None and worktree_path is not None:
            # Create issue ID from session ID (safe characters only)
            issue_id = f"brainstorm-{session_id}"

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
        else:
            # Fallback for backwards compatibility (e.g., tests without orchestrator)
            workflow_id = str(uuid4())

        # Update session status to completed
        session.status = SessionStatus.COMPLETED
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
