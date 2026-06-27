"""Tests for WorkflowTrajectoryRecorder and the atomic trajectory store."""
import json
import uuid

from harbor.utils.trajectory_validator import validate_trajectory

import amelia
from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
from amelia.trajectory import WorkflowTrajectoryRecorder


WF_ID = uuid.UUID("00000000-0000-0000-0000-00000000a11a")


async def test_recorder_assembles_valid_trajectory(tmp_path):
    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path,
        profile_snapshot={"profile_id": "default", "issue_id": "123"})
    inv = rec.begin_invocation("developer", model="claude-x")
    inv.record_prompt(instructions="You are the developer.", prompt="Fix the bug.")
    inv.record_messages([AgenticMessage(type=AgenticMessageType.RESULT, content="fixed")])
    inv.close(usage=DriverUsage(input_tokens=10, output_tokens=5), cost_usd=0.01)
    path = await rec.finalize(status="completed")

    data = json.loads(path.read_text())
    assert data["schema_version"] == "ATIF-v1.7"
    assert data["session_id"] == str(WF_ID)
    assert data["agent"]["model_name"] == "orchestrator"
    sub = data["subagent_trajectories"][0]
    assert sub["agent"] == {"name": "developer", "version": amelia.__version__, "model_name": "claude-x"}
    assert [s["source"] for s in sub["steps"][:2]] == ["system", "user"]   # resolved prompts present
    assert data["steps"][0]["observation"]["results"][0]  # parent step references the subagent
    assert data["extra"]["outcome"]["status"] == "completed"
    assert data["final_metrics"]["total_cost_usd"] == 0.01
    assert validate_trajectory(data)


async def test_close_persists_peak_context_into_final_metrics(tmp_path):
    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={})
    inv = rec.begin_invocation("developer", model="claude-x")
    inv.record_messages([AgenticMessage(type=AgenticMessageType.RESULT, content="done")])
    inv.close(
        usage=DriverUsage(
            input_tokens=10,
            output_tokens=5,
            context_tokens=120_000,
            context_window_tokens=200_000,
            context_utilization=0.6,
            context_warning_threshold=0.8,
            context_window_warning=False,
        ),
        cost_usd=0.01,
    )
    path = await rec.finalize(status="completed")

    data = json.loads(path.read_text())
    context = data["subagent_trajectories"][0]["final_metrics"]["extra"]["context"]
    assert context["context_tokens"] == 120_000
    assert context["context_window_tokens"] == 200_000
    assert context["context_utilization"] == 0.6
    assert context["context_window_warning"] is False


async def test_close_without_context_data_omits_context_extra(tmp_path):
    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={})
    inv = rec.begin_invocation("developer", model="claude-x")
    inv.record_messages([AgenticMessage(type=AgenticMessageType.RESULT, content="done")])
    inv.close(usage=DriverUsage(input_tokens=10, output_tokens=5), cost_usd=0.01)
    path = await rec.finalize(status="completed")

    data = json.loads(path.read_text())
    assert data["subagent_trajectories"][0]["final_metrics"].get("extra") is None


async def test_finalize_is_atomic_and_drains_open_invocation(tmp_path):
    rec = WorkflowTrajectoryRecorder(workflow_id=WF_ID, trajectory_dir=tmp_path,
                                     profile_snapshot={})
    inv = rec.begin_invocation("developer", model="m")
    inv.record_messages([AgenticMessage(type=AgenticMessageType.THINKING, content="…")])
    path = await rec.finalize(status="failed", failure_reason="crash")  # inv never closed
    data = json.loads(path.read_text())
    assert data["extra"]["outcome"] == {"status": "failed", "failure_reason": "crash"}
    assert data["subagent_trajectories"][0]["steps"]  # partial steps drained, not lost
    assert not list(tmp_path.glob("**/*.tmp"))        # no partial temp file left behind
