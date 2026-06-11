"""Path layout and atomic persistence for ATIF trajectory files.

One trajectory file per workflow: ``{trajectory_dir}/{workflow_id}/trajectory.json``.
Writes go through a temp file + ``os.replace`` so a crash mid-write never
leaves a half-written ``trajectory.json`` behind.
"""
import json
import os
import uuid
from pathlib import Path

from harbor.models.trajectories import Trajectory
from pydantic import ValidationError


def trajectory_path(trajectory_dir: Path, workflow_id: uuid.UUID) -> Path:
    """Return the canonical trajectory file path for a workflow.

    Args:
        trajectory_dir: Root directory for all trajectory files.
        workflow_id: Workflow the trajectory belongs to.

    Returns:
        ``{trajectory_dir}/{workflow_id}/trajectory.json``.
    """
    return trajectory_dir / str(workflow_id) / "trajectory.json"


def write_atomic(path: Path, trajectory: Trajectory) -> None:
    """Write a trajectory to ``path`` atomically (temp file + ``os.replace``).

    Creates parent directories as needed. On any write error the temp file is
    removed and the error propagates — a half-written file is never left at
    either the temp or the final path.

    Args:
        path: Destination file path.
        trajectory: Trajectory to serialize via ``to_json_dict()``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(trajectory.to_json_dict(), indent=2))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load(path: Path) -> Trajectory:
    """Load and validate a trajectory file.

    Args:
        path: Trajectory file to read.

    Returns:
        The parsed trajectory.

    Raises:
        ValueError: If the file is not a valid ATIF trajectory; the message
            names the offending path.
    """
    try:
        return Trajectory.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise ValueError(f"Invalid trajectory file {path}: {exc}") from exc
