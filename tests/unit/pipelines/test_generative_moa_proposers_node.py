"""Unit tests for the generative MoA proposers node.

Uses a real temporary git repository so worktree creation and diff collection
exercise production code paths. Only the Developer agent is stubbed (no live
LLM): each stub writes a distinct file into its isolated worktree.
"""

import asyncio
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.pipelines.implementation.moa import (
    _collect_worktree_diff,
    _create_worktree,
    _remove_worktree,
    generative_moa_proposers_node,
)
from amelia.pipelines.implementation.state import ImplementationState


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _config_with(
    profile: Profile,
    state: ImplementationState,
    **configurable: Any,
) -> RunnableConfig:
    return cast(
        RunnableConfig,
        {
            "configurable": {
                "profile": profile,
                "thread_id": str(state.workflow_id),
                **configurable,
            }
        },
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create an initialized git repo with one committed file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo


def _make_profile(repo: Path, moa_options: dict[str, Any]) -> Profile:
    agents = {
        "architect": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        "developer": AgentConfig(
            driver=DriverType.CLAUDE, model="sonnet", options={"moa": moa_options}
        ),
        "reviewer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
    }
    return Profile(name="test", tracker=TrackerType.NOOP, repo_root=str(repo), agents=agents)


def _make_state(profile: Profile) -> ImplementationState:
    return ImplementationState(
        workflow_id=uuid4(),
        created_at=datetime.now(UTC),
        status="running",
        profile_id=profile.name,
        goal="Implement the feature",
        plan_markdown="## Task 1\n\nDo the thing.",
    )


class _WritingDeveloper:
    """Stub Developer that writes a file named after its model into the worktree."""

    def __init__(self, config: Any, prompts: Any = None, sandbox_provider: Any = None, tool_context: Any = None) -> None:
        self.config = config
        self.driver = None

    async def run(self, state: Any, profile: Any, workflow_id: Any, **kwargs: Any) -> Any:
        path = Path(profile.repo_root) / f"out_{self.config.model}.txt"
        path.write_text(f"change by {self.config.model}\n")
        yield (
            state.model_copy(
                update={"agentic_status": "completed", "final_response": f"done {self.config.model}"}
            ),
            None,
        )


def _failing_developer_for(*models: str) -> type:
    """Build a stub Developer class that raises for the given models."""
    fail = set(models)

    class _FailingDeveloper(_WritingDeveloper):
        async def run(self, state: Any, profile: Any, workflow_id: Any, **kwargs: Any) -> Any:
            if self.config.model in fail:
                raise RuntimeError(f"proposer {self.config.model} blew up")
            async for item in super().run(state, profile, workflow_id, **kwargs):
                yield item

    return _FailingDeveloper


def _config(profile: Profile, state: ImplementationState) -> RunnableConfig:
    return _config_with(profile, state)


@pytest.mark.asyncio
async def test_proposers_produce_distinct_worktrees_and_diffs(git_repo: Path) -> None:
    profile = _make_profile(
        git_repo,
        {"enabled": True, "proposer_count": 2, "proposer_models": ["m0", "m1"]},
    )
    state = _make_state(profile)

    with patch("amelia.pipelines.implementation.moa.Developer", _WritingDeveloper):
        result = await generative_moa_proposers_node(state, _config(profile, state))

    candidates = result["generative_moa_candidates"]
    assert len(candidates) == 2
    assert all(c.status == "succeeded" for c in candidates)
    assert {c.model for c in candidates} == {"m0", "m1"}

    # Each candidate's diff captures the file its proposer wrote in isolation.
    by_model = {c.model: c for c in candidates}
    assert "out_m0.txt" in (by_model["m0"].diff or "")
    assert "out_m1.txt" in (by_model["m1"].diff or "")
    assert "out_m1.txt" not in (by_model["m0"].diff or "")

    # Worktrees are distinct paths.
    paths = {c.worktree_path for c in candidates}
    assert len(paths) == 2


@pytest.mark.asyncio
async def test_primary_worktree_not_mutated(git_repo: Path) -> None:
    profile = _make_profile(
        git_repo, {"enabled": True, "proposer_count": 2, "proposer_models": ["m0", "m1"]}
    )
    state = _make_state(profile)

    with patch("amelia.pipelines.implementation.moa.Developer", _WritingDeveloper):
        await generative_moa_proposers_node(state, _config(profile, state))

    # No proposer output files leaked into the primary worktree.
    leaked = list(git_repo.glob("out_*.txt"))
    assert leaked == []
    status = subprocess.run(
        ["git", "-C", str(git_repo), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status.strip() == ""


@pytest.mark.asyncio
async def test_collect_worktree_diff_includes_binary_patch(git_repo: Path) -> None:
    (git_repo / "asset.bin").write_bytes(bytes(range(256)) * 4)

    diff = await _collect_worktree_diff(git_repo)

    assert "GIT binary patch" in diff


@pytest.mark.asyncio
async def test_worktree_setup_and_cleanup_filesystem_calls_run_off_loop(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def record_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
        calls.append(getattr(func, "__name__", repr(func)))
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", record_to_thread)
    worktree = tmp_path / "moa-worktree"

    await _create_worktree(git_repo, worktree)
    await _remove_worktree(git_repo, worktree)

    assert "exists" in calls
    assert "mkdir" in calls


@pytest.mark.asyncio
async def test_sandboxed_developer_execution_rejected_for_worktree_moa(
    git_repo: Path,
) -> None:
    profile = _make_profile(git_repo, {"enabled": True, "proposer_count": 1})
    state = _make_state(profile)

    with pytest.raises(ValueError, match="does not support sandboxed Developer"):
        await generative_moa_proposers_node(
            state,
            _config_with(profile, state, sandbox_provider=object()),
        )


@pytest.mark.asyncio
async def test_single_proposer_failure_degrades(git_repo: Path) -> None:
    profile = _make_profile(
        git_repo, {"enabled": True, "proposer_count": 2, "proposer_models": ["m0", "m1"]}
    )
    state = _make_state(profile)

    with patch(
        "amelia.pipelines.implementation.moa.Developer", _failing_developer_for("m1")
    ):
        result = await generative_moa_proposers_node(state, _config(profile, state))

    candidates = result["generative_moa_candidates"]
    assert len(candidates) == 2
    by_model = {c.model: c for c in candidates}
    assert by_model["m0"].status == "succeeded"
    assert by_model["m1"].status == "failed"
    assert "blew up" in (by_model["m1"].error or "")


@pytest.mark.asyncio
async def test_all_proposers_fail_raises(git_repo: Path) -> None:
    profile = _make_profile(
        git_repo, {"enabled": True, "proposer_count": 2, "proposer_models": ["m0", "m1"]}
    )
    state = _make_state(profile)

    with (
        patch(
            "amelia.pipelines.implementation.moa.Developer",
            _failing_developer_for("m0", "m1"),
        ),
        pytest.raises(ValueError, match="All 2 generative MoA proposers failed"),
    ):
        await generative_moa_proposers_node(state, _config(profile, state))


@pytest.mark.asyncio
async def test_missing_goal_raises(git_repo: Path) -> None:
    profile = _make_profile(git_repo, {"enabled": True, "proposer_count": 1})
    state = _make_state(profile).model_copy(update={"goal": None})

    with pytest.raises(ValueError, match="require a goal"):
        await generative_moa_proposers_node(state, _config(profile, state))
