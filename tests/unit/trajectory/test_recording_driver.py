"""Tests for the RecordingDriver proxy over DriverInterface."""
import json
import uuid
from typing import Any

import pytest
from pydantic import BaseModel

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
from amelia.trajectory import RecordingDriver, WorkflowTrajectoryRecorder


WF_ID = uuid.UUID("00000000-0000-0000-0000-00000000d41f")


class FakeDriver:
    """Yields a tool call/result pair then a result; reports fixed usage."""

    USAGE = DriverUsage(
        input_tokens=42, output_tokens=7, cost_usd=0.02, model="fake-model"
    )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, str | None]:
        return "generated text", "sess-1"

    async def execute_agentic(self, prompt: str, cwd: str, **kwargs: Any):
        yield AgenticMessage(
            type=AgenticMessageType.TOOL_CALL, tool_name="write_file",
            tool_input={"path": "a.py"}, tool_call_id="c1",
        )
        yield AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT, tool_name="write_file",
            tool_output="ok", tool_call_id="c1",
        )
        yield AgenticMessage(type=AgenticMessageType.RESULT, content="done")

    def get_usage(self) -> DriverUsage | None:
        return self.USAGE

    async def cleanup_session(self, session_id: str) -> bool:
        return True


async def test_recording_driver_captures_stream_and_usage(tmp_path):
    rec = WorkflowTrajectoryRecorder(workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={})
    inv = rec.begin_invocation("developer", model="m")
    rd = RecordingDriver(FakeDriver(), inv)   # FakeDriver yields TOOL_CALL+TOOL_RESULT, then RESULT
    out = [m async for m in rd.execute_agentic(prompt="do it", cwd="/tmp",
                                               instructions="be careful")]
    assert len(out) == 3                       # passthrough is transparent to the agent
    path = await rec.finalize(status="completed")
    sub = json.loads(path.read_text())["subagent_trajectories"][0]
    assert sub["steps"][0]["source"] == "system" and sub["steps"][0]["message"] == "be careful"
    assert sub["steps"][1]["message"] == "do it"
    assert sub["final_metrics"]["total_prompt_tokens"] == FakeDriver.USAGE.input_tokens


async def test_generate_records_prompts_result_and_cost(tmp_path):
    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={}
    )
    inv = rec.begin_invocation("plan_validator", model="m")
    rd = RecordingDriver(FakeDriver(), inv)

    output, session_id = await rd.generate("validate this", system_prompt="be strict")

    assert (output, session_id) == ("generated text", "sess-1")
    path = await rec.finalize(status="completed")
    sub = json.loads(path.read_text())["subagent_trajectories"][0]
    assert [s["source"] for s in sub["steps"]] == ["system", "user", "agent"]
    assert sub["steps"][0]["message"] == "be strict"
    assert sub["steps"][1]["message"] == "validate this"
    assert sub["steps"][2]["message"] == "generated text"
    assert sub["final_metrics"]["total_cost_usd"] == FakeDriver.USAGE.cost_usd


async def test_generate_serializes_schema_output(tmp_path):
    class Verdict(BaseModel):
        approved: bool

    class SchemaDriver(FakeDriver):
        async def generate(self, prompt, system_prompt=None, schema=None, **kwargs):
            return Verdict(approved=True), None

    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={}
    )
    inv = rec.begin_invocation("plan_validator", model="m")
    rd = RecordingDriver(SchemaDriver(), inv)

    output, _ = await rd.generate("judge", schema=Verdict)

    assert output == Verdict(approved=True)
    path = await rec.finalize(status="completed")
    sub = json.loads(path.read_text())["subagent_trajectories"][0]
    assert json.loads(sub["steps"][-1]["message"]) == {"approved": True}


async def test_stream_exception_still_records_partial_and_closes(tmp_path):
    class ExplodingDriver(FakeDriver):
        async def execute_agentic(self, prompt, cwd, **kwargs):
            yield AgenticMessage(type=AgenticMessageType.THINKING, content="hmm")
            raise RuntimeError("driver crashed")

    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={}
    )
    inv = rec.begin_invocation("developer", model="m")
    rd = RecordingDriver(ExplodingDriver(), inv)

    with pytest.raises(RuntimeError, match="driver crashed"):
        async for _ in rd.execute_agentic(prompt="p", cwd="/tmp"):
            pass

    assert inv.closed
    path = await rec.finalize(status="failed", failure_reason="crash")
    sub = json.loads(path.read_text())["subagent_trajectories"][0]
    assert sub["steps"][0]["message"] == "p"                     # prompt survived
    assert sub["steps"][1]["reasoning_content"] == "hmm"         # partial stream survived


async def test_recording_errors_do_not_break_agent_stream(tmp_path, monkeypatch):
    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={}
    )
    inv = rec.begin_invocation("developer", model="m")

    def boom(messages):
        raise RuntimeError("recording broke")

    monkeypatch.setattr(inv, "record_messages", boom)
    rd = RecordingDriver(FakeDriver(), inv)

    out = [m async for m in rd.execute_agentic(prompt="p", cwd="/tmp")]

    assert len(out) == 3            # full stream delivered despite recording failure
    assert inv.closed               # invocation closed with what it has


async def test_tool_definitions_copied_to_subagent_agent(tmp_path):
    class ToolDefDriver(FakeDriver):
        def get_tool_definitions(self) -> list[dict[str, Any]] | None:
            return [{"name": "write_file", "description": "writes a file"}]

    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={}
    )
    inv = rec.begin_invocation("developer", model="m")
    rd = RecordingDriver(ToolDefDriver(), inv)
    async for _ in rd.execute_agentic(prompt="p", cwd="/tmp"):
        pass

    path = await rec.finalize(status="completed")
    sub = json.loads(path.read_text())["subagent_trajectories"][0]
    assert sub["agent"]["tool_definitions"] == [
        {"name": "write_file", "description": "writes a file"}
    ]


async def test_get_usage_and_cleanup_session_delegate(tmp_path):
    rec = WorkflowTrajectoryRecorder(
        workflow_id=WF_ID, trajectory_dir=tmp_path, profile_snapshot={}
    )
    inv = rec.begin_invocation("developer", model="m")
    rd = RecordingDriver(FakeDriver(), inv)

    assert rd.get_usage() == FakeDriver.USAGE
    assert await rd.cleanup_session("sess-1") is True
