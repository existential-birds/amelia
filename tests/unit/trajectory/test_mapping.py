"""Tests for AgenticMessage → ATIF step mapping."""
import pytest

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
from amelia.trajectory import map_messages, usage_to_metrics


def test_tool_call_and_result_pair_into_one_step():
    steps = map_messages([
        AgenticMessage(type=AgenticMessageType.TOOL_CALL, tool_name="write_file",
                       tool_input={"path": "a.py", "content": "x" * 5000}, tool_call_id="c1"),
        AgenticMessage(type=AgenticMessageType.TOOL_RESULT, tool_name="write_file",
                       tool_output="ok: " + "y" * 5000, tool_call_id="c1"),
    ], start_id=3)
    assert len(steps) == 1
    step = steps[0]
    assert step.step_id == 3 and step.source == "agent"
    assert step.tool_calls[0].function_name == "write_file"
    assert step.tool_calls[0].arguments["content"] == "x" * 5000          # untruncated input
    assert step.observation.results[0].source_call_id == "c1"
    assert step.observation.results[0].content == "ok: " + "y" * 5000     # untruncated output


def test_thinking_result_and_error_mapping():
    steps = map_messages([
        AgenticMessage(type=AgenticMessageType.THINKING, content="pondering"),
        AgenticMessage(type=AgenticMessageType.RESULT, content="done", model="claude-x"),
    ], start_id=1)
    assert steps[0].reasoning_content == "pondering"
    assert steps[1].message == "done" and steps[1].model_name == "claude-x"
    err = map_messages([AgenticMessage(type=AgenticMessageType.RESULT,
                                       content="boom", is_error=True)], start_id=1)
    assert err[0].extra["is_error"] is True


def test_step_ids_are_sequential_from_start_id():
    steps = map_messages([
        AgenticMessage(type=AgenticMessageType.THINKING, content="a"),
        AgenticMessage(type=AgenticMessageType.TOOL_CALL, tool_name="ls",
                       tool_input={}, tool_call_id="c1"),
        AgenticMessage(type=AgenticMessageType.TOOL_RESULT, tool_name="ls",
                       tool_output="files", tool_call_id="c1"),
        AgenticMessage(type=AgenticMessageType.RESULT, content="done"),
    ], start_id=7)
    assert [s.step_id for s in steps] == [7, 8, 9]
    assert all(s.source == "agent" for s in steps)


def test_unmatched_tool_result_raises_naming_orphan_id():
    with pytest.raises(ValueError, match="c-orphan"):
        map_messages([
            AgenticMessage(type=AgenticMessageType.TOOL_RESULT, tool_name="ls",
                           tool_output="files", tool_call_id="c-orphan"),
        ], start_id=1)


def test_usage_messages_are_skipped():
    steps = map_messages([
        AgenticMessage(type=AgenticMessageType.USAGE,
                       usage=DriverUsage(input_tokens=10, output_tokens=5)),
        AgenticMessage(type=AgenticMessageType.RESULT, content="done"),
    ], start_id=1)
    assert len(steps) == 1
    assert steps[0].message == "done"


def test_result_falls_back_to_tool_output():
    steps = map_messages([
        AgenticMessage(type=AgenticMessageType.RESULT, tool_output="from tool"),
    ], start_id=1)
    assert steps[0].message == "from tool"


def test_usage_to_metrics_maps_fields_one_to_one():
    usage = DriverUsage(input_tokens=100, output_tokens=50,
                        cache_read_tokens=25, cost_usd=0.5)
    metrics = usage_to_metrics(usage, cost=0.02)
    assert metrics.prompt_tokens == 100
    assert metrics.completion_tokens == 50
    assert metrics.cached_tokens == 25
    assert metrics.cost_usd == 0.02

    empty = usage_to_metrics(DriverUsage(), cost=None)
    assert empty.prompt_tokens is None
    assert empty.cost_usd is None
