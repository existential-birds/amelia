from amelia.server.database.repository import _build_workflow_filters
from amelia.server.models.state import WorkflowStatus


def test_no_filters():
    assert _build_workflow_filters() == ([], [])


def test_status_only():
    conds, params = _build_workflow_filters(status=WorkflowStatus.IN_PROGRESS)
    assert conds == ["status = $1"]
    assert params == [WorkflowStatus.IN_PROGRESS]


def test_worktree_only():
    conds, params = _build_workflow_filters(worktree_path="/repo")
    assert conds == ["worktree_path = $1"]
    assert params == ["/repo"]


def test_status_and_worktree_index_advances():
    conds, params = _build_workflow_filters(status=WorkflowStatus.BLOCKED, worktree_path="/repo")
    assert conds == ["status = $1", "worktree_path = $2"]
    assert params == [WorkflowStatus.BLOCKED, "/repo"]


def test_cursor_clause(_dt=__import__("datetime").datetime(2025, 1, 1)):  # noqa: B008
    conds, params = _build_workflow_filters(after_started_at=_dt, after_id="abc")
    assert conds == ["(started_at < $1 OR (started_at = $2 AND id < $3))"]
    assert params == [_dt, _dt, "abc"]
