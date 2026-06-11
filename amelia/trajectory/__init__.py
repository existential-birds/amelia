"""ATIF trajectory recording for amelia workflows.

Public surface for mapping driver message streams to ATIF-v1.7 trajectory
models (harbor) and, in later tasks, recording and projecting them.
"""
from amelia.trajectory.finalize import TrajectoryIndexWriter, finalize_and_index
from amelia.trajectory.mapping import map_messages, usage_to_metrics
from amelia.trajectory.projection import (
    aggregate_usage,
    trajectory_to_events,
    trajectory_to_token_summary,
)
from amelia.trajectory.recorder import AgentInvocationRecorder, WorkflowTrajectoryRecorder
from amelia.trajectory.recording_driver import RecordingDriver
from amelia.trajectory.store import load, trajectory_path, write_atomic


__all__ = [
    "AgentInvocationRecorder",
    "RecordingDriver",
    "TrajectoryIndexWriter",
    "WorkflowTrajectoryRecorder",
    "aggregate_usage",
    "finalize_and_index",
    "load",
    "map_messages",
    "trajectory_path",
    "trajectory_to_events",
    "trajectory_to_token_summary",
    "usage_to_metrics",
    "write_atomic",
]
