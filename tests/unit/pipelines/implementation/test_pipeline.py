"""Unit tests for ImplementationPipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from amelia.core.agentic_state import ToolCall
from amelia.core.constants import ToolName
from amelia.pipelines.base import PipelineMetadata
from amelia.pipelines.implementation.pipeline import ImplementationPipeline
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)


# Rebuild to resolve forward references for Pydantic
rebuild_implementation_state()


class TestImplementationPipelineProtocol:
    """Tests that ImplementationPipeline satisfies Pipeline protocol."""

    def test_has_metadata_property(self) -> None:
        """Should have metadata property returning PipelineMetadata."""
        pipeline = ImplementationPipeline()
        meta = pipeline.metadata
        assert isinstance(meta, PipelineMetadata)

    def test_metadata_name_is_implementation(self) -> None:
        """Metadata name should be 'implementation'."""
        pipeline = ImplementationPipeline()
        assert pipeline.metadata.name == "implementation"

    def test_metadata_display_name(self) -> None:
        """Metadata display_name should be 'Implementation'."""
        pipeline = ImplementationPipeline()
        assert pipeline.metadata.display_name == "Implementation"

    def test_metadata_has_description(self) -> None:
        """Metadata should have a description."""
        pipeline = ImplementationPipeline()
        assert pipeline.metadata.description
        assert len(pipeline.metadata.description) > 10

    def test_has_create_graph_method(self) -> None:
        """Should have create_graph method."""
        pipeline = ImplementationPipeline()
        assert hasattr(pipeline, "create_graph")
        assert callable(pipeline.create_graph)

    def test_get_state_class_returns_implementation_state(self) -> None:
        """Should return ImplementationState class."""
        pipeline = ImplementationPipeline()
        assert pipeline.get_state_class() is ImplementationState

    def test_creates_valid_initial_state(self) -> None:
        """Should create a valid ImplementationState."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id=uuid4(),
            profile_id="default",
        )
        assert isinstance(state, ImplementationState)
        assert state.workflow_id is not None  # UUID propagated
        assert state.profile_id == "default"
        assert state.status == "pending"
        assert state.pipeline_type == "implementation"

    def test_creates_compiled_graph(self) -> None:
        """Should return a compiled LangGraph."""
        pipeline = ImplementationPipeline()
        graph = pipeline.create_graph()
        # Compiled graph should have nodes attribute
        assert hasattr(graph, "nodes")


class TestImplementationPipelineGraph:
    """Tests for the compiled graph structure."""

    def test_graph_has_required_nodes(self) -> None:
        """Graph should contain all required nodes."""
        pipeline = ImplementationPipeline()
        graph = pipeline.create_graph()

        # Check that expected node names exist
        node_names = set(graph.nodes.keys())
        expected_nodes = {
            "architect_node",
            "plan_validator_node",
            "human_approval_node",
            "developer_node",
            "reviewer_node",
            "next_task_node",
        }
        assert expected_nodes.issubset(node_names), (
            f"Missing nodes: {expected_nodes - node_names}"
        )

    def test_graph_accepts_checkpointer(self) -> None:
        """Should accept an optional checkpointer argument."""
        pipeline = ImplementationPipeline()
        # Should not raise when called with None
        graph = pipeline.create_graph(checkpointer=None)
        assert graph is not None


