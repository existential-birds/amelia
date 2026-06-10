"""Per-workflow ATIF trajectory assembly.

``WorkflowTrajectoryRecorder`` owns one parent trajectory per workflow. Each
agent invocation (``begin_invocation``) adds a parent step that references an
embedded subagent trajectory, recorded through ``AgentInvocationRecorder``.
``finalize`` drains any still-open invocations, stamps the outcome, and writes
the file atomically via :mod:`amelia.trajectory.store`.
"""
import asyncio
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from harbor.models.trajectories import (
    Agent,
    FinalMetrics,
    Observation,
    ObservationResult,
    Step,
    SubagentTrajectoryRef,
    Trajectory,
)
from loguru import logger

import amelia
from amelia.drivers.base import AgenticMessage, DriverUsage
from amelia.trajectory.mapping import map_messages, usage_to_metrics
from amelia.trajectory.store import load, trajectory_path, write_atomic


def _sum_present[Num: (int, float)](values: Iterable[Num | None]) -> Num | None:
    """Sum the non-None values, or return None if none are present."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


class AgentInvocationRecorder:
    """Records one agent invocation as an embedded subagent trajectory."""

    def __init__(self, agent_name: str, model: str | None, trajectory_id: str) -> None:
        self.trajectory_id = trajectory_id
        self._agent = Agent(name=agent_name, version=amelia.__version__, model_name=model)
        self._steps: list[Step] = []
        self._final_metrics: FinalMetrics | None = None
        self._duration_ms: int | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        """Whether ``close`` has been called."""
        return self._closed

    @property
    def duration_ms(self) -> int | None:
        """Agent execution time in milliseconds, as reported by the driver."""
        return self._duration_ms

    def _next_id(self) -> int:
        return len(self._steps) + 1

    def set_tool_definitions(self, tool_definitions: list[dict[str, Any]]) -> None:
        """Attach the driver's tool definitions to the subagent's agent metadata.

        Args:
            tool_definitions: Tool definitions as reported by the driver.
        """
        self._agent.tool_definitions = tool_definitions

    def record_prompt(self, *, instructions: str | None, prompt: str) -> None:
        """Record the resolved prompts: a system step (if instructions) then a user step.

        Args:
            instructions: Resolved agent instructions; skipped when None.
            prompt: Resolved task prompt for the agent.
        """
        if instructions is not None:
            self._steps.append(
                Step(step_id=self._next_id(), source="system", message=instructions)
            )
        self._steps.append(Step(step_id=self._next_id(), source="user", message=prompt))

    def record_messages(self, messages: list[AgenticMessage]) -> None:
        """Append driver messages as ATIF steps (verbatim, untruncated).

        Args:
            messages: Driver messages in stream order.
        """
        self._steps.extend(map_messages(messages, start_id=self._next_id()))

    def close(
        self, usage: DriverUsage | None = None, cost_usd: float | None = None
    ) -> None:
        """Close the invocation, setting final metrics and last-step metrics.

        Idempotent — subsequent calls are no-ops. An invocation with no
        recorded steps gets a placeholder system step (ATIF requires at least
        one step per trajectory).

        Args:
            usage: Accumulated driver usage, if available.
            cost_usd: Resolved cost in USD; falls back to ``usage.cost_usd``.
        """
        if self._closed:
            return
        self._closed = True
        if not self._steps:
            self._steps.append(
                Step(step_id=1, source="system", message="(no messages recorded)")
            )
        if usage is not None:
            self._steps[-1].metrics = usage_to_metrics(usage, cost_usd)
            self._final_metrics = FinalMetrics(
                total_prompt_tokens=usage.input_tokens,
                total_completion_tokens=usage.output_tokens,
                total_cached_tokens=usage.cache_read_tokens,
                total_cost_usd=cost_usd if cost_usd is not None else usage.cost_usd,
                total_steps=len(self._steps),
            )
            self._duration_ms = usage.duration_ms
        else:
            self._final_metrics = FinalMetrics(total_steps=len(self._steps))

    def build(self) -> Trajectory:
        """Build the embedded subagent trajectory. The invocation must be closed."""
        if not self._closed:
            raise ValueError(
                f"invocation {self.trajectory_id!r} must be closed before build()"
            )
        return self.snapshot()

    def snapshot(self) -> Trajectory:
        """Build a read-only view of the invocation as recorded so far.

        Unlike :meth:`build`, this works on open invocations (live
        projection); an invocation with no steps yet gets a placeholder
        system step (ATIF requires at least one step per trajectory).
        """
        steps = self._steps or [
            Step(step_id=1, source="system", message="(no messages recorded)")
        ]
        return Trajectory(
            trajectory_id=self.trajectory_id,
            agent=self._agent,
            steps=steps,
            final_metrics=self._final_metrics,
        )


class WorkflowTrajectoryRecorder:
    """Assembles one canonical ATIF trajectory per workflow run."""

    def __init__(
        self,
        *,
        workflow_id: uuid.UUID,
        trajectory_dir: Path,
        profile_snapshot: dict[str, Any],
    ) -> None:
        self._workflow_id = workflow_id
        self._trajectory_dir = trajectory_dir
        self._profile_snapshot = profile_snapshot
        self._parent_steps: list[Step] = []
        self._invocations: list[AgentInvocationRecorder] = []
        self._prior_subagents: list[Trajectory] = []
        self._final_metrics: FinalMetrics | None = None
        self._total_duration_ms: int | None = None
        self._load_existing()

    def _load_existing(self) -> None:
        """Continue an existing trajectory file (resume after a finalized run).

        When ``trajectory.json`` already exists for this workflow, its parent
        steps and subagent trajectories are loaded so new invocations append
        rather than overwrite. A corrupt file is logged and recording starts
        fresh — resuming a workflow must not fail on a bad history file.
        """
        path = trajectory_path(self._trajectory_dir, self._workflow_id)
        if not path.exists():
            return
        try:
            existing = load(path)
        except (ValueError, OSError):
            logger.warning(
                "Existing trajectory file is invalid; starting fresh",
                workflow_id=str(self._workflow_id),
                path=str(path),
            )
            return
        self._parent_steps = list(existing.steps)
        self._prior_subagents = list(existing.subagent_trajectories or [])

    @property
    def final_metrics(self) -> FinalMetrics | None:
        """Parent final metrics computed by the most recent ``finalize`` call."""
        return self._final_metrics

    @property
    def total_duration_ms(self) -> int | None:
        """Sum of driver-reported execution times across all invocations.

        Populated after ``finalize`` is called. Returns ``None`` when no
        invocation reported a duration (e.g. drivers that do not track it).
        """
        return self._total_duration_ms

    def begin_invocation(
        self, agent_name: str, *, model: str | None = None
    ) -> AgentInvocationRecorder:
        """Start recording an agent invocation.

        Adds a parent step whose observation references a new embedded
        subagent trajectory with a unique ``trajectory_id``.

        Args:
            agent_name: Name of the invoked agent (e.g. ``"developer"``).
            model: Model the agent is configured with, if known.

        Returns:
            The invocation recorder for the agent's driver stream.
        """
        invocation_number = len(self._prior_subagents) + len(self._invocations) + 1
        trajectory_id = f"{agent_name}-inv-{invocation_number}"
        inv = AgentInvocationRecorder(agent_name, model, trajectory_id)
        self._invocations.append(inv)
        self._parent_steps.append(
            Step(
                step_id=len(self._parent_steps) + 1,
                source="agent",
                message=f"Invoked {agent_name}",
                llm_call_count=0,
                observation=Observation(
                    results=[
                        ObservationResult(
                            subagent_trajectory_ref=[
                                SubagentTrajectoryRef(trajectory_id=trajectory_id)
                            ]
                        )
                    ]
                ),
            )
        )
        return inv

    def snapshot(self) -> Trajectory:
        """Build a read-only trajectory of the current recording state.

        Used to project live history for active workflows without closing
        invocations or touching disk. Open invocations contribute their
        partial steps; no outcome or final metrics are stamped.
        """
        subagents = self._prior_subagents + [
            inv.snapshot() for inv in self._invocations
        ]
        parent_steps = self._parent_steps or [
            Step(step_id=1, source="system", message="No agent invocations recorded")
        ]
        return Trajectory(
            session_id=str(self._workflow_id),
            agent=Agent(
                name="amelia", version=amelia.__version__, model_name="orchestrator"
            ),
            steps=parent_steps,
            extra={"outcome": {"status": "in_progress"}, **self._profile_snapshot},
            subagent_trajectories=subagents or None,
        )

    async def finalize(
        self,
        status: str,
        failure_reason: str | None = None,
        outcome_extra: dict[str, Any] | None = None,
    ) -> Path:
        """Close open invocations, assemble the parent trajectory, and write it.

        Args:
            status: Terminal workflow status (e.g. ``"completed"``, ``"failed"``).
            failure_reason: Reason recorded in the outcome when the workflow failed.
            outcome_extra: Additional outcome fields (e.g. ``pipeline``, final
                review verdicts) merged into ``extra["outcome"]``.

        Returns:
            Path of the written ``trajectory.json``.

        Raises:
            Exception: Write errors propagate — never swallowed into a
                half-written file.
        """
        for inv in self._invocations:
            if not inv.closed:
                inv.close()
        subagents = self._prior_subagents + [inv.build() for inv in self._invocations]
        self._total_duration_ms = _sum_present(
            inv.duration_ms for inv in self._invocations
        )

        outcome: dict[str, Any] = {"status": status}
        if failure_reason is not None:
            outcome["failure_reason"] = failure_reason
        if outcome_extra:
            outcome.update(outcome_extra)

        parent_steps = self._parent_steps or [
            Step(step_id=1, source="system", message="No agent invocations recorded")
        ]
        self._final_metrics = FinalMetrics(
            total_prompt_tokens=_sum_present(
                s.final_metrics.total_prompt_tokens if s.final_metrics else None
                for s in subagents
            ),
            total_completion_tokens=_sum_present(
                s.final_metrics.total_completion_tokens if s.final_metrics else None
                for s in subagents
            ),
            total_cached_tokens=_sum_present(
                s.final_metrics.total_cached_tokens if s.final_metrics else None
                for s in subagents
            ),
            total_cost_usd=_sum_present(
                s.final_metrics.total_cost_usd if s.final_metrics else None
                for s in subagents
            ),
            total_steps=len(parent_steps),
        )
        trajectory = Trajectory(
            session_id=str(self._workflow_id),
            agent=Agent(
                name="amelia", version=amelia.__version__, model_name="orchestrator"
            ),
            steps=parent_steps,
            final_metrics=self._final_metrics,
            extra={"outcome": outcome, **self._profile_snapshot},
            subagent_trajectories=subagents or None,
        )
        path = trajectory_path(self._trajectory_dir, self._workflow_id)
        await asyncio.to_thread(write_atomic, path, trajectory)
        return path
