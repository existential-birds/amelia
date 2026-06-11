"""RecordingDriver — transparent DriverInterface proxy that records trajectories.

Wraps an agent's driver at the node seam (pattern P1): re-yields every
``AgenticMessage`` unchanged while buffering it into an
``AgentInvocationRecorder``, and closes the invocation with the driver's
accumulated usage when the stream ends. Recording failures are logged and
never break the agent stream; messages pass through verbatim — no filtering,
no mutation.
"""
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from pydantic import BaseModel

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
    GenerateResult,
)
from amelia.server.models.tokens import resolve_driver_cost
from amelia.trajectory.recorder import AgentInvocationRecorder


class RecordingDriver(DriverInterface):
    """Proxy over a driver that records the invocation as an ATIF trajectory."""

    def __init__(self, inner: DriverInterface, invocation: AgentInvocationRecorder) -> None:
        self._inner = inner
        self._invocation = invocation

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown public attributes to the inner driver.

        Keeps the proxy transparent for driver-specific attributes that node
        and agent code reads (e.g. ``model``). Dunder/private lookups raise so
        proxy internals never recurse into delegation.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Generate via the inner driver, recording a two-step invocation.

        Records the prompts (system step when ``system_prompt`` is set, then a
        user step), one agent step with the string output (schema outputs are
        serialized via ``model_dump_json()``), then closes the invocation with
        the driver's usage.
        """
        self._record_prompt(instructions=system_prompt, prompt=prompt)
        try:
            output, session_id = await self._inner.generate(
                prompt, system_prompt=system_prompt, schema=schema, **kwargs
            )
        except BaseException:
            await self._close_invocation([])
            raise
        text = output.model_dump_json() if isinstance(output, BaseModel) else str(output)
        await self._close_invocation(
            [AgenticMessage(type=AgenticMessageType.RESULT, content=text)]
        )
        return output, session_id

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
        allowed_tools: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgenticMessage]:
        """Execute via the inner driver, re-yielding every message unchanged.

        Records the resolved prompts up front, buffers the stream, and on
        stream end (including ``GeneratorExit`` or an inner exception) records
        the buffered messages and closes the invocation with the driver's
        accumulated usage.
        """
        self._record_prompt(instructions=instructions, prompt=prompt)
        buffered: list[AgenticMessage] = []
        try:
            async for message in self._inner.execute_agentic(
                prompt,
                cwd,
                session_id=session_id,
                instructions=instructions,
                schema=schema,
                allowed_tools=allowed_tools,
                **kwargs,
            ):
                buffered.append(message)
                yield message
        finally:
            await self._close_invocation(buffered)

    def get_usage(self) -> DriverUsage | None:
        """Delegate to the inner driver."""
        return self._inner.get_usage()

    def get_tool_definitions(self) -> list[dict[str, Any]] | None:
        """Delegate to the inner driver (None when it lacks the capability)."""
        getter = getattr(self._inner, "get_tool_definitions", None)
        return getter() if getter is not None else None

    async def cleanup_session(self, session_id: str) -> bool:
        """Delegate to the inner driver."""
        return await self._inner.cleanup_session(session_id)

    def _record_prompt(self, *, instructions: str | None, prompt: str) -> None:
        """Record resolved prompts; failures are logged, never raised."""
        try:
            self._invocation.record_prompt(instructions=instructions, prompt=prompt)
        except Exception:
            logger.exception(
                "Failed to record prompt for trajectory",
                trajectory_id=self._invocation.trajectory_id,
            )

    async def _close_invocation(self, messages: list[AgenticMessage]) -> None:
        """Record buffered messages and close the invocation with usage.

        Each recording stage is best-effort: a failure is logged and the
        invocation still closes with whatever was captured.
        """
        if messages:
            try:
                self._invocation.record_messages(messages)
            except Exception:
                logger.exception(
                    "Failed to record driver messages for trajectory",
                    trajectory_id=self._invocation.trajectory_id,
                )
        try:
            tool_definitions = self.get_tool_definitions()
            if tool_definitions is not None:
                self._invocation.set_tool_definitions(tool_definitions)
        except Exception:
            logger.exception(
                "Failed to record tool definitions for trajectory",
                trajectory_id=self._invocation.trajectory_id,
            )
        usage: DriverUsage | None = None
        cost_usd: float | None = None
        try:
            usage = self._inner.get_usage()
            if usage is not None:
                cost_usd = await resolve_driver_cost(
                    usage, getattr(self._inner, "model", None)
                )
        except Exception:
            usage = None
            logger.exception(
                "Failed to resolve driver usage for trajectory",
                trajectory_id=self._invocation.trajectory_id,
            )
        self._invocation.close(usage=usage, cost_usd=cost_usd)
