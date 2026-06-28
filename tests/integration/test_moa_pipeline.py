"""End-to-end integration test for the advisory Mixture-of-Agents (MoA) pipeline.

Enters through the production server entrypoint: ``OrchestratorService`` with
real Postgres fixtures and a real LangGraph run built by
``GraphRunner.create_server_graph(profile=...)``. With advisory MoA enabled on
the architect agent config, that builds the ``moa_proposers_node`` ->
``aggregator_node`` -> ``plan_validator_node`` graph, exercising the REAL
``Architect``/``Aggregator`` agents and nodes.

The ONLY thing mocked is the external LLM boundary (``ApiDriver.execute_agentic``).
The mock is dispatched purely by request kwargs (``required_tool`` /
``required_file_path`` / ``instructions``) so concurrent proposers consume it
deterministically. It returns ``write_plan`` tool calls carrying valid
``WritePlanInput`` so the real agents/nodes drive the genuine file-on-disk plan
contract that ``plan_validator_node`` consumes.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.conftest import (
    _wait_for_status,
    make_agentic_messages,
    make_reviewer_agentic_messages,
)


pytestmark = pytest.mark.integration


# Distinctive goal markers so on-disk plan content + plan_cache can be asserted
# to come from the right producer (a proposer vs. the synthesizing aggregator).
PROPOSER_GOAL = "Proposer plan: add a greet() helper to hello.py"
AGGREGATOR_GOAL = "Synthesized plan: add a greet() helper to hello.py"


@pytest.fixture(autouse=True)
def _api_key(mock_api_key: None) -> None:
    """Allow ApiDriver construction (shared mock_api_key fixture, autouse)."""


def _write_plan_messages(goal: str) -> list[AgenticMessage]:
    """A driver stream that issues a single valid ``write_plan`` tool call.

    The node overrides ``file_path`` with the authoritative plan path, so the
    placeholder here is irrelevant; the structured fields must validate against
    ``WritePlanInput`` because the real node renders them to markdown on disk.
    """
    write_plan_input: dict[str, Any] = {
        "goal": goal,
        "architecture_summary": "Add one pure helper function plus a unit test.",
        "tech_stack": ["Python"],
        "tasks": [
            {
                "number": "1",
                "title": "Implement greet helper",
                "files_to_create": ["hello.py"],
                "steps": [
                    "Write a failing test for greet().",
                    "Implement greet() returning 'hello'.",
                    "Run pytest to confirm it passes.",
                ],
            }
        ],
        "file_path": "/docs/plans/plan.md",
    }
    return [
        AgenticMessage(type=AgenticMessageType.THINKING, content="Planning..."),
        AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="write_plan",
            tool_input=write_plan_input,
            tool_call_id="call-write-plan",
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name="write_plan",
            tool_output="Plan written.",
            tool_call_id="call-write-plan",
        ),
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=f"Wrote the plan. {goal}",
            session_id="sess-plan",
        ),
    ]


def _moa_dispatch_execute_agentic(*, failing_proposer: str | None = None) -> Any:
    """Build an ``execute_agentic`` replacement dispatched by request kwargs.

    Dispatch is stateless (no call ordering), so concurrently-running proposers
    are handled deterministically:

    - ``required_tool == "write_plan"`` -> a planner (architect proposer or the
      aggregator). The aggregator targets the canonical path; a proposer targets
      a ``-proposerN`` path. Both emit a real ``write_plan`` tool call. If
      ``failing_proposer`` matches the request's ``required_file_path``, that one
      proposer's LLM call raises (best-effort path).
    - reviewer system prompt -> a parseable approval review.
    - everything else -> the developer write_file stream.
    """

    async def fake_execute_agentic(
        self: ApiDriver, prompt: str, cwd: str, **kwargs: Any
    ) -> AsyncGenerator[AgenticMessage, None]:
        # Mirror the real ApiDriver recording per-invocation usage.
        self._usage = DriverUsage(
            input_tokens=100, output_tokens=50, duration_ms=1500, model="claude-x"
        )
        instructions = (kwargs.get("instructions") or "").lower()
        required_tool = kwargs.get("required_tool")
        required_file_path = kwargs.get("required_file_path") or ""

        if required_tool == "write_plan":
            if failing_proposer is not None and failing_proposer in required_file_path:
                raise RuntimeError(f"proposer LLM call failed: {required_file_path}")
            is_aggregator = "synthesiz" in instructions
            goal = AGGREGATOR_GOAL if is_aggregator else PROPOSER_GOAL
            for msg in _write_plan_messages(goal):
                yield msg
            return

        if "code reviewer" in instructions:
            for msg in make_reviewer_agentic_messages(approved=True):
                yield msg
            return

        for msg in make_agentic_messages():
            yield msg

    return fake_execute_agentic


@pytest.fixture
async def moa_profile(
    test_profile_repository: ProfileRepository,
    valid_worktree: str,
) -> Profile:
    """Activate an api-driver profile with advisory MoA enabled on the architect.

    No explicit ``aggregator`` agent is configured, so the aggregator node also
    exercises its fallback to the architect config.
    """
    base = AgentConfig(driver="api", model="anthropic/claude-sonnet-4-20250514")
    architect = AgentConfig(
        driver="api",
        model="anthropic/claude-sonnet-4-20250514",
        options={"moa": {"enabled": True, "proposer_count": 2}},
    )
    profile = Profile(
        name="test",
        tracker="noop",
        repo_root=valid_worktree,
        agents={
            "architect": architect,
            "developer": base,
            "reviewer": base,
            "plan_validator": base,
            "evaluator": base,
            "task_reviewer": base,
        },
    )
    await test_profile_repository.create_profile(profile)
    await test_profile_repository.set_active(profile.name)
    return profile


def _canonical_plan_path(worktree: str, issue_id: str) -> Path:
    from amelia.core.constants import resolve_plan_path  # noqa: PLC0415

    rel = resolve_plan_path("docs/plans/{date}-{issue_key}.md", issue_id)
    return Path(worktree) / rel


class TestMoAPipelineEndToEnd:
    """The MoA graph synthesizes one canonical plan the Developer then executes."""

    async def test_two_proposers_synthesize_canonical_plan(
        self,
        orchestrator: OrchestratorService,
        test_db: Database,
        test_repository: Any,
        moa_profile: Profile,
        valid_worktree: str,
    ) -> None:
        """Both proposers succeed -> aggregator synthesizes the canonical plan.

        Observable consequences asserted: the canonical plan file exists on disk
        with the AGGREGATOR's synthesized content; ``plan_validator_node``
        populated goal/plan_markdown/total_tasks (surfaced via plan_cache); and
        the Developer stage runs to completion on the non-empty goal.
        """
        issue_id = "MOA-1"
        mock = _moa_dispatch_execute_agentic()
        with patch.object(ApiDriver, "execute_agentic", mock):
            workflow_id = await orchestrator.start_workflow(
                issue_id=issue_id,
                worktree_path=valid_worktree,
                task_title="Add greeting helper",
                task_description="Add a greet() helper to hello.py",
            )
            await _wait_for_status(test_db, workflow_id, "blocked")

            # Canonical plan file is on disk with the synthesized (aggregator) content.
            canonical = _canonical_plan_path(valid_worktree, issue_id)
            assert canonical.exists(), f"canonical plan not written at {canonical}"
            content = canonical.read_text()
            assert AGGREGATOR_GOAL in content, "canonical plan lacks synthesized content"

            # plan_validator_node populated goal / plan_markdown / total_tasks.
            workflow = await test_repository.get(workflow_id)
            assert workflow is not None
            assert workflow.plan_cache is not None
            assert workflow.plan_cache.goal == AGGREGATOR_GOAL
            plan_markdown = await workflow.plan_cache.get_plan_markdown()
            assert plan_markdown and AGGREGATOR_GOAL in plan_markdown
            assert workflow.plan_cache.total_tasks == 1

            # The Developer stage receives a non-empty goal and runs to completion.
            await orchestrator.approve_workflow(workflow_id)

        row = await test_db.fetch_one(
            "SELECT status FROM workflows WHERE id = $1", workflow_id
        )
        assert row is not None
        assert row["status"] == "completed", (
            "developer did not run to completion on the synthesized goal"
        )

    async def test_best_effort_one_proposer_fails_still_plans(
        self,
        orchestrator: OrchestratorService,
        test_db: Database,
        test_repository: Any,
        moa_profile: Profile,
        valid_worktree: str,
    ) -> None:
        """One proposer's LLM call errors -> the surviving proposer is promoted.

        With a single survivor the aggregator promotes it directly (no
        synthesis), and the run still produces a valid canonical plan with a
        non-empty Developer-visible goal.
        """
        issue_id = "MOA-2"
        # Fail proposer index 1; proposer 0 survives.
        mock = _moa_dispatch_execute_agentic(failing_proposer="proposer1")
        with patch.object(ApiDriver, "execute_agentic", mock):
            workflow_id = await orchestrator.start_workflow(
                issue_id=issue_id,
                worktree_path=valid_worktree,
                task_title="Add greeting helper",
                task_description="Add a greet() helper to hello.py",
            )
            await _wait_for_status(test_db, workflow_id, "blocked")

        # Canonical plan exists (promoted survivor) and the developer-visible
        # goal is non-empty.
        canonical = _canonical_plan_path(valid_worktree, issue_id)
        assert canonical.exists(), f"canonical plan not written at {canonical}"
        assert PROPOSER_GOAL in canonical.read_text()

        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.plan_cache is not None
        assert workflow.plan_cache.goal == PROPOSER_GOAL
        assert workflow.plan_cache.total_tasks == 1
