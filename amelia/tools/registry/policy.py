"""Tool policy + middleware that vetoes tool calls at runtime.

``ToolPolicy`` is the declarative allow-list and guardrail surface.
``ToolPolicyMiddleware`` enforces it by intercepting tool execution via
``wrap_tool_call`` / ``awrap_tool_call``: a denied call never reaches the handler, so its side
effects never happen. This is the enforcement spine for #357 (read-only
agents) and #228 (security guardrails).

The interception hook is ``wrap_tool_call`` / ``awrap_tool_call`` (not
``before_tool``) because langchain 1.x exposes tool interception exclusively
through the wrapping hook. Both sync and async hooks are implemented so callers
that use ``invoke()`` or ``ainvoke()`` get identical veto behavior.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from loguru import logger
from pydantic import BaseModel, ConfigDict

from amelia.core.constants import normalize_tool_name
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EPHEMERAL_SEQUENCE, EventLevel, EventType, WorkflowEvent
from amelia.tools.registry.registry import registry
from amelia.tools.registry.spec import Permission, RiskLevel, ToolSpec


# The handler types wrapping hooks receive.
_AsyncToolHandler = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]
_SyncToolHandler = Callable[[ToolCallRequest], ToolMessage | Command[Any]]
ToolValidator = Callable[["ToolValidationContext"], "ToolValidationResult"]


class HighRiskDecision(StrEnum):
    """Policy behavior for high-risk calls at or above EXECUTE risk."""

    AUTO = "auto"
    DENY = "deny"
    CONFIRM = "confirm"


class ToolPolicyAuditDecision(StrEnum):
    """Structured decision labels emitted to audit sinks."""

    ALLOWED = "allowed"
    DENIED = "denied"
    RESULT = "result"


@dataclass(frozen=True)
class ToolValidationContext:
    """Context passed to pre/post validators.

    ``result`` is ``None`` for pre-execution validators and populated for
    post-execution validators. Validators are intentionally small synchronous
    extension points; async wrappers still enforce them before/after awaiting
    the underlying handler.
    """

    tool_name: str
    raw_name: str
    args: dict[str, Any]
    spec: ToolSpec | None
    request: ToolCallRequest
    result: ToolMessage | Command[Any] | None = None


@dataclass(frozen=True)
class ToolValidationResult:
    """Result returned by a pre/post execution validator."""

    action: Literal["allow", "deny", "replace"]
    message: str | None = None
    replacement: ToolMessage | Command[Any] | None = None

    @classmethod
    def allow(cls) -> ToolValidationResult:
        return cls(action="allow")

    @classmethod
    def deny(cls, message: str) -> ToolValidationResult:
        return cls(action="deny", message=message)

    @classmethod
    def replace(cls, replacement: ToolMessage | Command[Any]) -> ToolValidationResult:
        return cls(action="replace", replacement=replacement)


class ToolPolicy(BaseModel):
    """Declarative policy governing which tools a run may invoke.

    Attributes:
        allowed: Canonical tool names permitted by this policy. A call whose
            normalized name is not in this set is denied.
        max_risk: Risk ceiling. A permitted tool whose ``risk_level`` exceeds
            this is still denied. Defaults to ``EXECUTE`` (permissive).
        permissions: Capabilities granted to this policy. Registered tools whose
            ``required_permissions`` are not a subset are denied.
        pre_exec_validators: Synchronous validators that can deny a call based
            on normalized tool metadata and raw parameters before execution.
        post_exec_validators: Synchronous validators that can deny or replace a
            handler result after execution.
        high_risk_decision: Behavior for tools with risk >= ``EXECUTE``. In
            headless mode, ``confirm`` is deterministic deny until an approval
            UI is wired in.
        allow_unregistered: Dynamic tool names that are allowed even though
            they are not in the registry, such as per-run submit tools.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    allowed: frozenset[str]
    max_risk: RiskLevel = RiskLevel.EXECUTE
    permissions: frozenset[Permission] = frozenset(Permission)
    pre_exec_validators: tuple[ToolValidator, ...] = ()
    post_exec_validators: tuple[ToolValidator, ...] = ()
    high_risk_decision: HighRiskDecision = HighRiskDecision.AUTO
    allow_unregistered: frozenset[str] = frozenset()


@dataclass(frozen=True)
class _PolicyDecision:
    decision: ToolPolicyAuditDecision
    reason: str
    message: str | None = None
    spec: ToolSpec | None = None


