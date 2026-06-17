"""Tests for call_reviewer_node orchestrator function.

Tests the review node behavior including base_commit fallback computation.
"""

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import ReviewResult
from amelia.pipelines.nodes import call_reviewer_node


_APPROVED_RESULT = ReviewResult(
    reviewer_persona="Agentic",
    approved=True,
    comments=[],
    severity="none",
)


@pytest.fixture(autouse=True)
def _mock_skill_detection():
    """Mock skill detection/loading for all review node tests."""
    with (
        patch(
            "amelia.pipelines.nodes._run_git_command",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch("amelia.pipelines.nodes.detect_stack", return_value=set()),
        patch("amelia.pipelines.nodes.load_skills", return_value=""),
    ):
        yield


@pytest.fixture
def run_reviewer_node(
    mock_execution_state_factory: Callable[..., Any],
    mock_runnable_config: Callable[..., dict[str, Any]],
) -> Callable[..., Any]:
    """Run call_reviewer_node with a mock Reviewer wired up.

    Returns a callable ``async (base_commit, get_commit_return, **state_kw)``
    that yields ``(result, captured_base_commits, mock_get_commit, mock_reviewer)``.
    """

    async def _run(
        base_commit: str | None = None,
        get_commit_return: str | None = "abc123def456",
        review_result: ReviewResult = _APPROVED_RESULT,
        agentic_review_override: Any = None,
        **state_kwargs: Any,
    ) -> dict[str, Any]:
        state, profile = mock_execution_state_factory(
            goal=state_kwargs.pop("goal", "Test goal"),
            base_commit=base_commit,
            **state_kwargs,
        )

        captured_base_commit: list[str] = []

        async def mock_agentic_review(state, base_commit: str, profile, *, workflow_id: str, diff_path: str | None = None):
            captured_base_commit.append(base_commit)
            return review_result, "session-123"

        config = mock_runnable_config(profile=profile)

        with (
            patch(
                "amelia.pipelines.nodes.get_current_commit",
                new_callable=AsyncMock,
                return_value=get_commit_return,
            ) as mock_get_commit,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_class,
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            if agentic_review_override is not None:
                mock_reviewer.agentic_review = agentic_review_override
            else:
                mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer.review = AsyncMock()
            mock_reviewer_class.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

        return {
            "result": result,
            "captured_base_commit": captured_base_commit,
            "mock_get_commit": mock_get_commit,
            "mock_reviewer": mock_reviewer,
        }

    return _run


class TestCallReviewNodeBaseCommitFallback:
    """Tests for base_commit fallback computation in call_reviewer_node."""

    @pytest.mark.asyncio
    async def test_computes_base_commit_when_missing(self, run_reviewer_node):
        """When base_commit is None, review node should compute it using get_current_commit."""
        out = await run_reviewer_node(base_commit=None, get_commit_return="abc123def456")

        out["mock_get_commit"].assert_called_once()
        assert out["captured_base_commit"] == ["abc123def456"]
        assert len(out["result"]["last_reviews"]) == 1
        assert out["result"]["last_reviews"][0].reviewer_persona == "general"

    @pytest.mark.asyncio
    async def test_uses_existing_base_commit_when_present(self, run_reviewer_node):
        """When base_commit is already set, review node should use it directly."""
        out = await run_reviewer_node(base_commit="existing123commit")

        out["mock_get_commit"].assert_not_called()
        assert out["captured_base_commit"] == ["existing123commit"]
        assert len(out["result"]["last_reviews"]) == 1
        assert out["result"]["last_reviews"][0].reviewer_persona == "general"

    @pytest.mark.asyncio
    async def test_falls_back_to_head_when_get_current_commit_fails(self, run_reviewer_node):
        """When get_current_commit returns None, review node should fall back to HEAD."""
        out = await run_reviewer_node(base_commit=None, get_commit_return=None)

        out["mock_get_commit"].assert_called_once()
        assert out["captured_base_commit"] == ["HEAD"]

    @pytest.mark.asyncio
    async def test_always_uses_agentic_review(self, run_reviewer_node):
        """Review node should always use agentic_review, never the old review() method."""
        agentic_mock = AsyncMock(return_value=(_APPROVED_RESULT, "session-123"))
        out = await run_reviewer_node(
            base_commit="abc123",
            agentic_review_override=agentic_mock,
        )

        agentic_mock.assert_called_once()
        out["mock_reviewer"].review.assert_not_called()


class TestCallReviewNodeMultipleReviewTypes:
    """Tests for running separate reviewer passes per review type."""

    @pytest.mark.asyncio
    async def test_loops_per_review_type(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Reviewer should run once per review type, each tagged with reviewer_persona."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        general_result = ReviewResult(
            reviewer_persona="original",
            approved=True,
            comments=[],
            severity="none",
        )
        security_result = ReviewResult(
            reviewer_persona="original",
            approved=False,
            comments=["SQL injection risk"],
            severity="major",
        )

        # Wrap profile to inject review_types
        original_get_config = profile.get_agent_config
        mock_profile = MagicMock(wraps=profile)
        mock_profile.repo_root = profile.repo_root

        def patched_get_config(name: str):
            cfg = original_get_config(name)
            if name in ("reviewer", "task_reviewer"):
                return cfg.model_copy(
                    update={"options": {**cfg.options, "review_types": ["general", "security"]}}
                )
            return cfg

        mock_profile.get_agent_config = patched_get_config
        config = mock_runnable_config(profile=mock_profile)

        review_call_count = 0

        async def mock_agentic_review(state, base_commit, profile, *, workflow_id, diff_path: str | None = None):
            nonlocal review_call_count
            review_call_count += 1
            if review_call_count == 1:
                return general_result, "session-1"
            return security_result, "session-2"

        async def mock_git_cmd(cmd, repo_root, sandbox_provider=None):
            if "--name-only" in cmd:
                return "app.py\n"
            return "import os"

        with (
            patch(
                "amelia.pipelines.nodes._run_git_command",
                side_effect=mock_git_cmd,
            ),
            patch("amelia.pipelines.nodes.detect_stack", return_value={"python"}),
            patch("amelia.pipelines.nodes.load_skills", return_value="# Guidelines") as mock_load,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer_cls.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

            # Reviewer constructed twice (once per review type)
            assert mock_reviewer_cls.call_count == 2
            # load_skills called once per review type
            assert mock_load.call_count == 2
            mock_load.assert_any_call({"python"}, ["general"])
            mock_load.assert_any_call({"python"}, ["security"])

            # Result contains both reviews, tagged with review type
            reviews = result["last_reviews"]
            assert len(reviews) == 2
            assert reviews[0].reviewer_persona == "general"
            assert reviews[0].approved is True
            assert reviews[1].reviewer_persona == "security"
            assert reviews[1].approved is False
            assert reviews[1].comments == ["SQL injection risk"]

    @pytest.mark.asyncio
    async def test_review_passes_run_concurrently(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Multiple review types run concurrently (not serially), each pass gets a
        distinct display agent_name, and results stay ordered/deterministic."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        review_types = ["general", "security", "performance"]
        original_get_config = profile.get_agent_config
        mock_profile = MagicMock(wraps=profile)
        mock_profile.repo_root = profile.repo_root

        def patched_get_config(name: str):
            cfg = original_get_config(name)
            if name in ("reviewer", "task_reviewer"):
                return cfg.model_copy(
                    update={"options": {**cfg.options, "review_types": review_types}}
                )
            return cfg

        mock_profile.get_agent_config = patched_get_config
        config = mock_runnable_config(profile=mock_profile)

        # Barrier proves concurrency: every pass must reach it before any returns.
        # Serial execution deadlocks the first pass -> wait_for times out (FAIL pre-fix).
        barrier = asyncio.Barrier(len(review_types))
        captured_names: list[str] = []

        def make_reviewer(*args: Any, **kwargs: Any) -> MagicMock:
            name = kwargs["agent_name"]
            captured_names.append(name)
            reviewer = MagicMock()
            reviewer.driver = MagicMock()

            async def _agentic_review(
                state, base_commit, profile, *, workflow_id, diff_path=None
            ):
                await barrier.wait()
                review_type = name.split(":", 1)[1]
                return (
                    ReviewResult(
                        reviewer_persona="raw",
                        approved=True,
                        comments=[],
                        severity="none",
                    ),
                    f"sid-{review_type}",
                )

            reviewer.agentic_review = _agentic_review
            return reviewer

        with patch("amelia.pipelines.nodes.Reviewer", side_effect=make_reviewer):
            result = await asyncio.wait_for(call_reviewer_node(state, config), timeout=2.0)

        # Each pass tagged with a distinct display name (canonical base + ':<type>').
        base = captured_names[0].split(":", 1)[0]
        assert base in ("reviewer", "task_reviewer")
        assert captured_names == [f"{base}:{rt}" for rt in review_types]
        # Results preserved in configured order, tagged by review type.
        assert [r.reviewer_persona for r in result["last_reviews"]] == review_types
        # Session id is the last pass's, deterministically (gather preserves order).
        assert result["driver_session_id"] == "sid-performance"

    @pytest.mark.asyncio
    async def test_single_review_type_keeps_canonical_name(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """With one review type there is no concurrency to disambiguate, so the
        canonical agent_name is preserved (no ':<type>' suffix)."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )
        config = mock_runnable_config(profile=profile)

        captured_names: list[str] = []

        def make_reviewer(*args: Any, **kwargs: Any) -> MagicMock:
            captured_names.append(kwargs["agent_name"])
            reviewer = MagicMock()
            reviewer.driver = MagicMock()
            reviewer.agentic_review = AsyncMock(return_value=(_APPROVED_RESULT, "session-1"))
            return reviewer

        with patch("amelia.pipelines.nodes.Reviewer", side_effect=make_reviewer):
            await call_reviewer_node(state, config)

        assert len(captured_names) == 1
        assert ":" not in captured_names[0]
        assert captured_names[0] in ("reviewer", "task_reviewer")

    @pytest.mark.asyncio
    async def test_invalid_review_types_falls_back(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Invalid review_types in agent options should fall back to ['general']."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        mock_review_result = ReviewResult(
            reviewer_persona="original",
            approved=True,
            comments=[],
            severity="none",
        )

        # Inject invalid review_types (empty list)
        original_get_config = profile.get_agent_config
        mock_profile = MagicMock(wraps=profile)
        mock_profile.repo_root = profile.repo_root

        def patched_get_config(name: str):
            cfg = original_get_config(name)
            if name in ("reviewer", "task_reviewer"):
                return cfg.model_copy(
                    update={"options": {**cfg.options, "review_types": []}}
                )
            return cfg

        mock_profile.get_agent_config = patched_get_config
        config = mock_runnable_config(profile=mock_profile)

        with (
            patch(
                "amelia.pipelines.nodes._run_git_command",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch("amelia.pipelines.nodes.detect_stack", return_value=set()),
            patch("amelia.pipelines.nodes.load_skills", return_value="") as mock_load,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = AsyncMock(
                return_value=(mock_review_result, "session-123")
            )
            mock_reviewer_cls.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

            # Should fall back to ["general"]
            mock_load.assert_called_once_with(set(), ["general"])
            assert len(result["last_reviews"]) == 1
            assert result["last_reviews"][0].reviewer_persona == "general"
