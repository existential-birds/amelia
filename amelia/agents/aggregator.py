"""Aggregator agent for synthesizing one plan from N candidate plans.

The Aggregator is the synthesis half of advisory Mixture-of-Agents (MoA)
planning. Given several candidate implementation plans produced independently
for the same issue, it reconciles them into a single canonical plan written to
the same file-on-disk location the Architect would have used, so the existing
``plan_validator_node`` → Developer pipeline consumes it unchanged.

It mirrors :class:`amelia.agents.architect.Architect`: agentic execution via
``execute_agentic`` with the ``write_plan`` tool, ``required_tool="write_plan"``.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from amelia.agents._driver_init import init_agent_driver
from amelia.agents.tool_profiles import resolve_agent_tools
from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.types import AgentConfig, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.server.models.events import WorkflowEvent
from amelia.tools.registry import ToolContext
from amelia.tools.write_plan import create_write_plan_tool


if TYPE_CHECKING:
    from amelia.pipelines.implementation.state import ImplementationState
    from amelia.sandbox.provider import SandboxProvider


class Aggregator:
    """Agent that synthesizes one canonical plan from N candidate plans.

    Reconciles overlapping candidate plans into a single plan and persists it
    via the ``write_plan`` tool to the canonical plan path that the validator
    stage reads. If the model never calls ``write_plan``, aggregation fails
    loudly rather than silently yielding an unchanged state.

    Attributes:
        driver: LLM driver interface for plan synthesis.

    """

    PROMPT_KEY_SYSTEM = "aggregator.system"

    SYSTEM_PROMPT = """You are a senior software architect synthesizing a single, superior \
implementation plan from several candidate plans.

You will receive N candidate plans, each produced independently for the same issue. \
Your job is to reconcile them into ONE canonical plan that is better than any individual \
candidate.

## Synthesis Principles
- Reconcile overlap: where candidates agree, consolidate into one clear set of steps.
- Prefer concrete, actionable steps: keep specific file paths, commands, and verifiable
  success criteria over vague descriptions.
- Resolve conflicts: where candidates disagree, pick the technically stronger option and
  discard the weaker one. Commit to one coherent plan — do not hedge or present alternatives.
- Preserve coverage: do not drop a necessary task that appears in only one candidate.
- Maintain TDD discipline: keep test-first steps where the candidates include them.

