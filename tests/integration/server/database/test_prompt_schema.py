# tests/integration/server/database/test_prompt_schema.py
"""Tests for prompt database schema."""
import asyncpg
import pytest

from amelia.server.database.connection import Database


pytestmark = pytest.mark.integration


async def _table_exists(db: Database, table: str) -> bool:
    """Check if a table exists."""
    row = await db.fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
        table,
    )
    return row[0] if row else False


async def test_prompts_table_exists(test_db: Database) -> None:
    """Prompts table should exist after schema creation."""
    assert await _table_exists(test_db, "prompts") is True


async def test_prompt_versions_table_exists(test_db: Database) -> None:
    """Prompt versions table should exist after schema creation."""
    assert await _table_exists(test_db, "prompt_versions") is True


async def test_workflow_prompt_versions_table_exists(test_db: Database) -> None:
    """Workflow prompt versions table should exist after schema creation."""
    assert await _table_exists(test_db, "workflow_prompt_versions") is True


async def test_can_insert_prompt(test_db: Database) -> None:
    """Should be able to insert a prompt."""
    await test_db.execute(
        """INSERT INTO prompts (id, agent, name, description, current_version_id)
           VALUES ($1, $2, $3, $4, $5)""",
        "architect.system", "architect", "Architect System", "Description", None,
    )
    result = await test_db.fetch_one("SELECT * FROM prompts WHERE id = $1", "architect.system")
    assert result is not None
    assert result["agent"] == "architect"


async def test_can_insert_prompt_version(test_db: Database) -> None:
    """Should be able to insert a prompt version with foreign key."""
    await test_db.execute(
        """INSERT INTO prompts (id, agent, name, description)
           VALUES ($1, $2, $3, $4)""",
        "architect.system", "architect", "Architect System", "Description",
    )
    await test_db.execute(
        """INSERT INTO prompt_versions (id, prompt_id, version_number, content, change_note)
           VALUES ($1, $2, $3, $4, $5)""",
        "v-123", "architect.system", 1, "You are an architect...", "Initial",
    )
    result = await test_db.fetch_one("SELECT * FROM prompt_versions WHERE id = $1", "v-123")
    assert result is not None
    assert result["version_number"] == 1


async def test_version_unique_constraint(test_db: Database) -> None:
    """Same prompt+version_number should fail unique constraint."""
    await test_db.execute(
        "INSERT INTO prompts (id, agent, name) VALUES ($1, $2, $3)",
        "test.prompt", "test", "Test",
    )
    await test_db.execute(
        "INSERT INTO prompt_versions (id, prompt_id, version_number, content) VALUES ($1, $2, $3, $4)",
        "v1", "test.prompt", 1, "Content",
    )
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await test_db.execute(
            "INSERT INTO prompt_versions (id, prompt_id, version_number, content) VALUES ($1, $2, $3, $4)",
            "v2", "test.prompt", 1, "Duplicate version number",
        )


async def test_workflow_prompt_version_foreign_keys(test_db: Database) -> None:
    """Workflow prompt versions should enforce foreign keys."""
    await test_db.execute(
        """INSERT INTO workflows (id, issue_id, worktree_path)
           VALUES (gen_random_uuid(), 'ISSUE-1', '/path')""",
    )
    wf = await test_db.fetch_one("SELECT id FROM workflows WHERE issue_id = 'ISSUE-1'")
    wf_id = wf["id"]
    await test_db.execute(
        "INSERT INTO prompts (id, agent, name) VALUES ($1, $2, $3)",
        "test.prompt", "test", "Test",
    )
    await test_db.execute(
        "INSERT INTO prompt_versions (id, prompt_id, version_number, content) VALUES ($1, $2, $3, $4)",
        "v1", "test.prompt", 1, "Content",
    )
    await test_db.execute(
        """INSERT INTO workflow_prompt_versions (workflow_id, prompt_id, version_id)
           VALUES ($1, $2, $3)""",
        wf_id, "test.prompt", "v1",
    )
    result = await test_db.fetch_one(
        "SELECT * FROM workflow_prompt_versions WHERE workflow_id = $1", wf_id
    )
    assert result is not None