class ToolPolicyMiddleware(AgentMiddleware):
    """Vetoes tool calls that violate a ``ToolPolicy`` before they execute.

    Denials return a substitute ``ToolMessage(status="error")`` describing the
    reason; the underlying tool handler is never invoked, so side effects are
    guaranteed not to occur. Allowed/denied/result decisions are emitted to the
    provided ``EventBus`` and loguru structured logs for auditability.
    """

    def __init__(
        self,
        policy: ToolPolicy,
        *,
        event_bus: EventBus | None = None,
        workflow_id: uuid.UUID | None = None,
        agent: str = "tool_policy",
    ) -> None:
        self.policy = policy
        self._event_bus = event_bus
        self._workflow_id = workflow_id or uuid.uuid4()
        self._agent = agent

    def _veto_tool_message(self, request: ToolCallRequest, message: str) -> ToolMessage:
        return ToolMessage(
            content=message,
            tool_call_id=request.tool_call["id"],
            status="error",
        )

    # Argument keys whose values are redacted in audit payloads to prevent
    # leaking secrets or user content to logs and event subscribers.
    _REDACTED_ARG_KEYS: frozenset[str] = frozenset({
        "content", "cmd", "command", "password", "token", "api_key",
        "secret", "body", "data", "text", "input", "query", "url",
    })

    @classmethod
    def _redact_args(cls, args: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of *args* with sensitive values replaced by '***'.

        Only top-level string keys in ``_REDACTED_ARG_KEYS`` are redacted;
        nested structures are left intact so the audit record stays readable
        without deep traversal.
        """
        redacted: dict[str, Any] = {}
        for key, value in args.items():
            if key.lower() in cls._REDACTED_ARG_KEYS:
                redacted[key] = "***"
            else:
                redacted[key] = value
        return redacted

    def _audit(
        self,
        *,
        request: ToolCallRequest,
        name: str,
        decision: ToolPolicyAuditDecision,
        reason: str,
        spec: ToolSpec | None,
        result: ToolMessage | Command[Any] | None = None,
        message: str | None = None,
    ) -> None:
        raw_args = dict(request.tool_call.get("args") or {})
        args = self._redact_args(raw_args)
        risk_level = spec.risk_level.name if spec else None
        required_permissions = sorted(str(permission) for permission in (spec.required_permissions if spec else ()))
        data: dict[str, Any] = {
            "decision": decision.value,
            "reason": reason,
            "tool_name": name,
            "raw_tool_name": request.tool_call["name"],
            "tool_call_id": request.tool_call["id"],
            "args": args,
            "risk_level": risk_level,
            "required_permissions": required_permissions,
        }
        if message is not None:
            data["message"] = message
        if result is not None:
            data["result_type"] = type(result).__name__
            if isinstance(result, ToolMessage):
                data["tool_status"] = result.status

        logger.bind(**data).info("tool_policy_decision")

        if self._event_bus is None:
            return
        level = EventLevel.WARNING if decision == ToolPolicyAuditDecision.DENIED else EventLevel.DEBUG
        self._event_bus.emit(
            WorkflowEvent(
                id=uuid.uuid4(),
                workflow_id=self._workflow_id,
                sequence=EPHEMERAL_SEQUENCE,
                timestamp=datetime.now(UTC),
                agent=self._agent,
                event_type=EventType.TOOL_POLICY_DECISION,
                level=level,
                message=message or f"Tool policy {decision.value}: {name}",
                data=data,
                tool_name=name,
                tool_input=args,
                is_error=decision == ToolPolicyAuditDecision.DENIED,
            )
        )

    def _evaluate_request(self, request: ToolCallRequest) -> tuple[str, _PolicyDecision]:
        raw_name = request.tool_call["name"]
        name = normalize_tool_name(raw_name)

        if name not in self.policy.allowed:
            return name, _PolicyDecision(
                decision=ToolPolicyAuditDecision.DENIED,
                reason="not_allowed",
                message=f"Denied: tool '{raw_name}' is not permitted by the active policy.",
            )

        spec = registry.get(name)
        if spec is None:
            if name in self.policy.allow_unregistered:
                return name, _PolicyDecision(
                    decision=ToolPolicyAuditDecision.ALLOWED,
                    reason="allowed_unregistered",
                )
            return name, _PolicyDecision(
                decision=ToolPolicyAuditDecision.DENIED,
                reason="unregistered",
                message=f"Denied: tool '{name}' is not registered.",
            )

        if spec.risk_level > self.policy.max_risk:
            return name, _PolicyDecision(
                decision=ToolPolicyAuditDecision.DENIED,
                reason="risk_ceiling",
                spec=spec,
                message=(
                    f"Denied: tool '{name}' risk level ({spec.risk_level.name}) "
                    f"exceeds the policy ceiling ({self.policy.max_risk.name})."
                ),
            )

        missing_permissions = spec.required_permissions - self.policy.permissions
        if missing_permissions:
            missing = ", ".join(sorted(str(permission) for permission in missing_permissions))
            return name, _PolicyDecision(
                decision=ToolPolicyAuditDecision.DENIED,
                reason="missing_permissions",
                spec=spec,
                message=f"Denied: tool '{name}' missing required permission(s): {missing}.",
            )

        if spec.risk_level >= RiskLevel.EXECUTE:
            if self.policy.high_risk_decision == HighRiskDecision.DENY:
                return name, _PolicyDecision(
                    decision=ToolPolicyAuditDecision.DENIED,
                    reason="high_risk_denied",
                    spec=spec,
                    message=f"Denied: tool '{name}' requires high-risk execution permission.",
                )
            if self.policy.high_risk_decision == HighRiskDecision.CONFIRM:
                return name, _PolicyDecision(
                    decision=ToolPolicyAuditDecision.DENIED,
                    reason="confirmation_required",
                    spec=spec,
                    message=(
                        f"Denied: tool '{name}' requires confirmation, which is unavailable "
                        "in headless mode."
                    ),
                )

        args = dict(request.tool_call.get("args") or {})
        ctx = ToolValidationContext(
            tool_name=name,
            raw_name=raw_name,
            args=args,
            spec=spec,
            request=request,
        )
        for validator in self.policy.pre_exec_validators:
            validation = validator(ctx)
            if validation.action == "deny":
                return name, _PolicyDecision(
                    decision=ToolPolicyAuditDecision.DENIED,
                    reason="pre_validator",
                    spec=spec,
                    message=validation.message or f"Denied: tool '{name}' failed pre-exec validation.",
                )

        return name, _PolicyDecision(
            decision=ToolPolicyAuditDecision.ALLOWED,
            reason="allowed",
            spec=spec,
        )

    def _apply_post_validators(
        self,
        *,
        name: str,
        request: ToolCallRequest,
        spec: ToolSpec | None,
        result: ToolMessage | Command[Any],
    ) -> tuple[ToolMessage | Command[Any], _PolicyDecision | None]:
        args = dict(request.tool_call.get("args") or {})
        current = result
        for validator in self.policy.post_exec_validators:
            ctx = ToolValidationContext(
                tool_name=name,
                raw_name=request.tool_call["name"],
                args=args,
                spec=spec,
                request=request,
                result=current,
            )
            validation = validator(ctx)
            if validation.action == "deny":
                message = validation.message or f"Denied: tool '{name}' failed post-exec validation."
                return self._veto_tool_message(request, message), _PolicyDecision(
                    decision=ToolPolicyAuditDecision.DENIED,
                    reason="post_validator",
                    spec=spec,
                    message=message,
                )
            if validation.action == "replace" and validation.replacement is not None:
                current = validation.replacement
        return current, None

    def _deny(self, request: ToolCallRequest, name: str, decision: _PolicyDecision) -> ToolMessage:
        message = decision.message or f"Denied: tool '{name}' by active policy."
        self._audit(
            request=request,
            name=name,
            decision=ToolPolicyAuditDecision.DENIED,
            reason=decision.reason,
            spec=decision.spec,
            message=message,
        )
        return self._veto_tool_message(request, message)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: _SyncToolHandler,
    ) -> ToolMessage | Command[Any]:
        """Sync interception hook matching ``awrap_tool_call`` semantics."""
        name, decision = self._evaluate_request(request)
        if decision.decision == ToolPolicyAuditDecision.DENIED:
            return self._deny(request, name, decision)
        self._audit(
            request=request,
            name=name,
            decision=ToolPolicyAuditDecision.ALLOWED,
            reason=decision.reason,
            spec=decision.spec,
        )
        result = handler(request)
        result, post_decision = self._apply_post_validators(
            name=name, request=request, spec=decision.spec, result=result
        )
        if post_decision is not None:
            self._audit(
                request=request,
                name=name,
                decision=ToolPolicyAuditDecision.DENIED,
                reason=post_decision.reason,
                spec=post_decision.spec,
                result=result,
                message=post_decision.message,
            )
            return result
        self._audit(
            request=request,
            name=name,
            decision=ToolPolicyAuditDecision.RESULT,
            reason="result",
            spec=decision.spec,
            result=result,
        )
        return result

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
        name, decision = self._evaluate_request(request)
        if decision.decision == ToolPolicyAuditDecision.DENIED:
            return self._deny(request, name, decision)
        self._audit(
            request=request,
            name=name,
            decision=ToolPolicyAuditDecision.ALLOWED,
            reason=decision.reason,
            spec=decision.spec,
        )
        result = await handler(request)
        result, post_decision = self._apply_post_validators(
            name=name, request=request, spec=decision.spec, result=result
        )
        if post_decision is not None:
            self._audit(
                request=request,
                name=name,
                decision=ToolPolicyAuditDecision.DENIED,
                reason=post_decision.reason,
                spec=post_decision.spec,
                result=result,
                message=post_decision.message,
            )
            return result
        self._audit(
            request=request,
            name=name,
            decision=ToolPolicyAuditDecision.RESULT,
            reason="result",
            spec=decision.spec,
            result=result,
        )
        return result