## Output
Write the final synthesized plan to disk using the `write_plan` tool. The plan is not
complete until it has been written via `write_plan`."""

    def __init__(
        self,
        config: AgentConfig,
        prompts: dict[str, str] | None = None,
        sandbox_provider: SandboxProvider | None = None,
    ):
        """Initialize the Aggregator agent.

        Args:
            config: Agent configuration with driver, model, and options.
            prompts: Optional dict mapping prompt IDs to custom content.
                Supports key: "aggregator.system".
            sandbox_provider: Optional shared sandbox provider for sandbox reuse.

        """
        _init = init_agent_driver(
            config,
            prompts=prompts,
            sandbox_provider=sandbox_provider,
        )
        self.driver = _init.driver
        self.options = _init.options
        self._prompts = _init.prompts
        self._driver_type = config.driver
        self._write_plan_tool_cache: dict[str, Any] = {}  # keyed by root_dir

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for synthesis.

        Returns custom prompt if injected, otherwise class default.
        """
        return self._prompts.get(self.PROMPT_KEY_SYSTEM, self.SYSTEM_PROMPT)

    def _build_prompt(self, candidates: list[str]) -> str:
        """Build the user prompt enumerating the candidate plans.

        Args:
            candidates: Candidate plan markdown strings to synthesize.

        Returns:
            Formatted prompt with each candidate under a ``### Candidate N`` header.

        """
        parts: list[str] = []
        parts.append("## Candidate Plans")
        parts.append(
            "Below are independently-produced candidate implementation plans for the "
            "same issue. Synthesize them into ONE superior canonical plan."
        )
        for i, candidate in enumerate(candidates, start=1):
            parts.append(f"### Candidate {i}\n\n{candidate}\n")

        parts.append("## Your Task")
        parts.append(
            "Reconcile overlap, prefer concrete and well-sequenced steps, and resolve "
            "conflicts in favor of the most correct approach. Use the `write_plan` tool "
            "to write the single canonical plan. Do NOT just output the plan as text — "
            "you MUST call `write_plan` to persist it, or the workflow will fail."
        )
        return "\n\n".join(parts)

    async def aggregate(
        self,
        candidate_plans: list[str],
        state: ImplementationState,
        profile: Profile,
        *,
        workflow_id: uuid.UUID,
    ) -> AsyncIterator[tuple[ImplementationState, WorkflowEvent]]:
        """Synthesize one canonical plan from N candidate plans via agentic execution.

        Drives the model with the ``write_plan`` tool to write the canonical plan
        file (the same path the Architect would have produced). Yields state/event
        tuples as execution progresses.

        Args:
            candidate_plans: Candidate plan markdown strings to synthesize.
            state: The execution state containing the issue.
            profile: The profile containing working directory and plan path settings.
            workflow_id: Workflow ID for stream events (required).

        Yields:
            Tuples of (updated ImplementationState, WorkflowEvent) as synthesis progresses.

        Raises:
            ValueError: If no issue is present, no candidates are supplied, or the
                model never calls ``write_plan`` (no plan produced).

        """
        if not state.issue:
            raise ValueError("Cannot aggregate plans: no issue in ImplementationState")
        if not candidate_plans:
            raise ValueError("Cannot aggregate plans: no candidate plans provided")

        user_prompt = self._build_prompt(candidate_plans)

        cwd = profile.repo_root
        plan_path = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
        tool_calls: list[ToolCall] = []
        tool_results: list[ToolResult] = []
        raw_output = ""
        wrote_plan_path: Path | None = None
        current_state = state

        logger.info(
            "Aggregator starting agentic execution",
            cwd=cwd,
            plan_path=plan_path,
            candidates=len(candidate_plans),
        )

        # Always synthesize through the write_plan tool (architect-style), so the
        # canonical plan lands on disk for plan_validator_node regardless of driver.
        tool_context = ToolContext(cwd=cwd, workflow_id=workflow_id)
        if cwd not in self._write_plan_tool_cache:
            self._write_plan_tool_cache[cwd] = create_write_plan_tool(root_dir=cwd)
        driver_kwargs: dict[str, Any] = {
            "required_file_path": plan_path,
            "tools": [self._write_plan_tool_cache[cwd]],
            "allowed_tools": [t.name for t in resolve_agent_tools("aggregator", tool_context)],
            "tool_context": tool_context,
            "required_tool": "write_plan",
        }

        try:
            async for message in self.driver.execute_agentic(
                prompt=user_prompt,
                cwd=cwd,
                instructions=self.system_prompt,
                **driver_kwargs,
            ):
                event: WorkflowEvent | None = None

                if message.type == AgenticMessageType.THINKING:
                    event = message.to_workflow_event(workflow_id=workflow_id, agent="aggregator")

                elif message.type == AgenticMessageType.TOOL_CALL:
                    call = ToolCall(
                        id=message.tool_call_id or f"call-{len(tool_calls)}",
                        tool_name=message.tool_name or "unknown",
                        tool_input=message.tool_input or {},
                    )
                    tool_calls.append(call)
                    event = message.to_workflow_event(workflow_id=workflow_id, agent="aggregator")

                elif message.type == AgenticMessageType.TOOL_RESULT:
                    result = ToolResult(
                        call_id=message.tool_call_id or f"call-{len(tool_results)}",
                        tool_name=message.tool_name or "unknown",
                        output=message.tool_output or "",
                        success=not message.is_error,
                    )
                    tool_results.append(result)
                    event = message.to_workflow_event(workflow_id=workflow_id, agent="aggregator")

                elif message.type == AgenticMessageType.RESULT:
                    raw_output = message.content or ""
                    event = message.to_workflow_event(workflow_id=workflow_id, agent="aggregator")

                    for tc in tool_calls:
                        if (
                            tc.tool_name in (ToolName.WRITE_PLAN, ToolName.WRITE_FILE)
                            and "file_path" in tc.tool_input
                        ):
                            wrote_plan_path = Path(tc.tool_input["file_path"])
                            break

                    logger.info(
                        "Aggregator plan synthesized",
                        agent="aggregator",
                        raw_output_length=len(raw_output),
                        tool_calls_count=len(tool_calls),
                        plan_path=str(wrote_plan_path) if wrote_plan_path else None,
                    )

                    current_state = state.model_copy(update={
                        "tool_calls": tool_calls,
                        "tool_results": tool_results,
                        "architect_raw_output": raw_output,
                        "plan_path": wrote_plan_path,
                    })
                    yield current_state, event
                    continue

                if event is not None:
                    current_state = state.model_copy(update={
                        "tool_calls": tool_calls,
                        "tool_results": tool_results,
                    })
                    yield current_state, event
        except (RuntimeError, ValueError) as exc:
            logger.exception("Aggregator agent failed")
            error_event = AgenticMessage(
                type=AgenticMessageType.RESULT,
                content=str(exc),
                is_error=True,
            ).to_workflow_event(workflow_id=workflow_id, agent="aggregator")
            current_state = state.model_copy(update={
                "tool_calls": tool_calls,
                "tool_results": tool_results,
                "architect_error": str(exc),
            })
            yield current_state, error_event
            return

        # Failure propagation: synthesis only "succeeds" if a plan was written.
        if wrote_plan_path is None:
            raise ValueError("aggregator produced no plan")
