"""Unit tests for external plan import helper."""

from pathlib import Path
from unittest.mock import patch

import pytest

from amelia.agents.architect import MarkdownPlanOutput
from amelia.core.types import AgentConfig, Profile


class TestImportExternalPlan:
    """Tests for import_external_plan helper function."""

    @pytest.fixture
    def mock_profile(self, tmp_path: Path) -> Profile:
        """Create mock profile for testing."""
        return Profile(
            name="test",
            tracker="noop",
            working_dir=str(tmp_path / "worktree"),
            agents={
                "plan_validator": AgentConfig(driver="cli", model="sonnet"),
            },
        )

    async def test_import_from_file_path(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import plan from file path reads and validates content."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        # Create worktree directory
        worktree = Path(mock_profile.working_dir)
        worktree.mkdir(parents=True, exist_ok=True)

        plan_file = worktree / "plan.md"
        plan_content = """# Implementation Plan

**Goal:** Add user authentication

### Task 1: Create auth module

Create the auth module.
"""
        plan_file.write_text(plan_content)

        # Target path must be within working directory (security constraint)
        target_path = worktree / "output" / "plan.md"

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = MarkdownPlanOutput(
                goal="Add user authentication",
                plan_markdown=plan_content,
                key_files=["auth.py"],
            )

            result = await import_external_plan(
                plan_file=str(plan_file),
                plan_content=None,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

        assert result.goal == "Add user authentication"
        assert result.plan_markdown == plan_content
        assert result.key_files == ["auth.py"]
        assert result.total_tasks == 1
        assert target_path.read_text() == plan_content

    async def test_import_from_inline_content(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import plan from inline content writes and validates."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        # Create worktree directory
        worktree = Path(mock_profile.working_dir)
        worktree.mkdir(parents=True, exist_ok=True)

        plan_content = """# Implementation Plan

**Goal:** Fix bug

### Task 1: Fix the bug

Fix it.
"""
        # Target path must be within working directory (security constraint)
        target_path = worktree / "output" / "plan.md"

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = MarkdownPlanOutput(
                goal="Fix bug",
                plan_markdown=plan_content,
                key_files=[],
            )

            result = await import_external_plan(
                plan_file=None,
                plan_content=plan_content,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

        assert result.goal == "Fix bug"
        assert target_path.read_text() == plan_content

    async def test_import_file_not_found_raises(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import with non-existent file raises FileNotFoundError."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        # Create worktree directory
        worktree = Path(mock_profile.working_dir)
        worktree.mkdir(parents=True, exist_ok=True)

        # Target path must be within working directory (security constraint)
        target_path = worktree / "output" / "plan.md"

        # Non-existent file within worktree
        with pytest.raises(FileNotFoundError, match="Plan file not found"):
            await import_external_plan(
                plan_file="nonexistent/plan.md",  # Relative to worktree
                plan_content=None,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

    async def test_import_empty_content_raises(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import with empty content raises ValueError."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        # Create worktree directory
        worktree = Path(mock_profile.working_dir)
        worktree.mkdir(parents=True, exist_ok=True)

        # Target path must be within working directory (security constraint)
        target_path = worktree / "output" / "plan.md"

        with pytest.raises(ValueError, match="Plan content is empty"):
            await import_external_plan(
                plan_file=None,
                plan_content="   ",
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

    async def test_import_relative_path_resolved_to_worktree(
        self, tmp_path: Path
    ) -> None:
        """Relative plan_file paths are resolved relative to worktree."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        plan_file = worktree / "docs" / "plan.md"
        plan_file.parent.mkdir(parents=True)
        plan_content = "# Plan\n\n### Task 1: Do thing\n\nDo it."
        plan_file.write_text(plan_content)

        profile = Profile(
            name="test",
            tracker="noop",
            working_dir=str(worktree),
            agents={
                "plan_validator": AgentConfig(driver="cli", model="sonnet"),
            },
        )

        # Target path must be within working directory (security constraint)
        target_path = worktree / "output" / "plan.md"

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = MarkdownPlanOutput(
                goal="Do thing",
                plan_markdown=plan_content,
                key_files=[],
            )

            result = await import_external_plan(
                plan_file="docs/plan.md",
                plan_content=None,
                target_path=target_path,
                profile=profile,
                workflow_id="wf-001",
            )

        assert result.goal == "Do thing"

    async def test_import_fallback_when_extraction_fails(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import uses fallback extraction when LLM extraction fails."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        # Create worktree directory
        worktree = Path(mock_profile.working_dir)
        worktree.mkdir(parents=True, exist_ok=True)

        plan_content = """# Implementation Plan

**Goal:** Build feature

### Task 1: Create module

Create: `src/feature.py`

Content here.
"""
        # Target path must be within working directory (security constraint)
        target_path = worktree / "output" / "plan.md"

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            # Simulate extraction failure
            mock_extract.side_effect = RuntimeError("Extraction failed")

            result = await import_external_plan(
                plan_file=None,
                plan_content=plan_content,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

        # Fallback should extract goal from **Goal:** pattern
        assert result.goal == "Build feature"
        assert result.plan_markdown == plan_content
        # Fallback should extract key files from Create: pattern
        assert "src/feature.py" in result.key_files
        assert result.total_tasks == 1

    async def test_import_plan_file_path_traversal_blocked(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import rejects plan_file that resolves outside working directory."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        # Create worktree directory
        worktree = Path(mock_profile.working_dir)
        worktree.mkdir(parents=True, exist_ok=True)

        # Target path within working directory
        target_path = worktree / "output" / "plan.md"

        # Attempt path traversal with ..
        with pytest.raises(ValueError, match="resolves outside working directory"):
            await import_external_plan(
                plan_file="../../../etc/passwd",
                plan_content=None,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

    async def test_import_target_path_traversal_blocked(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import rejects target_path that resolves outside working directory."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        # Create worktree directory
        worktree = Path(mock_profile.working_dir)
        worktree.mkdir(parents=True, exist_ok=True)

        # Attempt path traversal with target_path outside worktree
        target_path = tmp_path / "outside" / "plan.md"

        with pytest.raises(ValueError, match="resolves outside working directory"):
            await import_external_plan(
                plan_file=None,
                plan_content="# Plan\n\n### Task 1: Do thing",
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

    async def test_import_absolute_plan_file_outside_worktree_blocked(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import rejects absolute plan_file path outside working directory."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        # Create worktree directory
        worktree = Path(mock_profile.working_dir)
        worktree.mkdir(parents=True, exist_ok=True)

        # Create plan file outside worktree
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_plan = outside_dir / "plan.md"
        outside_plan.write_text("# Plan\n\n### Task 1: Do thing")

        # Target path within working directory
        target_path = worktree / "output" / "plan.md"

        # Attempt to read file outside worktree
        with pytest.raises(ValueError, match="resolves outside working directory"):
            await import_external_plan(
                plan_file=str(outside_plan),
                plan_content=None,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )
