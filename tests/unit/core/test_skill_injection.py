"""Tests for skill injection into the reviewer via call_reviewer_node."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import ReviewResult, Severity
from amelia.pipelines.nodes import call_reviewer_node


@pytest.fixture
def mock_runnable_config(mock_profile_factory):
    """Create a mock RunnableConfig for review node tests."""
    def _create(
        profile=None,
        workflow_id: str = "test-workflow-123",
        event_bus=None,
        repository=None,
    ) -> dict[str, Any]:
        if profile is None:
            profile = mock_profile_factory(preset="cli_single")
        return {
            "configurable": {
                "thread_id": workflow_id,
                "profile": profile,
                "event_bus": event_bus,
                "repository": repository,
            }
        }
    return _create


class TestSkillInjection:
    """Tests for review skill injection in call_reviewer_node."""

    @pytest.mark.asyncio
    async def test_skills_injected_into_reviewer(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Verify detect_stack and load_skills are called and review_guidelines
        is passed to the Reviewer constructor."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        mock_review_result = ReviewResult(
            reviewer_persona="general",
            approved=True,
            comments=[],
            severity=Severity.NONE,
        )

        config = mock_runnable_config(profile=profile)

        with (
            patch(
                "amelia.pipelines.nodes.detect_stack",
                return_value={"python", "fastapi"},
            ) as mock_detect,
            patch(
                "amelia.pipelines.nodes.load_skills",
                return_value="# Python Review Guidelines\n...",
            ) as mock_load,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
            patch(
                "amelia.pipelines.nodes._save_token_usage",
                new_callable=AsyncMock,
            ),
            patch(
                "amelia.pipelines.nodes._run_git_command",
                new_callable=AsyncMock,
                side_effect=lambda cmd, *a, **kw: (
                    "src/app.py\nsrc/routes.py\n" if "--name-only" in cmd
                    else "from fastapi import FastAPI\n"
                ),
            ),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = AsyncMock(
                return_value=(mock_review_result, "session-123")
            )
            mock_reviewer_cls.return_value = mock_reviewer

            await call_reviewer_node(state, config)

            # Verify detect_stack was called with changed files and diff content
            mock_detect.assert_called_once_with(
                ["src/app.py", "src/routes.py"],
                "from fastapi import FastAPI\n",
            )

            # Verify load_skills was called per review type (default: ["general"])
            mock_load.assert_called_once_with({"python", "fastapi"}, ["general"])

            # Verify Reviewer was constructed with review_guidelines
            mock_reviewer_cls.assert_called_once()
            call_kwargs = mock_reviewer_cls.call_args
            assert "review_guidelines" in call_kwargs.kwargs
            assert "Python Review Guidelines" in call_kwargs.kwargs["review_guidelines"]

    @pytest.mark.asyncio
    async def test_custom_review_types_from_agent_options(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Verify review_types from agent_config.options are passed to load_skills."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        mock_review_result = ReviewResult(
            reviewer_persona="general",
            approved=True,
            comments=[],
            severity=Severity.NONE,
        )

        # Wrap profile to inject review_types into reviewer agent options
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

        with (
            patch(
                "amelia.pipelines.nodes.detect_stack",
                return_value={"python"},
            ),
            patch(
                "amelia.pipelines.nodes.load_skills",
                return_value="# Guidelines",
            ) as mock_load,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
            patch(
                "amelia.pipelines.nodes._save_token_usage",
                new_callable=AsyncMock,
            ),
            patch(
                "amelia.pipelines.nodes._run_git_command",
                side_effect=lambda cmd, *a, **kw: (
                    "app.py\n" if "--name-only" in cmd else ""
                ),
            ),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = AsyncMock(
                return_value=(mock_review_result, "session-456")
            )
            mock_reviewer_cls.return_value = mock_reviewer

            await call_reviewer_node(state, config)

            # Verify load_skills was called once per review type
            assert mock_load.call_count == 2
            mock_load.assert_any_call({"python"}, ["general"])
            mock_load.assert_any_call({"python"}, ["security"])

    @pytest.mark.asyncio
    async def test_empty_skills_when_no_matching_tags(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Verify reviewer still works when no skills match the detected stack."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        mock_review_result = ReviewResult(
            reviewer_persona="general",
            approved=True,
            comments=[],
            severity=Severity.NONE,
        )

        config = mock_runnable_config(profile=profile)

        with (
            patch(
                "amelia.pipelines.nodes.detect_stack",
                return_value=set(),
            ),
            patch(
                "amelia.pipelines.nodes.load_skills",
                return_value="",
            ),
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
            patch(
                "amelia.pipelines.nodes._save_token_usage",
                new_callable=AsyncMock,
            ),
            patch(
                "amelia.pipelines.nodes._run_git_command",
                new_callable=AsyncMock,
                return_value="",
            ),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = AsyncMock(
                return_value=(mock_review_result, "session-789")
            )
            mock_reviewer_cls.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

            # Reviewer should be created with empty guidelines
            call_kwargs = mock_reviewer_cls.call_args
            assert call_kwargs.kwargs["review_guidelines"] == ""

            # Review should still complete successfully
            assert result["last_reviews"][0].approved is True
