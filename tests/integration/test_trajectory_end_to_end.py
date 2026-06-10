"""End-to-end integration tests for ATIF trajectory recording.

Enters through ``OrchestratorService`` with real Postgres fixtures
(``test_db``/``test_repository``) and a real LangGraph run. The driver is
mocked at the external boundary only (``ApiDriver.execute_agentic``), matching
the established integration-test pattern.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from harbor.utils.trajectory_validator import validate_trajectory
from langgraph.checkpoint.memory import MemorySaver

from amelia.core.types import Profile
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.conftest import (
    make_agentic_messages,
    make_profile,
    make_reviewer_agentic_messages,
)


pytestmark = pytest.mark.integration


PLAN_MARKDOWN = """# Plan: Add greeting helper

**Goal:** Add a greeting helper function to hello.py that returns a friendly message.

### Task 1: Implement the greeting helper

- Create `hello.py` with a `greet()` function returning the string "hello".
- Keep the implementation minimal; do not create any other files.
- This plan drives the integration test through architect, developer, and reviewer.
"""


@pytest.fixture(autouse=True)
def _api_key(mock_api_key: None) -> None:
    """Allow ApiDriver construction (shared mock_api_key fixture, autouse)."""


@pytest.fixture
async def api_profile(
    test_profile_repository: ProfileRepository,
    valid_worktree: str,
) -> Profile:
    """Create and activate an api-driver profile so ApiDriver mocking applies."""
    profile = make_profile(driver="api", repo_root=valid_worktree)
    await test_profile_repository.create_profile(profile)
    await test_profile_repository.set_active(profile.name)
    return profile


@pytest.fixture
def trajectory_dir(tmp_path: Path) -> Path:
    """Isolated trajectory root for the orchestrator under test."""
    return tmp_path / "trajectories"


@pytest.fixture
def orchestrator(
    test_event_bus: EventBus,
    test_repository: WorkflowRepository,
    test_profile_repository: ProfileRepository,
    trajectory_dir: Path,
) -> OrchestratorService:
    """Real OrchestratorService with real Postgres repos and a working checkpointer."""
    return OrchestratorService(
        event_bus=test_event_bus,
        repository=test_repository,
        profile_repo=test_profile_repository,
        checkpointer=MemorySaver(),
        trajectory_dir=trajectory_dir,
    )


def _architect_messages() -> list[AgenticMessage]:
    """Architect stream: RESULT carries the plan (raw-output fallback writes the file)."""
    return [
        AgenticMessage(type=AgenticMessageType.THINKING, content="Designing the plan..."),
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=PLAN_MARKDOWN,
            session_id="sess-architect",
        ),
    ]


def _scripted_execute_agentic(
    scripts: list[list[AgenticMessage] | Exception],
) -> Any:
    """Build an execute_agentic replacement that plays one script per call.

    Calls beyond the script list replay the last script. An ``Exception``
    entry raises instead of yielding (driver failure at the boundary).
    """
    call_count = {"n": 0}

    async def fake_execute_agentic(
        self: Any, prompt: str, cwd: str, **kwargs: Any
    ) -> AsyncGenerator[AgenticMessage, None]:
        idx = min(call_count["n"], len(scripts) - 1)
        call_count["n"] += 1
        script = scripts[idx]
        if isinstance(script, Exception):
            raise script
        for msg in script:
            yield msg

    return fake_execute_agentic


async def _wait_for_status(
    test_db: Database,
    workflow_id: uuid.UUID,
    status: str,
    timeout: float = 60.0,
) -> None:
    """Poll the workflows row until it reaches *status* (or fail loudly)."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last_seen: str | None = None
    while loop.time() < deadline:
        row = await test_db.fetch_one(
            "SELECT status FROM workflows WHERE id = $1", workflow_id
        )
        if row is not None:
            last_seen = row["status"]
            if last_seen == status:
                return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"workflow {workflow_id} never reached {status!r} (last seen: {last_seen!r})"
    )


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
