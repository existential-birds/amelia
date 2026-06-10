"""Shared trajectory finalization core.

Both terminal seams (the server graph runner and the PR auto-fix pipeline)
finalize a :class:`~amelia.trajectory.recorder.WorkflowTrajectoryRecorder` the
same way: write the trajectory file with the run's outcome, persist the thin
index columns, log, and never let a finalization error mask the run's own
result. ``finalize_and_index`` owns that core; callers keep pipeline-specific
outcome assembly (verdicts, pipeline label) at their own sites.

The index write lives on the server repository layer, so this module takes a
:class:`TrajectoryIndexWriter` callable instead of importing ``amelia.server``
— keeping the trajectory package free of a cross-layer dependency.
"""
import uuid
from pathlib import Path
from typing import Any, Protocol

from harbor.models.trajectories import FinalMetrics
from loguru import logger

from amelia.trajectory.recorder import WorkflowTrajectoryRecorder


class TrajectoryIndexWriter(Protocol):
    """Persists the thin trajectory index columns for a finalized workflow."""

    async def __call__(
        self,
        workflow_id: uuid.UUID,
        path: Path,
        final_metrics: FinalMetrics | None,
        execution_duration_ms: int | None = None,
    ) -> None: ...


async def finalize_and_index(
    recorder: WorkflowTrajectoryRecorder,
    workflow_id: uuid.UUID,
    *,
    status: str,
    failure_reason: str | None,
    outcome_extra: dict[str, Any],
    write_index: TrajectoryIndexWriter | None,
) -> bool:
    """Write the trajectory file, persist its index columns, and log.

    Best-effort: any error is logged and never propagates — finalization must
    not mask the workflow's own success or failure.

    Args:
        recorder: The workflow's trajectory recorder.
        workflow_id: Workflow whose trajectory to finalize and index.
        status: Terminal outcome status (``completed``/``failed``/``cancelled``).
        failure_reason: Outcome failure reason for failed workflows.
        outcome_extra: Pipeline-specific outcome fields (e.g. ``pipeline``
            label, review verdicts) merged into the trajectory outcome.
        write_index: Index-column writer, or ``None`` to skip indexing.

    Returns:
        ``True`` when finalize and index both succeeded, ``False`` otherwise.
        Callers use this to decide registry retention / retry.
    """
    try:
        path = await recorder.finalize(
            status=status,
            failure_reason=failure_reason,
            outcome_extra=outcome_extra,
        )
        if write_index is not None:
            await write_index(
                workflow_id,
                path,
                recorder.final_metrics,
                execution_duration_ms=recorder.total_duration_ms,
            )
        logger.info(
            "Trajectory finalized",
            workflow_id=workflow_id,
            status=status,
            path=str(path),
        )
        return True
    except Exception:
        logger.exception(
            "Failed to finalize trajectory",
            workflow_id=workflow_id,
            status=status,
        )
        return False
