"""Tests for projecting ATIF trajectories into dashboard wire models."""
import uuid

from harbor.models.trajectories import (
    Agent,
    FinalMetrics,
    Observation,
    ObservationResult,
    Step,
    SubagentTrajectoryRef,
    ToolCall,
    Trajectory,
)

import amelia
from amelia.server.models.events import EventType
from amelia.trajectory.projection import trajectory_to_events, trajectory_to_token_summary


WF_ID = uuid.UUID("00000000-0000-0000-0000-00000000a11a")


def make_subagent(
    name: str,
    trajectory_id: str,
    *,
    final_metrics: FinalMetrics | None,
    model: str | None = "claude-x",
) -> Trajectory:
    """Build an embedded subagent trajectory with prompt, thinking, tool, and result steps."""
    return Trajectory(
        trajectory_id=trajectory_id,
        agent=Agent(name=name, version=amelia.__version__, model_name=model),
        steps=[
            Step(step_id=1, source="system", message=f"You are the {name}."),
            Step(step_id=2, source="user", message="Fix the bug."),
            Step(step_id=3, source="agent", message="", reasoning_content="pondering"),
            Step(
                step_id=4,
                source="agent",
                message="",
                tool_calls=[
                    ToolCall(
                        tool_call_id="c1",
                        function_name="write_file",
                        arguments={"path": "a.py", "content": "x" * 5000},
                    )
                ],
                observation=Observation(
                    results=[ObservationResult(source_call_id="c1", content="ok: " + "y" * 5000)]
                ),
            ),
            Step(step_id=5, source="agent", message="fixed it"),
        ],
        final_metrics=final_metrics,
    )


def make_parent_step(step_id: int, agent_name: str, trajectory_id: str) -> Step:
    """Build a parent step delegating to an embedded subagent trajectory."""
    return Step(
        step_id=step_id,
        source="agent",
        message=f"Invoked {agent_name}",
        llm_call_count=0,
        observation=Observation(
            results=[
                ObservationResult(
                    subagent_trajectory_ref=[SubagentTrajectoryRef(trajectory_id=trajectory_id)]
                )
            ]
        ),
    )


def build_minimal_trajectory() -> Trajectory:
    """One developer invocation with prompts, thinking, one tool call, and a result."""
    sub = make_subagent(
        "developer",
        "developer-inv-1",
        final_metrics=FinalMetrics(
            total_prompt_tokens=10,
            total_completion_tokens=5,
            total_cached_tokens=2,
            total_cost_usd=0.01,
            total_steps=5,
        ),
    )
    return Trajectory(
        session_id=str(WF_ID),
        agent=Agent(name="amelia", version=amelia.__version__, model_name="orchestrator"),
        steps=[make_parent_step(1, "developer", "developer-inv-1")],
        final_metrics=FinalMetrics(total_cost_usd=0.01, total_steps=1),
        extra={"outcome": {"status": "completed"}},
        subagent_trajectories=[sub],
    )


def test_steps_project_to_workflow_events():
    traj = build_minimal_trajectory()
    events = trajectory_to_events(traj, workflow_id=WF_ID)

    tool_step_evt = next(e for e in events if e.event_type == EventType.CLAUDE_TOOL_CALL)
    assert tool_step_evt.agent == "developer"
    assert tool_step_evt.tool_name == "write_file"
    assert [e.sequence for e in events] == sorted(e.sequence for e in events)
    assert all(e.workflow_id == WF_ID for e in events)


def test_system_and_user_steps_are_skipped():
    events = trajectory_to_events(build_minimal_trajectory(), workflow_id=WF_ID)
    messages = [e.message for e in events]
    assert "You are the developer." not in messages
    assert "Fix the bug." not in messages


def test_reasoning_tool_result_and_final_output_mapping():
    events = trajectory_to_events(build_minimal_trajectory(), workflow_id=WF_ID)

    thinking = next(e for e in events if e.event_type == EventType.CLAUDE_THINKING)
    assert thinking.message == "pondering"
    assert thinking.agent == "developer"

    tool_result = next(e for e in events if e.event_type == EventType.CLAUDE_TOOL_RESULT)
    assert tool_result.tool_name == "write_file"
    assert tool_result.message.startswith("ok: ")

    assert events[-1].event_type == EventType.AGENT_OUTPUT
    assert events[-1].message == "fixed it"


def test_display_strings_are_truncated_but_ordering_is_preserved():
    events = trajectory_to_events(build_minimal_trajectory(), workflow_id=WF_ID)

    tool_call = next(e for e in events if e.event_type == EventType.CLAUDE_TOOL_CALL)
    assert tool_call.tool_input is not None
    assert len(tool_call.tool_input["content"]) < 5000  # truncated for display

    tool_result = next(e for e in events if e.event_type == EventType.CLAUDE_TOOL_RESULT)
    assert len(tool_result.message) < 5000


def test_multiple_subagents_flatten_in_invocation_order():
    dev = make_subagent("developer", "developer-inv-1", final_metrics=None)
    rev = make_subagent("reviewer", "reviewer-inv-2", final_metrics=None)
    traj = Trajectory(
        session_id=str(WF_ID),
        agent=Agent(name="amelia", version=amelia.__version__, model_name="orchestrator"),
        steps=[
            make_parent_step(1, "developer", "developer-inv-1"),
            make_parent_step(2, "reviewer", "reviewer-inv-2"),
        ],
        subagent_trajectories=[dev, rev],
    )

    events = trajectory_to_events(traj, workflow_id=WF_ID)
    agents = [e.agent for e in events]
    assert set(agents) == {"developer", "reviewer"}
    # All developer events come before all reviewer events (invocation order).
    assert agents.index("reviewer") == len([a for a in agents if a == "developer"])


def test_empty_trajectory_projects_to_no_events():
    traj = Trajectory(
        session_id=str(WF_ID),
        agent=Agent(name="amelia", version=amelia.__version__, model_name="orchestrator"),
        steps=[Step(step_id=1, source="system", message="No agent invocations recorded")],
    )
    assert trajectory_to_events(traj, workflow_id=WF_ID) == []


def test_token_summary_from_trajectory():
    summary = trajectory_to_token_summary(build_minimal_trajectory())
    assert summary.total_cost_usd == 0.01
    assert summary.total_input_tokens == 10
    assert summary.total_output_tokens == 5
    assert summary.total_cache_read_tokens == 2
    assert {u.agent for u in summary.breakdown} == {"developer"}
    assert summary.breakdown[0].model == "claude-x"


def test_token_summary_skips_subagents_without_metrics_and_handles_empty():
    dev = make_subagent("developer", "developer-inv-1", final_metrics=None)
    traj = Trajectory(
        session_id=str(WF_ID),
        agent=Agent(name="amelia", version=amelia.__version__, model_name="orchestrator"),
        steps=[make_parent_step(1, "developer", "developer-inv-1")],
        subagent_trajectories=[dev],
    )
    summary = trajectory_to_token_summary(traj)
    assert summary.breakdown == []
    assert summary.total_cost_usd == 0.0
