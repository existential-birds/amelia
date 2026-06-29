"""Unit tests for the generative MoA aggregator node.

Uses a real temporary git repository so diff application exercises the
production ``git apply`` path.
"""

import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.pipelines.implementation.moa import generative_moa_aggregator_node
from amelia.pipelines.implementation.state import (
    GenerativeMoACandidate,
    GenerativeMoAFailedCandidate,
    GenerativeMoASucceededCandidate,
    ImplementationState,
)
from tests.unit.pipelines.conftest import _git


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _modify_patch(path: str, old: str, new: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index 1111111..2222222 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        f"-{old}\n"
        f"+{new}\n"
    )


def _real_patch(repo: Path, path: str, content: str) -> str:
    target = repo / path
    original = target.read_text()
    target.write_text(content)
    try:
        return _git_out(repo, "diff", "--binary")
    finally:
        target.write_text(original)


def _make_profile(repo: Path) -> Profile:
    agents = {
        "architect": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        "reviewer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
    }
    return Profile(name="test", tracker=TrackerType.NOOP, repo_root=str(repo), agents=agents)


def _make_state(
    profile: Profile, candidates: Sequence[GenerativeMoACandidate]
) -> ImplementationState:
    return ImplementationState(
        workflow_id=uuid4(),
        created_at=datetime.now(UTC),
        status="running",
        profile_id=profile.name,
        goal="Implement the feature",
        generative_moa_candidates=list(candidates),
    )


def _config(profile: Profile, state: ImplementationState) -> RunnableConfig:
    return cast(
        RunnableConfig,
        {"configurable": {"profile": profile, "thread_id": str(state.workflow_id)}},
    )


def test_moa_selection_has_no_agents_layer_aggregator_abstraction() -> None:
    moa_path = Path(generative_moa_aggregator_node.__code__.co_filename)
    assert not (moa_path.parents[2] / "agents" / "aggregator.py").exists()


@pytest.mark.asyncio
async def test_applies_selected_candidate_diff(git_repo: Path) -> None:
    profile = _make_profile(git_repo)
    base_commit = _git_out(git_repo, "rev-parse", "HEAD").strip()
    candidates = [
        GenerativeMoASucceededCandidate(
            proposer_id=0,
            status="succeeded",
            model="m0",
            diff=_modify_patch("code.txt", "line1", "line1 by p0"),
        ),
    ]
    state = _make_state(profile, candidates)

    result = await generative_moa_aggregator_node(state, _config(profile, state))

    assert (git_repo / "code.txt").read_text() == "line1 by p0\n"
    selected = result["generative_moa_selected"]
    assert selected.proposer_id == 0
    assert result["base_commit"] == base_commit
    assert "line1 by p0" in _git_out(git_repo, "diff", base_commit, "HEAD")


@pytest.mark.asyncio
async def test_falls_back_to_next_candidate_on_bad_diff(git_repo: Path) -> None:
    profile = _make_profile(git_repo)
    candidates = [
        # Selected first by the aggregator, but its context does not match.
        GenerativeMoASucceededCandidate(
            proposer_id=0,
            status="succeeded",
            model="m0",
            diff=_modify_patch("code.txt", "does-not-match", "broken"),
        ),
        GenerativeMoASucceededCandidate(
            proposer_id=1,
            status="succeeded",
            model="m1",
            diff=_modify_patch("code.txt", "line1", "line1 by p1"),
        ),
    ]
    state = _make_state(profile, candidates)

    result = await generative_moa_aggregator_node(state, _config(profile, state))

    assert (git_repo / "code.txt").read_text() == "line1 by p1\n"
    assert result["generative_moa_selected"].proposer_id == 1


@pytest.mark.asyncio
async def test_failed_three_way_candidate_does_not_dirty_fallback(
    git_repo: Path,
) -> None:
    profile = _make_profile(git_repo)
    conflicting_patch = _real_patch(git_repo, "code.txt", "line1 by p0\n")

    (git_repo / "code.txt").write_text("line1 changed upstream\n")
    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-m", "upstream change")

    candidates = [
        GenerativeMoASucceededCandidate(
            proposer_id=0,
            status="succeeded",
            model="m0",
            diff=conflicting_patch,
        ),
        GenerativeMoASucceededCandidate(
            proposer_id=1,
            status="succeeded",
            model="m1",
            diff=_real_patch(git_repo, "code.txt", "line1 by p1\n"),
        ),
    ]
    state = _make_state(profile, candidates)

    result = await generative_moa_aggregator_node(state, _config(profile, state))

    assert result["generative_moa_selected"].proposer_id == 1
    assert (git_repo / "code.txt").read_text() == "line1 by p1\n"
    assert _git_out(git_repo, "status", "--porcelain") == ""


@pytest.mark.asyncio
async def test_no_successful_candidates_raises(git_repo: Path) -> None:
    profile = _make_profile(git_repo)
    candidates = [
        GenerativeMoAFailedCandidate(
            proposer_id=0, status="failed", model="m0", error="boom"
        ),
    ]
    state = _make_state(profile, candidates)

    with pytest.raises(ValueError, match="no successful candidates"):
        await generative_moa_aggregator_node(state, _config(profile, state))


@pytest.mark.asyncio
async def test_all_candidate_diffs_unappliable_raises(git_repo: Path) -> None:
    profile = _make_profile(git_repo)
    candidates = [
        GenerativeMoASucceededCandidate(
            proposer_id=0,
            status="succeeded",
            model="m0",
            diff=_modify_patch("code.txt", "nope", "x"),
        ),
        GenerativeMoASucceededCandidate(
            proposer_id=1,
            status="succeeded",
            model="m1",
            diff=_modify_patch("code.txt", "also-nope", "y"),
        ),
    ]
    state = _make_state(profile, candidates)

    with pytest.raises(ValueError, match="no candidate diff applied cleanly"):
        await generative_moa_aggregator_node(state, _config(profile, state))
