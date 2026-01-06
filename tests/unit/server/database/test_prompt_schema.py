"""Tests for prompt database schema."""
import aiosqlite
import pytest

from amelia.server.database.connection import Database


@pytest.fixture
async def db(tmp_path):
    """Create a temporary database with schema."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    await database.connect()
    await database.ensure_schema()
    yield database
    await database.close()


async def test_prompts_table_exists(db: Database) -> None:
    """Prompts table should exist after schema creation."""
    result = await db.fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'"
    )
    assert result is not None
    assert result[0] == "prompts"


async def test_prompt_versions_table_exists(db: Database) -> None:
    """Prompt versions table should exist after schema creation."""
    result = await db.fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prompt_versions'"
    )
    assert result is not None
    assert result[0] == "prompt_versions"


async def test_workflow_prompt_versions_table_exists(db: Database) -> None:
    """Workflow prompt versions table should exist after schema creation."""
    result = await db.fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_prompt_versions'"
    )
    assert result is not None


async def test_can_insert_prompt(db: Database) -> None:
    """Should be able to insert a prompt."""
    await db.execute(
        """INSERT INTO prompts (id, agent, name, description, current_version_id)
           VALUES (?, ?, ?, ?, ?)""",
        ("architect.system", "architect", "Architect System", "Description", None),
    )
    result = await db.fetch_one("SELECT * FROM prompts WHERE id = ?", ("architect.system",))
    assert result is not None
    assert result["agent"] == "architect"


async def test_can_insert_prompt_version(db: Database) -> None:
    """Should be able to insert a prompt version with foreign key."""
    # First insert the prompt
    await db.execute(
        """INSERT INTO prompts (id, agent, name, description)
           VALUES (?, ?, ?, ?)""",
        ("architect.system", "architect", "Architect System", "Description"),
    )
    # Then insert the version
    await db.execute(
        """INSERT INTO prompt_versions (id, prompt_id, version_number, content, change_note)
           VALUES (?, ?, ?, ?, ?)""",
        ("v-123", "architect.system", 1, "You are an architect...", "Initial"),
    )
    result = await db.fetch_one("SELECT * FROM prompt_versions WHERE id = ?", ("v-123",))
    assert result is not None
    assert result["version_number"] == 1


async def test_version_unique_constraint(db: Database) -> None:
    """Same prompt+version_number should fail unique constraint."""
    await db.execute(
        "INSERT INTO prompts (id, agent, name) VALUES (?, ?, ?)",
        ("test.prompt", "test", "Test"),
    )
    await db.execute(
        "INSERT INTO prompt_versions (id, prompt_id, version_number, content) VALUES (?, ?, ?, ?)",
        ("v1", "test.prompt", 1, "Content"),
    )
    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute(
            "INSERT INTO prompt_versions (id, prompt_id, version_number, content) VALUES (?, ?, ?, ?)",
            ("v2", "test.prompt", 1, "Duplicate version number"),
        )


async def test_workflow_prompt_version_foreign_keys(db: Database) -> None:
    """Workflow prompt versions should enforce foreign keys."""
    # Create a workflow first
    await db.execute(
        """INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, state_json)
           VALUES (?, ?, ?, ?, ?)""",
        ("wf-123", "ISSUE-1", "/path", "main", "{}"),
    )
    # Create prompt and version
    await db.execute(
        "INSERT INTO prompts (id, agent, name) VALUES (?, ?, ?)",
        ("test.prompt", "test", "Test"),
    )
    await db.execute(
        "INSERT INTO prompt_versions (id, prompt_id, version_number, content) VALUES (?, ?, ?, ?)",
        ("v1", "test.prompt", 1, "Content"),
    )
    # Now link them
    await db.execute(
        """INSERT INTO workflow_prompt_versions (workflow_id, prompt_id, version_id)
           VALUES (?, ?, ?)""",
        ("wf-123", "test.prompt", "v1"),
    )
    result = await db.fetch_one(
        "SELECT * FROM workflow_prompt_versions WHERE workflow_id = ?", ("wf-123",)
    )
    assert result is not None
