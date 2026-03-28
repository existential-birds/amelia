"""Tests for write_plan tool implementation."""

import json
from pathlib import Path
from typing import Any

import pytest

from amelia.tools.write_plan import (
    create_write_plan_tool,
    execute_write_plan,
)


class TestExecuteWritePlan:
    """Tests for execute_write_plan core logic."""

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        return {
            "goal": "Build user auth",
            "architecture_summary": "JWT middleware approach",
            "tech_stack": ["Python", "FastAPI"],
            "tasks": [
                {
                    "number": "1",
                    "title": "Create auth module",
                    "files_to_create": ["src/auth.py"],
                    "files_to_modify": [],
                    "steps": ["**Step 1:** Write tests", "**Step 2:** Implement"],
                }
            ],
            "file_path": "/docs/plans/test.md",
        }

    @pytest.mark.asyncio
    async def test_returns_success_message(self, valid_input: dict, tmp_path: Path):
        """Should return success message with task count and file path."""
        valid_input["file_path"] = str(tmp_path / "plan.md")
        result = await execute_write_plan(valid_input, root_dir=str(tmp_path))
        assert "Successfully wrote plan" in result
        assert "1 task(s)" in result

    @pytest.mark.asyncio
    async def test_writes_file_to_disk(self, valid_input: dict, tmp_path: Path):
        """Should write the rendered markdown to the specified file."""
        plan_file = tmp_path / "plan.md"
        valid_input["file_path"] = str(plan_file)
        await execute_write_plan(valid_input, root_dir=str(tmp_path))
        assert plan_file.exists()
        content = plan_file.read_text()
        assert "### Task 1: Create auth module" in content
        assert "**Goal:** Build user auth" in content

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, valid_input: dict, tmp_path: Path):
        """Should create parent directories if they don't exist."""
        plan_file = tmp_path / "deep" / "nested" / "plan.md"
        valid_input["file_path"] = str(plan_file)
        await execute_write_plan(valid_input, root_dir=str(tmp_path))
        assert plan_file.exists()

    @pytest.mark.asyncio
    async def test_validation_error_returns_message(self, tmp_path: Path):
        """Invalid input should return descriptive error, not raise."""
        bad_input: dict[str, Any] = {
            "goal": "",
            "architecture_summary": "arch",
            "tasks": [],
            "file_path": "/plan.md",
        }
        result = await execute_write_plan(bad_input, root_dir=str(tmp_path))
        assert "Validation error" in result

    @pytest.mark.asyncio
    async def test_stores_structured_data(self, valid_input: dict, tmp_path: Path):
        """Should write a .json sidecar with structured plan data."""
        plan_file = tmp_path / "plan.md"
        valid_input["file_path"] = str(plan_file)
        await execute_write_plan(valid_input, root_dir=str(tmp_path))
        json_file = tmp_path / "plan.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert data["goal"] == "Build user auth"
        assert len(data["tasks"]) == 1

    @pytest.mark.asyncio
    async def test_virtual_path_resolved_relative(self, valid_input: dict, tmp_path: Path):
        """Virtual paths starting with / should resolve relative to root_dir."""
        valid_input["file_path"] = "/docs/plans/test.md"
        await execute_write_plan(valid_input, root_dir=str(tmp_path))
        assert (tmp_path / "docs" / "plans" / "test.md").exists()
        assert (tmp_path / "docs" / "plans" / "test.json").exists()


class TestCreateWritePlanTool:
    """Tests for LangChain tool factory."""

    def test_creates_tool_with_correct_name(self):
        """Tool name should be 'write_plan'."""
        tool = create_write_plan_tool(root_dir="/tmp")
        assert tool.name == "write_plan"

    def test_tool_has_description(self):
        """Tool should have a non-empty description."""
        tool = create_write_plan_tool(root_dir="/tmp")
        assert len(tool.description) > 20

    def test_tool_has_schema(self):
        """Tool should have an args_schema matching WritePlanInput fields."""
        tool = create_write_plan_tool(root_dir="/tmp")
        schema = tool.args_schema.model_json_schema() if tool.args_schema else {}
        assert "goal" in schema.get("properties", {})
        assert "tasks" in schema.get("properties", {})
