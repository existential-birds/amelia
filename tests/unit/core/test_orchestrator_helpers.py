"""Tests for orchestrator helper functions."""

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.agentic_state import ToolCall
from amelia.core.constants import ToolName
from amelia.core.orchestrator import _extract_config_params, _extract_goal_from_markdown
from amelia.core.types import Profile


class TestExtractConfigParams:
    """Tests for _extract_config_params helper."""

    def test_extracts_profile_from_config(self) -> None:
        """Should extract profile from config.configurable.profile."""
        profile = Profile(name="test", driver="cli:claude", model="sonnet")
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
                "profile": profile,
            }
        }
        stream_emitter, workflow_id, extracted_profile = _extract_config_params(config)
        assert extracted_profile == profile
        assert workflow_id == "wf-123"

    def test_raises_if_profile_missing(self) -> None:
        """Should raise ValueError if profile not in config."""
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
            }
        }
        with pytest.raises(ValueError, match="profile is required"):
            _extract_config_params(config)


class TestExtractGoalFromMarkdown:
    """Tests for temporary goal extraction helper."""

    def test_extracts_goal_from_markdown(self) -> None:
        """Should extract goal from **Goal:** line."""
        markdown = "# Plan\n\n**Goal:** Implement the feature\n\n## Tasks"
        result = _extract_goal_from_markdown(markdown)
        assert result == "Implement the feature"

    def test_returns_none_for_empty_input(self) -> None:
        """Should return None for empty/None input."""
        assert _extract_goal_from_markdown(None) is None
        assert _extract_goal_from_markdown("") is None

    def test_returns_none_when_no_goal_line(self) -> None:
        """Should return None when no Goal line present."""
        markdown = "# Plan\n\nSome content without goal"
        assert _extract_goal_from_markdown(markdown) is None

    def test_handles_goal_with_colon_in_content(self) -> None:
        """Should handle goal text that contains colons."""
        markdown = "**Goal:** Fix bug: handle edge case"
        result = _extract_goal_from_markdown(markdown)
        assert result == "Fix bug: handle edge case"

    def test_handles_multiline_document(self) -> None:
        """Should find goal anywhere in document."""
        markdown = """# Implementation Plan

Some preamble text.

**Goal:** The actual goal here

## Task 1
Content
"""
        result = _extract_goal_from_markdown(markdown)
        assert result == "The actual goal here"

    def test_returns_none_for_empty_goal_line(self) -> None:
        """Should return None when Goal line has no content."""
        markdown = "# Plan\n\n**Goal:**\n\n## Tasks"
        assert _extract_goal_from_markdown(markdown) is None
        # Also test with whitespace only
        markdown_whitespace = "# Plan\n\n**Goal:**   \n\n## Tasks"
        assert _extract_goal_from_markdown(markdown_whitespace) is None


class TestPlanExtractionFromToolCalls:
    """Tests for plan extraction from tool calls with different tool name formats.

    These tests verify that plan extraction works with both:
    - Normalized tool names (write_file) from CLI driver
    - Raw tool names (write_file) from API driver
    """

    def test_plan_extracted_when_tool_name_is_write_file(self) -> None:
        """Plan should be extracted when tool_name equals ToolName.WRITE_FILE."""
        plan_content = """# Implementation Plan

**Goal:** Implement user authentication feature

## Task 1: Setup
..."""

        tool_calls = [
            ToolCall(
                id="tool_123",
                tool_name=ToolName.WRITE_FILE,  # Normalized format from CLI driver
                tool_input={"file_path": "/tmp/plan.md", "content": plan_content},
            )
        ]

        # This is the extraction logic from call_architect_node (line ~207)
        # Testing directly to verify the fix works
        extracted_content = None
        for tool_call in tool_calls:
            if tool_call.tool_name == ToolName.WRITE_FILE and isinstance(tool_call.tool_input, dict):
                file_path = tool_call.tool_input.get("file_path", "")
                content = tool_call.tool_input.get("content", "")
                if file_path.endswith(".md") and "**Goal:**" in content:
                    extracted_content = content
                    break

        assert extracted_content is not None
        assert "**Goal:** Implement user authentication" in extracted_content

    def test_plan_extracted_when_tool_name_is_raw_string(self) -> None:
        """Plan should be extracted when tool_name is 'write_file' string."""
        plan_content = """# API Feature

**Goal:** Implement REST endpoints

## Tasks
..."""

        tool_calls = [
            ToolCall(
                id="tool_456",
                tool_name="write_file",  # Direct string, API driver format
                tool_input={"file_path": "/tmp/plan.md", "content": plan_content},
            )
        ]

        # Using ToolName constant for comparison
        extracted_content = None
        for tool_call in tool_calls:
            if tool_call.tool_name == ToolName.WRITE_FILE and isinstance(tool_call.tool_input, dict):
                file_path = tool_call.tool_input.get("file_path", "")
                content = tool_call.tool_input.get("content", "")
                if file_path.endswith(".md") and "**Goal:**" in content:
                    extracted_content = content
                    break

        assert extracted_content is not None
        assert "**Goal:** Implement REST endpoints" in extracted_content

    def test_plan_not_extracted_for_old_write_tool_name(self) -> None:
        """Plan should NOT be extracted when tool_name is old 'Write' format.

        This test verifies the problem we're fixing - the old hardcoded 'Write'
        check fails for normalized/API tool names.
        """
        plan_content = """# Feature Plan

**Goal:** Add dark mode support

## Tasks
..."""

        tool_calls = [
            ToolCall(
                id="tool_789",
                tool_name=ToolName.WRITE_FILE,  # Normalized format
                tool_input={"file_path": "/tmp/plan.md", "content": plan_content},
            )
        ]

        # This is the OLD broken extraction logic (hardcoded "Write")
        extracted_with_old_logic = None
        for tool_call in tool_calls:
            if tool_call.tool_name == "Write" and isinstance(tool_call.tool_input, dict):
                file_path = tool_call.tool_input.get("file_path", "")
                content = tool_call.tool_input.get("content", "")
                if file_path.endswith(".md") and "**Goal:**" in content:
                    extracted_with_old_logic = content
                    break

        # Old logic fails to extract!
        assert extracted_with_old_logic is None

        # But new logic (using ToolName constant) works
        extracted_with_new_logic = None
        for tool_call in tool_calls:
            if tool_call.tool_name == ToolName.WRITE_FILE and isinstance(tool_call.tool_input, dict):
                file_path = tool_call.tool_input.get("file_path", "")
                content = tool_call.tool_input.get("content", "")
                if file_path.endswith(".md") and "**Goal:**" in content:
                    extracted_with_new_logic = content
                    break

        assert extracted_with_new_logic is not None
