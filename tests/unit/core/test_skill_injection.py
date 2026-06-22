"""Tests for skill injection into the reviewer via call_reviewer_node."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import ReviewResult, Severity
from amelia.pipelines.nodes import call_reviewer_node


class TestSkillInjection:
    """Tests for review skill injection in call_reviewer_node."""

    @pytest.mark.asyncio
    async def test_skills_injected_into_reviewer(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Verify detect_stack and load_skills_by_type are called and
        review_guidelines is passed to the Reviewer constructor."""
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
                "amelia.pipelines.nodes.load_skills_by_type",
                return_value={"general": "# Python Review Guidelines\n..."},
            ) as mock_load,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
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

            # Verify load_skills_by_type was called once with the default
            # review type list (skills resolved once per node invocation).
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
        """Verify review_types from agent_config.options are passed to load_skills_by_type."""
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
                "amelia.pipelines.nodes.load_skills_by_type",
                return_value={"general": "# Guidelines", "security": "# Security Guidelines"},
            ) as mock_load,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
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

            # Skills are resolved once per node invocation: a single
            # load_skills_by_type call covering all configured review types,
            # not one call per type.
            mock_load.assert_called_once_with({"python"}, ["general", "security"])

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
                "amelia.pipelines.nodes.load_skills_by_type",
                return_value={"general": ""},
            ),
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
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
