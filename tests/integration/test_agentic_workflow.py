# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for agentic workflow."""
import pytest

from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.core.types import Issue


@pytest.mark.integration
class TestAgenticOrchestrator:
    """Test agentic workflow graph structure."""

    def test_graph_has_required_nodes(self):
        """Graph should have architect, developer, reviewer nodes."""
        graph = create_orchestrator_graph()
        graph_str = str(graph.get_graph().nodes)

        assert "architect" in graph_str
        assert "developer" in graph_str
        assert "reviewer" in graph_str

    def test_graph_does_not_have_batch_nodes(self):
        """Graph should NOT have batch/blocker nodes."""
        graph = create_orchestrator_graph()
        graph_str = str(graph.get_graph().nodes)

        assert "batch_approval" not in graph_str
        assert "blocker" not in graph_str
        assert "batch" not in graph_str.lower() or "batch_approval" not in graph_str

    def test_graph_has_human_approval_node(self):
        """Graph should have human approval node."""
        graph = create_orchestrator_graph()
        graph_str = str(graph.get_graph().nodes)

        assert "human_approval" in graph_str


@pytest.mark.integration
class TestExecutionStateAgentic:
    """Test ExecutionState for agentic fields."""

    def test_execution_state_has_goal(self):
        """ExecutionState should have goal field."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature X",
        )
        assert state.goal == "Implement feature X"

    def test_execution_state_has_tool_tracking(self):
        """ExecutionState should track tool calls and results."""
        from amelia.core.agentic_state import ToolCall, ToolResult

        call = ToolCall(id="1", tool_name="shell", tool_input={"cmd": "ls"})
        result = ToolResult(call_id="1", tool_name="shell", output="ok", success=True)

        state = ExecutionState(
            profile_id="test",
            goal="test",
            tool_calls=[call],
            tool_results=[result],
        )
        assert len(state.tool_calls) == 1
        assert len(state.tool_results) == 1

    def test_execution_state_no_batch_fields(self):
        """ExecutionState should NOT have batch/step fields."""
        state = ExecutionState(profile_id="test", goal="test")

        # These fields should not exist
        assert not hasattr(state, "execution_plan")
        assert not hasattr(state, "current_batch_index")
        assert not hasattr(state, "batch_results")
        assert not hasattr(state, "current_blocker")
