"""Tool policy + middleware that vetoes tool calls at runtime.

``ToolPolicy`` is the declarative allow-list and risk ceiling.
``ToolPolicyMiddleware`` enforces it by intercepting tool execution via
``awrap_tool_call``: a denied call never reaches the handler, so its side
effects never happen. This is the enforcement spine for #357 (read-only
agents) and #228 (security guardrails).

The interception hook is ``awrap_tool_call`` (not ``before_tool``) because
langchain 1.x exposes tool interception exclusively through the wrapping hook.
amelia is async-only, so no synchronous ``wrap_tool_call`` is provided.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from amelia.core.constants import normalize_tool_name
from amelia.tools.registry.registry import registry
from amelia.tools.registry.spec import RiskLevel


# The handler type awrap_tool_call receives.
type _AsyncToolHandler = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]


class ToolPolicy(BaseModel):
    """Declarative policy governing which tools a run may invoke.

    Attributes:
        allowed: Canonical tool names permitted by this policy. A call whose
            normalized name is not in this set is denied.
        max_risk: Risk ceiling. A permitted tool whose ``risk_level`` exceeds
            this is still denied. Defaults to ``EXECUTE`` (permissive).
    """

    model_config = ConfigDict(frozen=True)

    allowed: frozenset[str]
    max_risk: RiskLevel = RiskLevel.EXECUTE


class ToolPolicyMiddleware(AgentMiddleware):
    """Vetoes tool calls that violate a ``ToolPolicy`` before they execute.

    Denials return a substitute ``ToolMessage(status="error")`` describing the
    reason; the underlying tool handler is never invoked, so side effects are
    guaranteed not to occur.
    """

    def __init__(self, policy: ToolPolicy) -> None:
        self.policy = policy

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: _AsyncToolHandler,
    ) -> ToolMessage | Command[Any]:
        """Intercept a tool call, denying it if it violates the policy.

        Args:
            request: The tool call request. ``request.tool_call["name"]`` is
                normalized via ``normalize_tool_name`` so CLI aliases (e.g.
                ``"Write"``) are enforced consistently.
            handler: The async callable that would execute the tool. Only
                called when the policy permits the call.

        Returns:
            The handler's ``ToolMessage``/``Command`` on success, or an
            error ``ToolMessage`` describing the denial otherwise.
        """
        raw_name = request.tool_call["name"]
        name = normalize_tool_name(raw_name)
        tool_call_id = request.tool_call["id"]

        if name not in self.policy.allowed:
            return ToolMessage(
                content=f"Denied: tool '{raw_name}' is not permitted by the active policy.",
                tool_call_id=tool_call_id,
                status="error",
            )

        spec = registry.get(name)
        if spec is None:
            return ToolMessage(
                content=f"Denied: tool '{name}' is not registered.",
                tool_call_id=tool_call_id,
                status="error",
            )
        if spec.risk_level > self.policy.max_risk:
            return ToolMessage(
                content=(
                    f"Denied: tool '{name}' risk level ({spec.risk_level.name}) "
                    f"exceeds the policy ceiling ({self.policy.max_risk.name})."
                ),
                tool_call_id=tool_call_id,
                status="error",
            )

        return await handler(request)
