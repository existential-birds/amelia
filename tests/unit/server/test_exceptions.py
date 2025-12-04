"""Unit tests for server exception classes."""


from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)


def test_workflow_conflict_error():
    """Test WorkflowConflictError stores worktree_path and workflow_id."""
    error = WorkflowConflictError(
        worktree_path="/tmp/issue-123",
        workflow_id="wf-abc",
    )
    assert error.worktree_path == "/tmp/issue-123"
    assert error.workflow_id == "wf-abc"
    assert "already active" in str(error)


def test_concurrency_limit_error_with_current_count():
    """Test ConcurrencyLimitError with explicit current_count."""
    error = ConcurrencyLimitError(max_concurrent=5, current_count=5)
    assert error.max_concurrent == 5
    assert error.current_count == 5


def test_concurrency_limit_error_defaults_current_to_max():
    """Test ConcurrencyLimitError defaults current_count to max_concurrent."""
    error = ConcurrencyLimitError(max_concurrent=3)
    assert error.max_concurrent == 3
    assert error.current_count == 3


def test_invalid_state_error_with_current_status():
    """Test InvalidStateError with current_status."""
    error = InvalidStateError(
        message="Cannot start workflow",
        workflow_id="wf-xyz",
        current_status="running",
    )
    assert error.workflow_id == "wf-xyz"
    assert error.current_status == "running"
    assert "Cannot start workflow" in str(error)


def test_invalid_state_error_without_current_status():
    """Test InvalidStateError without current_status."""
    error = InvalidStateError(
        message="Invalid transition",
        workflow_id="wf-123",
    )
    assert error.workflow_id == "wf-123"
    assert error.current_status is None


def test_workflow_not_found_error():
    """Test WorkflowNotFoundError stores workflow_id."""
    error = WorkflowNotFoundError(workflow_id="wf-missing")
    assert error.workflow_id == "wf-missing"
    assert "not found" in str(error)
