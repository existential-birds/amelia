# tests/unit/server/models/test_responses.py
"""Tests for response models."""

from amelia.server.models.responses import BatchStartResponse


class TestBatchStartResponse:
    """Tests for BatchStartResponse model."""

    def test_all_started_success(self) -> None:
        """Response with all workflows started successfully."""
        response = BatchStartResponse(
            started=["wf-1", "wf-2", "wf-3"],
            errors={},
        )
        assert response.started == ["wf-1", "wf-2", "wf-3"]
        assert response.errors == {}

    def test_partial_success(self) -> None:
        """Response with some workflows started, some failed."""
        response = BatchStartResponse(
            started=["wf-1"],
            errors={
                "wf-2": "Worktree already has active workflow",
                "wf-3": "Workflow not found",
            },
        )
        assert response.started == ["wf-1"]
        assert len(response.errors) == 2
        assert "wf-2" in response.errors

    def test_all_failed(self) -> None:
        """Response when all workflows fail to start."""
        response = BatchStartResponse(
            started=[],
            errors={"wf-1": "Error 1", "wf-2": "Error 2"},
        )
        assert response.started == []
        assert len(response.errors) == 2

    def test_empty_response(self) -> None:
        """Response when no workflows to start."""
        response = BatchStartResponse(started=[], errors={})
        assert response.started == []
        assert response.errors == {}
