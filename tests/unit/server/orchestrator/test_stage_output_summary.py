# tests/unit/server/orchestrator/test_stage_output_summary.py
"""Tests for STAGE_COMPLETED output summarization (fix for #427)."""

from typing import TYPE_CHECKING, Self
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.orchestrator.service import _summarize_stage_output


if TYPE_CHECKING:
    from amelia.server.orchestrator.service import OrchestratorService


class TestSummarizeStageOutput:
    """Tests for the _summarize_stage_output helper."""

    def test_none_output_returns_none(self) -> None:
        assert _summarize_stage_output(None) is None

    def test_empty_dict_returns_empty_dict(self) -> None:
        assert _summarize_stage_output({}) == {}

    def test_tool_calls_replaced_with_count(self) -> None:
        output = {"tool_calls": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}
        result = _summarize_stage_output(output)
        assert result is not None
        assert "tool_calls" not in result
        assert result["tool_calls_count"] == 3

    def test_tool_results_replaced_with_count(self) -> None:
        output = {"tool_results": [{"output": "a"}, {"output": "b"}]}
        result = _summarize_stage_output(output)
        assert result is not None
        assert "tool_results" not in result
        assert result["tool_results_count"] == 2

    def test_long_strings_truncated(self) -> None:
        long_string = "x" * 600
        output = {"final_response": long_string}
        result = _summarize_stage_output(output)
        assert result is not None
        assert len(result["final_response"]) < len(long_string)
        assert result["final_response"].endswith("… [truncated]")
        assert len(result["final_response"]) == 500 + len("… [truncated]")

    def test_short_strings_preserved(self) -> None:
        output = {"final_response": "short answer"}
        result = _summarize_stage_output(output)
        assert result is not None
        assert result["final_response"] == "short answer"

    def test_string_at_boundary_preserved(self) -> None:
        output = {"msg": "x" * 500}
        result = _summarize_stage_output(output)
        assert result is not None
        assert result["msg"] == "x" * 500

    def test_non_list_non_string_fields_preserved(self) -> None:
        output = {
            "agentic_status": "completed",
            "review_iteration": 3,
            "is_approved": True,
            "error": None,
        }
        result = _summarize_stage_output(output)
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
        result = _summarize_stage_output(output)
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
            "raw_architect_output": "B" * 2000,
            "architect_error": None,
            "tool_calls": [{"id": "1"}],
            "tool_results": [{"output": "r1"}],
        }
        result = _summarize_stage_output(output)
        assert result is not None
        assert result["raw_architect_output"].endswith("… [truncated]")
        assert result["architect_error"] is None
        assert result["tool_calls_count"] == 1
        assert result["tool_results_count"] == 1


class TestEmissionPathsSummarize:
    """Tests that both STAGE_COMPLETED emission paths use summarized output."""

    @pytest.fixture
    def service(self: Self) -> "OrchestratorService":
        from amelia.server.orchestrator.service import OrchestratorService

        return OrchestratorService(
            repository=AsyncMock(),
            event_bus=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_handle_stream_chunk_uses_summary(self: Self, service: "OrchestratorService") -> None:
        """_handle_stream_chunk should summarize output in STAGE_COMPLETED events."""
        from amelia.server.models.events import EventType

        with (
            patch.object(service, "_emit", new_callable=AsyncMock) as mock_emit,
            patch.object(service, "_emit_agent_messages", new_callable=AsyncMock),
        ):
            big_output = {
                "tool_calls": [{"id": str(i)} for i in range(100)],
                "tool_results": [{"output": f"r{i}"} for i in range(100)],
                "agentic_status": "completed",
            }

            await service._handle_stream_chunk("wf-1", {"developer_node": big_output})

            # Find the STAGE_COMPLETED call
            stage_completed_calls = [
                c
                for c in mock_emit.call_args_list
                if c.args[1] == EventType.STAGE_COMPLETED
            ]
            assert len(stage_completed_calls) == 1

            data = stage_completed_calls[0].kwargs.get("data") or stage_completed_calls[
                0
            ].args[4]
            assert data["output"]["tool_calls_count"] == 100
            assert data["output"]["tool_results_count"] == 100
            assert "tool_calls" not in data["output"]
            assert "tool_results" not in data["output"]
            assert data["output"]["agentic_status"] == "completed"

    @pytest.mark.asyncio
    async def test_handle_stream_chunk_passes_raw_to_emit_agent_messages(
        self: Self, service: "OrchestratorService"
    ) -> None:
        """_emit_agent_messages should still receive the raw output."""
        with (
            patch.object(service, "_emit", new_callable=AsyncMock),
            patch.object(service, "_emit_agent_messages", new_callable=AsyncMock) as mock_emit_agent_messages,
        ):
            big_output = {
                "tool_calls": [{"id": "1"}],
                "agentic_status": "completed",
            }

            await service._handle_stream_chunk("wf-1", {"developer_node": big_output})

            # _emit_agent_messages should get the original, unsummarized output
            mock_emit_agent_messages.assert_called_once_with(
                "wf-1", "developer_node", big_output
            )

    @pytest.mark.asyncio
    async def test_handle_graph_event_uses_summary(
        self: Self, service: "OrchestratorService"
    ) -> None:
        """_handle_graph_event should summarize output in STAGE_COMPLETED events."""
        from amelia.server.models.events import EventType

        with patch.object(service, "_emit", new_callable=AsyncMock) as mock_emit:
            event: dict[str, object] = {
                "event": "on_chain_end",
                "name": "architect_node",
                "data": {
                    "tool_calls": [{"id": "1"}, {"id": "2"}],
                    "raw_architect_output": "plan details",
                },
            }

            await service._handle_graph_event("wf-1", event)

            stage_completed_calls = [
                c
                for c in mock_emit.call_args_list
                if c.args[1] == EventType.STAGE_COMPLETED
            ]
            assert len(stage_completed_calls) == 1

            data = stage_completed_calls[0].kwargs.get("data") or stage_completed_calls[
                0
            ].args[4]
            assert data["output"]["tool_calls_count"] == 2
            assert "tool_calls" not in data["output"]
            assert data["output"]["raw_architect_output"] == "plan details"
