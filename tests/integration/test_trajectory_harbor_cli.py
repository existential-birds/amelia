"""Harbor CLI export gate against a real amelia trajectory.

Produces a canonical trajectory through the same production path as
``test_trajectory_end_to_end`` (real ``OrchestratorService`` + Postgres, driver
mocked at the external boundary only), projects it into harbor's export
layout, then drives the **actual** ``harbor traces export`` CLI as a
subprocess — the production-entrypoint test for the interchange contract.

Layout + command were verified against harbor 0.13.1:

- trial dir = any dir containing ``agent/``; ``result.json`` sits beside it
  and its ``agent.name`` must be a harbor ``AgentName`` enum value with
  ``SUPPORTS_ATIF`` (we stage ``"claude-code"``).
- the CLI ignores embedded ``subagent_trajectories``; each one must be
  projected to a sibling ``agent/trajectory.<trajectory_id>.json`` file.
  The canonical amelia storage file stays single-file (embedded) — staging
  for export is a projection, which is what ``arrange_harbor_layout`` does.
"""

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from amelia.core.types import Profile
from amelia.drivers.api import ApiDriver
from amelia.server.database.connection import Database
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.conftest import (
    make_agentic_messages,
    make_reviewer_agentic_messages,
)
from tests.integration.test_trajectory_end_to_end import (  # noqa: F401
    _api_key,
    _architect_messages,
    _scripted_execute_agentic,
    _wait_for_status,
    api_profile,
    orchestrator,
    trajectory_dir,
)


pytestmark = pytest.mark.integration


EXPORT_ARGS = ("--verbose", "--path")


def arrange_harbor_layout(trajectory_run_dir: Path) -> Path:
    """Project amelia's canonical trajectory into harbor's export layout.

    Builds ``<root>/trial-1/{result.json,agent/trajectory.json}`` and writes
    each embedded subagent trajectory to a sibling
    ``agent/trajectory.<trajectory_id>.json`` (the CLI only exports subagent
    rows from sibling files, never from the embedded list).

    Args:
        trajectory_run_dir: Directory holding the canonical ``trajectory.json``.

    Returns:
        The staging root to pass to ``harbor traces export --path``.
    """
    data = json.loads((trajectory_run_dir / "trajectory.json").read_text())

    root = trajectory_run_dir.parent / f"{trajectory_run_dir.name}-harbor-export"
    trial_dir = root / "trial-1"
    agent_dir = trial_dir / "agent"
    agent_dir.mkdir(parents=True)

    result = {
        "config": {
            # Hard constraint from Task 0: agent.name must be a harbor
            # AgentName enum value whose agent class has SUPPORTS_ATIF.
            "agent": {"name": "claude-code", "model_name": "claude-sonnet-4"},
            "task_name": "amelia-workflow",
            "trial_name": "trial-1",
            "job_id": data["session_id"],
        },
        "task_name": "amelia-workflow",
        "trial_name": "trial-1",
        "started_at": "2026-06-09T00:00:00Z",
    }
    (trial_dir / "result.json").write_text(json.dumps(result, indent=2))

    (agent_dir / "trajectory.json").write_text(json.dumps(data, indent=2))
    for subagent in data.get("subagent_trajectories", []):
        sub_path = agent_dir / f"trajectory.{subagent['trajectory_id']}.json"
        sub_path.write_text(json.dumps(subagent, indent=2))

    return root


def _exported_row_count(stdout: str) -> int:
    """Parse the row count from the CLI's ``Exported N rows from <path>`` summary.

    The CLI builds the dataset in memory (no on-disk artifact without
    ``--push``), so the printed summary is the observable export result.
    """
    match = re.search(r"Exported (\d+) rows", stdout)
    assert match is not None, f"no export summary in harbor output: {stdout!r}"
    return int(match.group(1))


@pytest.fixture
async def completed_workflow_trajectory_dir(
    orchestrator: OrchestratorService,  # noqa: F811
    test_db: Database,
    api_profile: Profile,  # noqa: F811
    valid_worktree: str,
) -> Path:
    """Run a full implementation workflow and return its trajectory directory."""
    scripts = [
        _architect_messages(),
        make_agentic_messages(),
        make_reviewer_agentic_messages(approved=True),
    ]
    with patch.object(ApiDriver, "execute_agentic", _scripted_execute_agentic(scripts)):
        workflow_id = await orchestrator.start_workflow(
            issue_id="TRAJ-HARBOR-1",
            worktree_path=valid_worktree,
            task_title="Add greeting helper",
            task_description="Add a greet() helper to hello.py",
        )
        await _wait_for_status(test_db, workflow_id, "blocked")
        await orchestrator.approve_workflow(workflow_id)

    row = await test_db.fetch_one(
        "SELECT status, trajectory_path FROM workflows WHERE id = $1", workflow_id
    )
    assert row is not None and row["status"] == "completed"
    return Path(row["trajectory_path"]).parent


class TestHarborCliExportGate:
    """`harbor traces export` must consume amelia's trajectory end to end."""

    async def test_harbor_cli_consumes_amelia_trajectory(
        self, completed_workflow_trajectory_dir: Path
    ) -> None:
        layout = arrange_harbor_layout(completed_workflow_trajectory_dir)

        proc = subprocess.run(
            ["uv", "run", "harbor", "traces", "export", *EXPORT_ARGS, str(layout)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert proc.returncode == 0, proc.stderr
        assert _exported_row_count(proc.stdout) > 0, proc.stdout
        # Spike caveat: the CLI ignores embedded subagents — the projection must
        # surface every invocation as a sibling file, one exported row each.
        for agent in ("architect", "developer", "reviewer"):
            assert f"subagent trajectory {agent}-inv" in proc.stdout, proc.stdout
