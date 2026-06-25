"""End-to-end integration tests for ATIF trajectory recording.

Enters through ``OrchestratorService`` with real Postgres fixtures
(``test_db``/``test_repository``) and a real LangGraph run. The driver is
mocked at the external boundary only (``ApiDriver.execute_agentic``), matching
the established integration-test pattern.
"""

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from harbor.utils.trajectory_validator import validate_trajectory

from amelia.core.types import Profile
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import AgenticMessage
from amelia.server.database.connection import Database
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.conftest import (
    PLAN_MARKDOWN,
    _architect_messages,
    _scripted_execute_agentic,
    _wait_for_status,
    api_profile,  # noqa: F401  (re-exported fixture)
    make_agentic_messages,
    make_reviewer_agentic_messages,
    orchestrator,  # noqa: F401  (re-exported fixture)
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _api_key(mock_api_key: None) -> None:
    """Allow ApiDriver construction (shared mock_api_key fixture, autouse)."""


class TestTrajectoryEndToEnd:
    """Canonical trajectory file is produced and indexed for implementation runs."""

    async def test_workflow_run_produces_canonical_trajectory(
        self,
        orchestrator: OrchestratorService,
        test_db: Database,
        api_profile: Profile,
        valid_worktree: str,
    ) -> None:
        scripts: list[list[AgenticMessage] | Exception] = [
            _architect_messages(),
            make_agentic_messages(),
            make_reviewer_agentic_messages(approved=True),
        ]
        with patch.object(ApiDriver, "execute_agentic", _scripted_execute_agentic(scripts)):
            workflow_id = await orchestrator.start_workflow(
                issue_id="TRAJ-1",
                worktree_path=valid_worktree,
                task_title="Add greeting helper",
                task_description="Add a greet() helper to hello.py",
            )
            await _wait_for_status(test_db, workflow_id, "blocked")
            await orchestrator.approve_workflow(workflow_id)

        row = await test_db.fetch_one(
            """
            SELECT status, trajectory_path, total_cost_usd, total_tokens, total_duration_ms
            FROM workflows WHERE id = $1
            """,
            workflow_id,
        )
        assert row is not None
        assert row["status"] == "completed"
        assert row["trajectory_path"], "trajectory_path index column was not set"

        data = json.loads(Path(row["trajectory_path"]).read_text())
        assert validate_trajectory(data)
        assert data["schema_version"] == "ATIF-v1.7"
        assert data["session_id"] == str(workflow_id)

        agents = [s["agent"]["name"] for s in data["subagent_trajectories"]]
        assert "architect" in agents
        assert "developer" in agents
        assert "reviewer" in agents

        outcome = data["extra"]["outcome"]
        assert outcome["status"] == "completed"
        assert outcome["pipeline"] == "implementation"
        assert outcome["reviews"], "final review verdicts missing from outcome"
        assert outcome["reviews"][0]["approved"] is True
        assert outcome["reviews"][0]["persona"] == "general"

        # Profile snapshot recorded on the parent trajectory
        assert data["extra"]["profile_id"] == api_profile.name
        assert data["extra"]["issue_id"] == "TRAJ-1"

        # Index columns mirror the file's final metrics
        assert row["total_cost_usd"] == data["final_metrics"].get("total_cost_usd")
        assert row["total_duration_ms"] is not None

        # Resolved prompts captured per invocation: system step then user step
        developer = next(
            s for s in data["subagent_trajectories"] if s["agent"]["name"] == "developer"
        )
        assert [step["source"] for step in developer["steps"][:2]] == ["system", "user"]
        # Untruncated driver stream follows the prompts
        assert any(step.get("tool_calls") for step in developer["steps"])

    async def test_failed_workflow_drains_partial_trajectory(
        self,
        orchestrator: OrchestratorService,
        test_db: Database,
        api_profile: Profile,
        valid_worktree: str,
    ) -> None:
        scripts: list[list[AgenticMessage] | Exception] = [
            _architect_messages(),
            ValueError("developer exploded"),
        ]
        with patch.object(ApiDriver, "execute_agentic", _scripted_execute_agentic(scripts)):
            workflow_id = await orchestrator.start_workflow(
                issue_id="TRAJ-2",
                worktree_path=valid_worktree,
                task_title="Failing task",
                task_description="The developer driver fails at the boundary",
            )
            await _wait_for_status(test_db, workflow_id, "blocked")
            with pytest.raises(ValueError, match="developer exploded"):
                await orchestrator.approve_workflow(workflow_id)

        row = await test_db.fetch_one(
            "SELECT status, trajectory_path FROM workflows WHERE id = $1", workflow_id
        )
        assert row is not None
        assert row["status"] == "failed"
        assert row["trajectory_path"], "failed workflow must still index its trajectory"

        data = json.loads(Path(row["trajectory_path"]).read_text())
        assert validate_trajectory(data)
        assert data["extra"]["outcome"]["status"] == "failed"
        assert data["extra"]["outcome"]["failure_reason"]

        # Steps captured up to the failure survived the drain
        agents = [s["agent"]["name"] for s in data["subagent_trajectories"]]
        assert "architect" in agents
        assert "developer" in agents
        developer = next(
            s for s in data["subagent_trajectories"] if s["agent"]["name"] == "developer"
        )
        assert developer["steps"], "partial developer steps were lost"
