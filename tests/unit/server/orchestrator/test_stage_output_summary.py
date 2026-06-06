# tests/unit/server/orchestrator/test_stage_output_summary.py
"""Tests for STAGE_COMPLETED output summarization (fix for #427).

Emission-path coverage (that both STAGE_COMPLETED paths summarize) now lives in
``test_event_emitter.py``, asserting on the WorkflowEvents the bus broadcasts.
"""

from amelia.server.orchestrator.event_emitter import summarize_stage_output


class TestSummarizeStageOutput:
    """Tests for the summarize_stage_output helper."""

    def test_none_output_returns_none(self) -> None:
        assert summarize_stage_output(None) is None

    def test_empty_dict_returns_empty_dict(self) -> None:
        assert summarize_stage_output({}) == {}

    def test_tool_calls_replaced_with_count(self) -> None:
        output = {"tool_calls": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}
        result = summarize_stage_output(output)
        assert result is not None
        assert "tool_calls" not in result
        assert result["tool_calls_count"] == 3

    def test_tool_results_replaced_with_count(self) -> None:
        output = {"tool_results": [{"output": "a"}, {"output": "b"}]}
        result = summarize_stage_output(output)
        assert result is not None
        assert "tool_results" not in result
        assert result["tool_results_count"] == 2

    def test_long_strings_truncated(self) -> None:
        long_string = "x" * 600
        output = {"final_response": long_string}
        result = summarize_stage_output(output)
        assert result is not None
        assert len(result["final_response"]) < len(long_string)
        assert result["final_response"].endswith("… [truncated]")
        assert len(result["final_response"]) == 500 + len("… [truncated]")

    def test_short_strings_preserved(self) -> None:
        output = {"final_response": "short answer"}
        result = summarize_stage_output(output)
        assert result is not None
        assert result["final_response"] == "short answer"

    def test_string_at_boundary_preserved(self) -> None:
        output = {"msg": "x" * 500}
        result = summarize_stage_output(output)
        assert result is not None
        assert result["msg"] == "x" * 500

    def test_non_list_non_string_fields_preserved(self) -> None:
        output = {
            "agentic_status": "completed",
            "review_iteration": 3,
            "is_approved": True,
            "error": None,
        }
        result = summarize_stage_output(output)
        assert result == output

    def test_developer_node_realistic_output(self) -> None:
        output = {
            "agentic_status": "completed",
            "error": None,
            "driver_session_id": "sess-123",
            "final_response": "A" * 1000,
            "tool_calls": [{"id": str(i)} for i in range(163_000)],
            "tool_results": [{"output": f"result-{i}"} for i in range(163_000)],
        }
        result = summarize_stage_output(output)
        assert result is not None
        assert result["agentic_status"] == "completed"
        assert result["error"] is None
        assert result["driver_session_id"] == "sess-123"
        assert result["tool_calls_count"] == 163_000
        assert result["tool_results_count"] == 163_000
        assert "tool_calls" not in result
        assert "tool_results" not in result
        assert result["final_response"].endswith("… [truncated]")

    def test_architect_node_realistic_output(self) -> None:
        output = {
            "plan_markdown": "B" * 2000,
            "architect_error": None,
            "tool_calls": [{"id": "1"}],
            "tool_results": [{"output": "r1"}],
        }
        result = summarize_stage_output(output)
        assert result is not None
        assert result["plan_markdown"].endswith("… [truncated]")
        assert result["architect_error"] is None
        assert result["tool_calls_count"] == 1
        assert result["tool_results_count"] == 1

    def test_nested_dict_strings_truncated(self) -> None:
        """Nested dictionaries should have their string values truncated."""
        output = {
            "metadata": {
                "description": "x" * 600,
                "short_field": "short",
            },
        }
        result = summarize_stage_output(output)
        assert result is not None
        assert result["metadata"]["description"].endswith("… [truncated]")
        assert len(result["metadata"]["description"]) == 500 + len("… [truncated]")
        assert result["metadata"]["short_field"] == "short"

    def test_nested_list_strings_truncated(self) -> None:
        """Lists containing strings should have those strings truncated."""
        output = {
            "messages": ["x" * 600, "short", "y" * 700],
        }
        result = summarize_stage_output(output)
        assert result is not None
        assert result["messages"][0].endswith("… [truncated]")
        assert result["messages"][1] == "short"
        assert result["messages"][2].endswith("… [truncated]")

    def test_deeply_nested_structures_truncated(self) -> None:
        """Deeply nested structures should have all strings truncated."""
        output = {
            "level1": {
                "level2": {
                    "level3": ["a" * 600, {"level4": "b" * 600}],
                },
            },
        }
        result = summarize_stage_output(output)
        assert result is not None
        assert result["level1"]["level2"]["level3"][0].endswith("… [truncated]")
        assert result["level1"]["level2"]["level3"][1]["level4"].endswith("… [truncated]")

    def test_list_of_dicts_with_long_strings(self) -> None:
        """Lists of dicts (common pattern) should be truncated."""
        output = {
            "results": [
                {"content": "x" * 600, "id": "1"},
                {"content": "short", "id": "2"},
            ],
        }
        result = summarize_stage_output(output)
        assert result is not None
        assert result["results"][0]["content"].endswith("… [truncated]")
        assert result["results"][0]["id"] == "1"
        assert result["results"][1]["content"] == "short"
        assert result["results"][1]["id"] == "2"

