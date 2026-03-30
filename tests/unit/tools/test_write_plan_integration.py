"""Integration tests for write_plan tool with downstream consumers."""

import json
from pathlib import Path

import pytest

from amelia.pipelines.implementation.utils import (
    _extract_goal_from_plan,
    _extract_key_files_from_plan,
    _looks_like_plan,
    extract_task_count,
    extract_task_section,
    extract_task_title,
    validate_plan_structure,
)
from amelia.tools.write_plan import execute_write_plan


class TestWritePlanDownstreamCompatibility:
    """Verify write_plan output is fully compatible with all downstream consumers."""

    @pytest.fixture
    def plan_input(self) -> dict:
        return {
            "goal": "Add JWT authentication to the API",
            "architecture_summary": "FastAPI middleware with JWT tokens, bcrypt password hashing, and SQLAlchemy user model.",
            "tech_stack": ["Python", "FastAPI", "PyJWT", "bcrypt", "SQLAlchemy"],
            "tasks": [
                {
                    "number": "1",
                    "title": "Create User model and migration",
                    "files_to_create": ["src/models/user.py", "tests/test_user_model.py"],
                    "files_to_modify": ["src/models/__init__.py"],
                    "steps": [
                        "**Step 1: Write the failing test**\n\n```python\ndef test_user_model_has_email():\n    user = User(email='test@example.com', password_hash='abc')\n    assert user.email == 'test@example.com'\n```",
                        "**Step 2: Run test to verify it fails**\n\nRun: `pytest tests/test_user_model.py -v`\nExpected: FAIL",
                        "**Step 3: Implement User model**\n\n```python\nclass User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer, primary_key=True)\n    email = Column(String, unique=True, nullable=False)\n    password_hash = Column(String, nullable=False)\n```",
                        "**Step 4: Run test to verify it passes**\n\nRun: `pytest tests/test_user_model.py -v`\nExpected: PASS",
                    ],
                },
                {
                    "number": "2",
                    "title": "Implement auth middleware",
                    "files_to_create": ["src/middleware/auth.py"],
                    "files_to_modify": ["src/main.py:15-20"],
                    "steps": [
                        "**Step 1: Write the failing test**\n\n```python\ndef test_auth_middleware_rejects_invalid_token():\n    response = client.get('/protected', headers={'Authorization': 'Bearer invalid'})\n    assert response.status_code == 401\n```",
                        "**Step 2: Implement middleware**\n\n```python\nasync def auth_middleware(request, call_next):\n    token = request.headers.get('Authorization', '').replace('Bearer ', '')\n    try:\n        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])\n    except jwt.InvalidTokenError:\n        return JSONResponse(status_code=401, content={'detail': 'Invalid token'})\n    return await call_next(request)\n```",
                    ],
                },
                {
                    "number": "3",
                    "title": "Add login endpoint",
                    "files_to_create": ["src/routes/auth.py"],
                    "files_to_modify": [],
                    "steps": [
                        "**Step 1: Write test and implement**\n\nImplement POST /login endpoint.",
                    ],
                },
            ],
            "file_path": "/docs/plans/test-plan.md",
        }

    @pytest.mark.asyncio
    async def test_extract_task_count(self, plan_input: dict, tmp_path: Path):
        """extract_task_count should find all 3 tasks."""
        plan_input["file_path"] = str(tmp_path / "plan.md")
        await execute_write_plan(plan_input, root_dir=str(tmp_path))
        md = (tmp_path / "plan.md").read_text()
        assert extract_task_count(md) == 3

    @pytest.mark.asyncio
    async def test_extract_task_title(self, plan_input: dict, tmp_path: Path):
        """extract_task_title should find correct titles by index."""
        plan_input["file_path"] = str(tmp_path / "plan.md")
        await execute_write_plan(plan_input, root_dir=str(tmp_path))
        md = (tmp_path / "plan.md").read_text()
        assert extract_task_title(md, 0) == "Create User model and migration"
        assert extract_task_title(md, 1) == "Implement auth middleware"
        assert extract_task_title(md, 2) == "Add login endpoint"

    @pytest.mark.asyncio
    async def test_extract_goal(self, plan_input: dict, tmp_path: Path):
        """_extract_goal_from_plan should find the goal."""
        plan_input["file_path"] = str(tmp_path / "plan.md")
        await execute_write_plan(plan_input, root_dir=str(tmp_path))
        md = (tmp_path / "plan.md").read_text()
        goal = _extract_goal_from_plan(md)
        assert "JWT authentication" in goal

    @pytest.mark.asyncio
    async def test_extract_key_files(self, plan_input: dict, tmp_path: Path):
        """_extract_key_files_from_plan should find all declared files."""
        plan_input["file_path"] = str(tmp_path / "plan.md")
        await execute_write_plan(plan_input, root_dir=str(tmp_path))
        md = (tmp_path / "plan.md").read_text()
        files = _extract_key_files_from_plan(md)
        assert "src/models/user.py" in files
        assert "src/middleware/auth.py" in files
        assert "src/routes/auth.py" in files

    @pytest.mark.asyncio
    async def test_validate_plan_structure(self, plan_input: dict, tmp_path: Path):
        """validate_plan_structure should return valid=True."""
        plan_input["file_path"] = str(tmp_path / "plan.md")
        await execute_write_plan(plan_input, root_dir=str(tmp_path))
        md = (tmp_path / "plan.md").read_text()
        result = validate_plan_structure(plan_input["goal"], md)
        assert result.valid, f"Validation failed: {result.issues}"

    @pytest.mark.asyncio
    async def test_looks_like_plan(self, plan_input: dict, tmp_path: Path):
        """_looks_like_plan should recognize the rendered output."""
        plan_input["file_path"] = str(tmp_path / "plan.md")
        await execute_write_plan(plan_input, root_dir=str(tmp_path))
        md = (tmp_path / "plan.md").read_text()
        assert _looks_like_plan(md) is True

    @pytest.mark.asyncio
    async def test_extract_task_section(self, plan_input: dict, tmp_path: Path):
        """extract_task_section should isolate individual tasks."""
        plan_input["file_path"] = str(tmp_path / "plan.md")
        await execute_write_plan(plan_input, root_dir=str(tmp_path))
        md = (tmp_path / "plan.md").read_text()

        # Extract task 0 (first task)
        section = extract_task_section(md, 0)
        assert "### Task 1:" in section
        assert "Create User model and migration" in section
        # Should NOT contain task 2 content
        assert "### Task 2:" not in section

        # Extract task 1 (second task)
        section = extract_task_section(md, 1)
        assert "### Task 2:" in section
        assert "Implement auth middleware" in section

    @pytest.mark.asyncio
    async def test_json_sidecar_matches_markdown(self, plan_input: dict, tmp_path: Path):
        """JSON sidecar should contain the same data as rendered markdown."""
        plan_input["file_path"] = str(tmp_path / "plan.md")
        await execute_write_plan(plan_input, root_dir=str(tmp_path))

        md = (tmp_path / "plan.md").read_text()
        data = json.loads((tmp_path / "plan.json").read_text())

        # Task count should match
        assert extract_task_count(md) == len(data["tasks"])
        # Goal should match
        assert data["goal"] == plan_input["goal"]
