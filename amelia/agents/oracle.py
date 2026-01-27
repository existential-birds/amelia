"""Oracle agent — expert consultation using agentic LLM execution.

Accepts a problem statement and codebase context, reasons about it using
an agentic LLM session with tool access, and returns structured advice.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel

from amelia.core.types import AgentConfig, OracleConsultation
from amelia.drivers.base import AgenticMessageType
from amelia.drivers.factory import get_driver
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventDomain, EventType, WorkflowEvent
from amelia.tools.file_bundler import bundle_files


class OracleConsultResult(BaseModel):
    """Result from an Oracle consultation.

    Attributes:
        advice: The Oracle's advice text.
        consultation: Full consultation record for persistence.
    """

    advice: str
    consultation: OracleConsultation


_SYSTEM_PROMPT = (
    "You are a consulting expert. Analyze the codebase context and provide "
    "advice on the given problem. Be specific, actionable, and reference "
    "concrete files and patterns from the codebase."
)


class Oracle:
    """Oracle agent for expert codebase consultations.

    Uses agentic LLM execution to analyze code and provide advice.
    The agent can read additional files and run shell commands during
    its reasoning process.

    Note:
        Oracle instances are designed for single use (one ``consult()`` call
        per instance). The internal sequence counter is not reset between
        calls; create a new instance for each consultation.

    Args:
        config: Agent configuration with driver, model, and options.
        event_bus: Optional EventBus for emitting consultation events.
    """

    def __init__(
        self,
        config: AgentConfig,
        event_bus: EventBus | None = None,
    ):
        self._driver = get_driver(config.driver, model=config.model)
        self._event_bus = event_bus
        self._config = config
        self._seq = 0

    def _emit(self, event: WorkflowEvent) -> None:
        """Emit event via EventBus if available."""
        if self._event_bus is not None:
            self._event_bus.emit(event)

    def _make_event(
        self,
        event_type: EventType,
        session_id: str,
        message: str,
        *,
        workflow_id: str | None = None,
        **kwargs: Any,
    ) -> WorkflowEvent:
        """Create a WorkflowEvent for Oracle consultations."""
        self._seq += 1
        return WorkflowEvent(
            id=str(uuid4()),
            domain=EventDomain.ORACLE,
            workflow_id=workflow_id or session_id,
            session_id=session_id,
            sequence=self._seq,
            timestamp=datetime.now(tz=UTC),
            agent="oracle",
            event_type=event_type,
            message=message,
            **kwargs,
        )

    async def consult(
        self,
        problem: str,
        working_dir: str,
        files: list[str] | None = None,
        workflow_id: str | None = None,
    ) -> OracleConsultResult:
        """Run an Oracle consultation.

        Gathers codebase context via FileBundler, then uses agentic LLM
        execution to analyze the problem and generate advice.

        Args:
            problem: The problem statement to analyze.
            working_dir: Root directory for codebase access.
            files: Optional glob patterns for files to include as context.
                If not provided, no files are bundled.
            workflow_id: Optional workflow ID for cross-referencing.

        Returns:
            OracleConsultResult with advice and consultation record.
        """
        session_id = str(uuid4())
        timestamp = datetime.now(tz=UTC)

        logger.info(
            "Oracle consultation started",
            session_id=session_id,
            working_dir=working_dir,
        )

        # Emit started event
        self._emit(self._make_event(
            EventType.ORACLE_CONSULTATION_STARTED,
            session_id=session_id,
            message=f"Oracle consultation started: {problem[:100]}",
            workflow_id=workflow_id,
        ))

        # Gather codebase context only when file patterns are specified
        files_consulted: list[str] = []
        bundle_tokens = 0
        bundle = None
        if files:
            try:
                bundle = await bundle_files(working_dir=working_dir, patterns=files)
                files_consulted = [f.path for f in bundle.files]
                bundle_tokens = bundle.total_tokens
            except Exception as exc:
                logger.error(
                    "Oracle file bundling failed",
                    session_id=session_id,
                    error=str(exc),
                )

                consultation = OracleConsultation(
                    timestamp=timestamp,
                    problem=problem,
                    model=self._config.model,
                    session_id=session_id,
                    workflow_id=workflow_id,
                    files_consulted=[],
                    tokens={},
                    outcome="error",
                    error_message=f"File bundling failed: {exc}",
                )

                self._emit(self._make_event(
                    EventType.ORACLE_CONSULTATION_FAILED,
                    session_id=session_id,
                    message=f"Oracle consultation failed: file bundling error: {exc}",
                    workflow_id=workflow_id,
                ))

                return OracleConsultResult(advice="", consultation=consultation)
        else:
            logger.info(
                "No file patterns specified, skipping file bundling",
                session_id=session_id,
            )

        # Build prompt with context
        context_parts: list[str] = [f"## Problem\n\n{problem}"]
        if bundle and bundle.files:
            context_parts.append("\n## Codebase Context\n")
            for f in bundle.files:
                context_parts.append(f"### {f.path}\n```\n{f.content}\n```\n")

        user_prompt = "\n".join(context_parts)

        # Execute agentic consultation. Events are emitted inline during
        # iteration for real-time streaming. The try/except captures driver
        # failures; error-path event emissions are outside the try/except
        # so programming errors in event construction propagate naturally.
        advice = ""
        driver_error: Exception | None = None
        try:
            async for message in self._driver.execute_agentic(
                prompt=user_prompt,
                cwd=working_dir,
                instructions=_SYSTEM_PROMPT,
            ):
                if message.type == AgenticMessageType.THINKING:
                    self._emit(self._make_event(
                        EventType.ORACLE_CONSULTATION_THINKING,
                        session_id=session_id,
                        message=message.content or "",
                        workflow_id=workflow_id,
                    ))

                elif message.type == AgenticMessageType.TOOL_CALL:
                    tool_name = message.tool_name or "unknown"
                    logger.debug(
                        "Oracle tool call",
                        session_id=session_id,
                        tool_name=tool_name,
                    )
                    self._emit(self._make_event(
                        EventType.ORACLE_TOOL_CALL,
                        session_id=session_id,
                        message=f"Tool call: {tool_name}",
                        workflow_id=workflow_id,
                        tool_name=tool_name,
                        tool_input=message.tool_input,
                    ))

                elif message.type == AgenticMessageType.TOOL_RESULT:
                    tool_name = message.tool_name or "unknown"
                    logger.debug(
                        "Oracle tool result",
                        session_id=session_id,
                        tool_name=tool_name,
                        is_error=message.is_error,
                    )
                    self._emit(self._make_event(
                        EventType.ORACLE_TOOL_RESULT,
                        session_id=session_id,
                        message=f"Tool result: {tool_name}",
                        workflow_id=workflow_id,
                        tool_name=tool_name,
                        is_error=message.is_error,
                    ))

                elif message.type == AgenticMessageType.RESULT:
                    advice = message.content or ""

        except Exception as exc:
            driver_error = exc

        if driver_error is not None:
            logger.error(
                "Oracle consultation failed",
                session_id=session_id,
                error=str(driver_error),
            )

            consultation = OracleConsultation(
                timestamp=timestamp,
                problem=problem,
                model=self._config.model,
                session_id=session_id,
                workflow_id=workflow_id,
                files_consulted=files_consulted,
                tokens={"context": bundle_tokens},
                outcome="error",
                error_message=str(driver_error),
            )

            self._emit(self._make_event(
                EventType.ORACLE_CONSULTATION_FAILED,
                session_id=session_id,
                message=f"Oracle consultation failed: {driver_error}",
                workflow_id=workflow_id,
            ))

            return OracleConsultResult(advice="", consultation=consultation)

        consultation = OracleConsultation(
            timestamp=timestamp,
            problem=problem,
            advice=advice,
            model=self._config.model,
            session_id=session_id,
            workflow_id=workflow_id,
            files_consulted=files_consulted,
            tokens={"context": bundle_tokens},
            outcome="success",
        )

        self._emit(self._make_event(
            EventType.ORACLE_CONSULTATION_COMPLETED,
            session_id=session_id,
            message="Oracle consultation completed",
            workflow_id=workflow_id,
        ))

        logger.info(
            "Oracle consultation completed",
            session_id=session_id,
            advice_length=len(advice),
        )

        return OracleConsultResult(advice=advice, consultation=consultation)