class TestImplementationPipelineInitialState:
    """Tests for initial state creation."""

    def test_initial_state_has_workflow_id(self) -> None:
        """Initial state should have workflow_id set."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id=uuid4(),
            profile_id="default",
        )
        assert state.workflow_id is not None  # UUID propagated

    def test_initial_state_has_profile_id(self) -> None:
        """Initial state should have profile_id set."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id=uuid4(),
            profile_id="my-profile",
        )
        assert state.profile_id == "my-profile"

    def test_initial_state_has_created_at(self) -> None:
        """Initial state should have created_at timestamp."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id=uuid4(),
            profile_id="default",
        )
        assert state.created_at is not None

    def test_initial_state_is_pending(self) -> None:
        """Initial state should have status='pending'."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id=uuid4(),
            profile_id="default",
        )
        assert state.status == "pending"

    def test_initial_state_has_empty_history(self) -> None:
        """Initial state should have empty history."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id=uuid4(),
            profile_id="default",
        )
        assert state.history == []


class TestPlanValidatorStructuredData:
    """Tests for structured plan data (JSON sidecar) in plan_validator_node."""

    @pytest.mark.asyncio
    async def test_plan_validator_reads_json_sidecar(
        self,
        tmp_path: Path,
        mock_profile_factory,
        mock_issue_factory,
    ) -> None:
        """If .json sidecar exists, plan_validator should populate plan_structured."""
        import json
        from datetime import UTC, datetime

        from amelia.pipelines.implementation.nodes import plan_validator_node

        # Create plan directory and files
        plan_dir = tmp_path / "docs" / "plans"
        plan_dir.mkdir(parents=True)

        issue = mock_issue_factory(id="TEST-123")
        profile = mock_profile_factory(repo_root=str(tmp_path))

        # Resolve the actual plan filename
        from amelia.core.constants import resolve_plan_path

        plan_rel = resolve_plan_path(profile.plan_path_pattern, issue.id)
        plan_md = tmp_path / plan_rel
        plan_json = plan_md.with_suffix(".json")
        plan_md.parent.mkdir(parents=True, exist_ok=True)

        plan_md.write_text(
            "# Test Plan\n\n**Goal:** Test goal\n\n---\n\n"
            "### Task 1: Do thing\n\n"
            "Step content here that is long enough to pass validation checks and more text.\n"
            "Additional padding to satisfy minimum content length requirements for validation.\n"
            "Even more content to make this look like a real plan with substance.\n"
        )
        plan_json.write_text(json.dumps({
            "goal": "Structured test goal",
            "architecture_summary": "Test arch",
            "tech_stack": ["Python"],
            "tasks": [
                {
                    "number": "1",
                    "title": "Do thing",
                    "steps": ["Step"],
                    "files_to_modify": ["src/app.py"],
                    "files_to_create": ["src/new.py"],
                }
            ],
            "file_path": "/docs/plans/test.md",
        }))

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="pending",
            profile_id=profile.name,
            issue=issue,
        )

        config = {
            "configurable": {
                "thread_id": state.workflow_id,
                "profile": profile,
            }
        }

        result = await plan_validator_node(state, config)

        assert result["plan_structured"] is not None
        assert result["plan_structured"].goal == "Structured test goal"
        assert len(result["plan_structured"].tasks) == 1
        # Structured goal should override regex-extracted goal
        assert result["goal"] == "Structured test goal"
        # Key files should come from structured data
        assert "src/app.py" in result["key_files"]
        assert "src/new.py" in result["key_files"]
        assert result["total_tasks"] == 1

    @pytest.mark.asyncio
    async def test_plan_validator_without_json_sidecar(
        self,
        tmp_path: Path,
        mock_profile_factory,
        mock_issue_factory,
    ) -> None:
        """Without .json sidecar, plan_structured should be None and regex is used."""
        from datetime import UTC, datetime

        from amelia.core.constants import resolve_plan_path
        from amelia.pipelines.implementation.nodes import plan_validator_node

        issue = mock_issue_factory(id="TEST-456")
        profile = mock_profile_factory(repo_root=str(tmp_path))

        plan_rel = resolve_plan_path(profile.plan_path_pattern, issue.id)
        plan_md = tmp_path / plan_rel
        plan_md.parent.mkdir(parents=True, exist_ok=True)
        plan_md.write_text(
            "# Test Plan\n\n**Goal:** Regex extracted goal\n\n---\n\n"
            "### Task 1: First thing\n\n"
            "Step content here that is long enough to pass validation checks.\n"
            "### Task 2: Second thing\n\n"
            "More step content here for the second task.\n"
        )

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="pending",
            profile_id=profile.name,
            issue=issue,
        )

        config = {
            "configurable": {
                "thread_id": state.workflow_id,
                "profile": profile,
            }
        }

        result = await plan_validator_node(state, config)

        assert result["plan_structured"] is None
        assert result["goal"] is not None  # Should still extract via regex

    @pytest.mark.asyncio
    async def test_plan_validator_handles_malformed_json_sidecar(
        self,
        tmp_path: Path,
        mock_profile_factory,
        mock_issue_factory,
    ) -> None:
        """Malformed JSON sidecar should be ignored gracefully."""
        from datetime import UTC, datetime

        from amelia.core.constants import resolve_plan_path
        from amelia.pipelines.implementation.nodes import plan_validator_node

        issue = mock_issue_factory(id="TEST-789")
        profile = mock_profile_factory(repo_root=str(tmp_path))

        plan_rel = resolve_plan_path(profile.plan_path_pattern, issue.id)
        plan_md = tmp_path / plan_rel
        plan_json = plan_md.with_suffix(".json")
        plan_md.parent.mkdir(parents=True, exist_ok=True)

        plan_md.write_text(
            "# Test Plan\n\n**Goal:** Fallback goal\n\n---\n\n"
            "### Task 1: Do thing\n\n"
            "Step content here that is long enough to pass validation checks.\n"
        )
        plan_json.write_text("{not valid json!!!")

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="pending",
            profile_id=profile.name,
            issue=issue,
        )

        config = {
            "configurable": {
                "thread_id": state.workflow_id,
                "profile": profile,
            }
        }

        result = await plan_validator_node(state, config)

        # Should fall back to regex extraction
        assert result["plan_structured"] is None
        assert result["goal"] is not None

    @pytest.mark.asyncio
    async def test_plan_validator_empty_dict_sidecar_falls_back_to_regex(
        self,
        tmp_path: Path,
        mock_profile_factory,
        mock_issue_factory,
    ) -> None:
        """Empty {} sidecar should be ignored — regex extraction used instead."""
        import json
        from datetime import UTC, datetime

        from amelia.core.constants import resolve_plan_path
        from amelia.pipelines.implementation.nodes import plan_validator_node

        issue = mock_issue_factory(id="TEST-EMPTY")
        profile = mock_profile_factory(repo_root=str(tmp_path))

        plan_rel = resolve_plan_path(profile.plan_path_pattern, issue.id)
        plan_md = tmp_path / plan_rel
        plan_json = plan_md.with_suffix(".json")
        plan_md.parent.mkdir(parents=True, exist_ok=True)

        plan_md.write_text(
            "# Test Plan\n\n**Goal:** Regex fallback goal\n\n---\n\n"
            "### Task 1: First thing\n\n"
            "Step content here that is long enough to pass validation checks.\n"
        )
        plan_json.write_text(json.dumps({}))  # empty dict — truthy but useless

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="pending",
            profile_id=profile.name,
            issue=issue,
        )

        config = {
            "configurable": {
                "thread_id": state.workflow_id,
                "profile": profile,
            }
        }

        result = await plan_validator_node(state, config)

        # Empty dict sidecar is normalised to None → regex path used
        assert result["plan_structured"] is None
        assert result["goal"] is not None  # From regex
        assert result["total_tasks"] >= 1  # From regex extraction

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="chmod does not restrict owner reads on Windows",
    )
    @pytest.mark.skipif(
        __import__("os").getuid() == 0 if hasattr(__import__("os"), "getuid") else False,
        reason="root can read files regardless of permissions",
    )
    async def test_plan_validator_handles_unreadable_json_sidecar(
        self,
        tmp_path: Path,
        mock_profile_factory,
        mock_issue_factory,
    ) -> None:
        """OSError reading sidecar (e.g. permissions) should be caught gracefully."""
        import os
        from datetime import UTC, datetime

        from amelia.core.constants import resolve_plan_path
        from amelia.pipelines.implementation.nodes import plan_validator_node

        issue = mock_issue_factory(id="TEST-OSERR")
        profile = mock_profile_factory(repo_root=str(tmp_path))

        plan_rel = resolve_plan_path(profile.plan_path_pattern, issue.id)
        plan_md = tmp_path / plan_rel
        plan_json = plan_md.with_suffix(".json")
        plan_md.parent.mkdir(parents=True, exist_ok=True)

        plan_md.write_text(
            "# Test Plan\n\n**Goal:** OS error goal\n\n---\n\n"
            "### Task 1: Do thing\n\n"
            "Step content here that is long enough to pass validation checks.\n"
        )
        plan_json.write_text('{"goal": "still unreadable"}')

        # Make file unreadable
        os.chmod(plan_json, 0o000)
        try:
            state = ImplementationState(
                workflow_id=uuid4(),
                created_at=datetime.now(UTC),
                status="pending",
                profile_id=profile.name,
                issue=issue,
            )

            config = {
                "configurable": {
                    "thread_id": state.workflow_id,
                    "profile": profile,
                }
            }

            result = await plan_validator_node(state, config)

            # OSError should be caught; falls back to regex
            assert result["plan_structured"] is None
            assert result["goal"] is not None
        finally:
            os.chmod(plan_json, 0o644)  # restore for cleanup


    @pytest.mark.asyncio
    async def test_plan_validator_handles_non_dict_json_sidecar(
        self,
        tmp_path: Path,
        mock_profile_factory,
        mock_issue_factory,
    ) -> None:
        """Non-dict JSON sidecar (e.g. a list) should be ignored gracefully."""
        import json
        from datetime import UTC, datetime

        from amelia.core.constants import resolve_plan_path
        from amelia.pipelines.implementation.nodes import plan_validator_node

        issue = mock_issue_factory(id="TEST-NONDICT")
        profile = mock_profile_factory(repo_root=str(tmp_path))

        plan_rel = resolve_plan_path(profile.plan_path_pattern, issue.id)
        plan_md = tmp_path / plan_rel
        plan_json = plan_md.with_suffix(".json")
        plan_md.parent.mkdir(parents=True, exist_ok=True)

        plan_md.write_text(
            "# Test Plan\n\n**Goal:** Non-dict goal\n\n---\n\n"
            "### Task 1: Do thing\n\n"
            "Step content here that is long enough to pass validation checks.\n"
        )
        # Write a JSON array instead of an object
        plan_json.write_text(json.dumps(["not", "a", "dict"]))

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="pending",
            profile_id=profile.name,
            issue=issue,
        )

        config = {
            "configurable": {
                "thread_id": state.workflow_id,
                "profile": profile,
            }
        }

        result = await plan_validator_node(state, config)

        # Non-dict sidecar should be ignored; falls back to regex
        assert result["plan_structured"] is None
        assert result["goal"] is not None


class TestArchitectNodeWritePlan:
    """Tests for write_plan tool call handling in architect node fallback."""

    def test_write_plan_tool_call_recognized(self) -> None:
        """ToolCall with WRITE_PLAN should be recognized by tool_name."""
        tool_call = ToolCall(
            id="call-1",
            tool_name=ToolName.WRITE_PLAN,
            tool_input={
                "goal": "Build auth",
                "architecture_summary": "JWT approach",
                "tasks": [{"number": "1", "title": "Setup", "steps": ["Do it"]}],
                "file_path": "/docs/plans/test.md",
            },
        )
        assert tool_call.tool_name == "write_plan"
        assert tool_call.tool_name == ToolName.WRITE_PLAN

    @pytest.mark.asyncio
    async def test_execute_write_plan_from_tool_input(self, tmp_path: Path) -> None:
        """execute_write_plan should write plan file from structured input."""
        from amelia.tools.write_plan import execute_write_plan

        tool_input = {
            "goal": "Build auth system",
            "architecture_summary": "JWT-based authentication",
            "tasks": [
                {
                    "number": "1",
                    "title": "Setup JWT",
                    "steps": ["Install deps", "Create middleware"],
                }
            ],
            "file_path": "/docs/plans/auth.md",
        }
        result = await execute_write_plan(tool_input, root_dir=str(tmp_path))
        assert result.startswith("Successfully")
        assert (tmp_path / "docs" / "plans" / "auth.md").exists()

    @pytest.mark.asyncio
    async def test_resolve_plan_overrides_llm_file_path(self, tmp_path: Path) -> None:
        """_resolve_plan_from_tool_calls should write to authoritative plan_path, not LLM path."""
        from amelia.pipelines.implementation.nodes import _resolve_plan_from_tool_calls

        tool_call = ToolCall(
            id="call-1",
            tool_name=ToolName.WRITE_PLAN,
            tool_input={
                "goal": "Build auth",
                "architecture_summary": "JWT approach",
                "tasks": [{"number": "1", "title": "Setup", "steps": ["Do it"]}],
                "file_path": "/wrong/llm/provided/path.md",  # LLM's path — should be ignored
            },
        )
        authoritative_path = tmp_path / "correct" / "plan.md"

        plan_written = await _resolve_plan_from_tool_calls(
            tool_calls=[tool_call],
            plan_path=authoritative_path,
            working_dir=tmp_path,
        )

        assert plan_written, "write_plan should succeed"
        assert authoritative_path.exists(), "Plan should be at authoritative path"
        assert not (tmp_path / "wrong" / "llm" / "provided" / "path.md").exists(), (
            "LLM-provided path should NOT be used"
        )

    @pytest.mark.asyncio
    async def test_write_plan_fallback_continues_on_failure(self, tmp_path: Path) -> None:
        """If write_plan fails, _resolve_plan_from_tool_calls should fall through to write_file."""
        from amelia.pipelines.implementation.nodes import _resolve_plan_from_tool_calls

        bad_input: dict[str, Any] = {
            "goal": "",  # empty goal triggers validation error
            "tasks": [],
            "file_path": "/docs/plans/test.md",
        }
        write_plan_call = ToolCall(
            id="call-1",
            tool_name=ToolName.WRITE_PLAN,
            tool_input=bad_input,
        )
        write_file_call = ToolCall(
            id="call-2",
            tool_name=ToolName.WRITE_FILE,
            tool_input={
                "file_path": "/docs/plans/test.md",
                "content": "# Plan\n## Task 1\nDo stuff",
            },
        )
        plan_path = tmp_path / "docs" / "plans" / "test.md"

        plan_written = await _resolve_plan_from_tool_calls(
            tool_calls=[write_plan_call, write_file_call],
            plan_path=plan_path,
            working_dir=tmp_path,
        )

        assert plan_written, "write_file fallback should succeed after write_plan failure"
        assert plan_path.exists()
        assert "Task 1" in plan_path.read_text()

    @pytest.mark.asyncio
    async def test_raw_output_fallback_creates_parent_directory(self, tmp_path: Path) -> None:
        """Raw-output fallback should create parent dirs before writing."""
        from amelia.pipelines.implementation.nodes import _resolve_plan_from_tool_calls

        # Plan path in a non-existent subdirectory
        plan_path = tmp_path / "deep" / "nested" / "dir" / "plan.md"
        assert not plan_path.parent.exists()

        raw_output = (
            "# Implementation Plan\n\n"
            "**Goal:** Build a feature\n\n"
            "**Architecture:** Simple design\n\n"
            "## Phase 1\n\n"
            "### Task 1: Do the thing\n\n"
            "```python\nprint('hello')\n```\n\n"
            "Some steps here with enough content to pass the length check.\n"
            "Additional detail to ensure we exceed the minimum character threshold.\n"
        )

        plan_written = await _resolve_plan_from_tool_calls(
            tool_calls=[],  # No tool calls — forces raw-output fallback
            plan_path=plan_path,
            working_dir=tmp_path,
            raw_output=raw_output,
        )

        assert plan_written, "Raw-output fallback should succeed"
        assert plan_path.exists()
        assert "Task 1" in plan_path.read_text()
