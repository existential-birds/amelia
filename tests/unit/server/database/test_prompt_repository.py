# tests/unit/server/database/test_prompt_repository.py
"""Tests for PromptRepository."""
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from amelia.agents.prompts.models import Prompt
from amelia.server.database.connection import Database
from amelia.server.database.prompt_repository import PromptRepository


@pytest.fixture
async def db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Create a temporary database with schema."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    await database.connect()
    await database.ensure_schema()
    yield database
    await database.close()


@pytest.fixture
async def repo(db: Database) -> PromptRepository:
    """Create a PromptRepository."""
    return PromptRepository(db)


class TestPromptCRUD:
    """Tests for prompt CRUD operations."""

    async def test_create_prompt(self, repo: PromptRepository) -> None:
        """Should create a prompt."""
        prompt = Prompt(
            id="test.prompt",
            agent="test",
            name="Test Prompt",
            description="A test prompt",
        )
        await repo.create_prompt(prompt)
        result = await repo.get_prompt("test.prompt")
        assert result is not None
        assert result.name == "Test Prompt"

    async def test_list_prompts(self, repo: PromptRepository) -> None:
        """Should list all prompts."""
        await repo.create_prompt(Prompt(id="p1", agent="a", name="Prompt 1"))
        await repo.create_prompt(Prompt(id="p2", agent="b", name="Prompt 2"))
        prompts = await repo.list_prompts()
        assert len(prompts) == 2

    async def test_get_prompt_not_found(self, repo: PromptRepository) -> None:
        """Should return None for non-existent prompt."""
        result = await repo.get_prompt("nonexistent")
        assert result is None


class TestVersionManagement:
    """Tests for version management."""

    async def test_create_version(self, repo: PromptRepository) -> None:
        """Should create a new version."""
        await repo.create_prompt(Prompt(id="test.prompt", agent="test", name="Test"))
        version = await repo.create_version(
            prompt_id="test.prompt",
            content="New prompt content",
            change_note="Initial version",
        )
        assert version.version_number == 1
        assert version.content == "New prompt content"

    async def test_create_version_increments_number(self, repo: PromptRepository) -> None:
        """Version numbers should auto-increment."""
        await repo.create_prompt(Prompt(id="test.prompt", agent="test", name="Test"))
        v1 = await repo.create_version("test.prompt", "Content 1", "First")
        v2 = await repo.create_version("test.prompt", "Content 2", "Second")
        assert v1.version_number == 1
        assert v2.version_number == 2

    async def test_create_version_sets_active(self, repo: PromptRepository) -> None:
        """Creating a version should set it as active."""
        await repo.create_prompt(Prompt(id="test.prompt", agent="test", name="Test"))
        version = await repo.create_version("test.prompt", "Content", None)
        prompt = await repo.get_prompt("test.prompt")
        assert prompt is not None
        assert prompt.current_version_id == version.id

    async def test_get_versions(self, repo: PromptRepository) -> None:
        """Should list all versions for a prompt."""
        await repo.create_prompt(Prompt(id="test.prompt", agent="test", name="Test"))
        await repo.create_version("test.prompt", "V1", None)
        await repo.create_version("test.prompt", "V2", None)
        versions = await repo.get_versions("test.prompt")
        assert len(versions) == 2
        # Should be ordered by version_number descending (newest first)
        assert versions[0].version_number == 2
        assert versions[1].version_number == 1

    async def test_get_version_by_id(self, repo: PromptRepository) -> None:
        """Should get a specific version by ID."""
        await repo.create_prompt(Prompt(id="test.prompt", agent="test", name="Test"))
        created = await repo.create_version("test.prompt", "Content", None)
        result = await repo.get_version(created.id)
        assert result is not None
        assert result.content == "Content"

    async def test_set_active_version(self, repo: PromptRepository) -> None:
        """Should change the active version."""
        await repo.create_prompt(Prompt(id="test.prompt", agent="test", name="Test"))
        v1 = await repo.create_version("test.prompt", "V1", None)
        await repo.create_version("test.prompt", "V2", None)  # v2 is now active
        # Switch back to v1
        await repo.set_active_version("test.prompt", v1.id)
        prompt = await repo.get_prompt("test.prompt")
        assert prompt is not None
        assert prompt.current_version_id == v1.id

    async def test_reset_to_default(self, repo: PromptRepository) -> None:
        """Should clear current_version_id."""
        await repo.create_prompt(Prompt(id="test.prompt", agent="test", name="Test"))
        await repo.create_version("test.prompt", "Content", None)
        await repo.reset_to_default("test.prompt")
        prompt = await repo.get_prompt("test.prompt")
        assert prompt is not None
        assert prompt.current_version_id is None


class TestWorkflowLinking:
    """Tests for workflow-prompt linking."""

    async def test_record_workflow_prompt(self, repo: PromptRepository, db: Database) -> None:
        """Should record which version a workflow used."""
        # Create workflow
        await db.execute(
            "INSERT INTO workflows (id, issue_id, worktree_path, state_json) VALUES (?, ?, ?, ?)",
            ("wf-1", "ISSUE-1", "/path", "{}"),
        )
        # Create prompt and version
        await repo.create_prompt(Prompt(id="test.prompt", agent="test", name="Test"))
        version = await repo.create_version("test.prompt", "Content", None)
        # Record the link
        await repo.record_workflow_prompt("wf-1", "test.prompt", version.id)
        # Verify
        results = await repo.get_workflow_prompts("wf-1")
        assert len(results) == 1
        assert results[0].version_id == version.id

    async def test_get_workflow_prompts_empty(self, repo: PromptRepository) -> None:
        """Should return empty list for workflow with no prompts."""
        results = await repo.get_workflow_prompts("nonexistent")
        assert results == []
