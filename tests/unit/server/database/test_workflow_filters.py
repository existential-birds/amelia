import datetime

from amelia.server.database.repository import _build_workflow_filters
from amelia.server.models.state import WorkflowStatus


_DT = datetime.datetime(2025, 1, 1)


class TestWorkflowFilters:
    def test_no_filters(self):
        assert _build_workflow_filters() == ([], [])

    def test_status_only(self):
        conds, params = _build_workflow_filters(status=WorkflowStatus.IN_PROGRESS)
        assert conds == ["status = $1"]
        assert params == [WorkflowStatus.IN_PROGRESS]

    def test_worktree_only(self):
        conds, params = _build_workflow_filters(worktree_path="/repo")
        assert conds == ["worktree_path = $1"]
        assert params == ["/repo"]

    def test_status_and_worktree_index_advances(self):
        conds, params = _build_workflow_filters(status=WorkflowStatus.BLOCKED, worktree_path="/repo")
        assert conds == ["status = $1", "worktree_path = $2"]
        assert params == [WorkflowStatus.BLOCKED, "/repo"]

    def test_cursor_clause(self):
        conds, params = _build_workflow_filters(after_started_at=_DT, after_id="abc")
        assert conds == ["(started_at < $1 OR (started_at = $2 AND id < $3))"]
        assert params == [_DT, _DT, "abc"]

    def test_status_and_cursor_index_advances(self):
        # Cursor placeholders must start at idx = len(params) + 1 = 2
        # when a leading status filter already occupies $1.
        conds, params = _build_workflow_filters(
            status=WorkflowStatus.IN_PROGRESS,
            after_started_at=_DT,
            after_id="abc",
        )
        assert conds == [
            "status = $1",
            "(started_at < $2 OR (started_at = $3 AND id < $4))",
        ]
        assert params == [WorkflowStatus.IN_PROGRESS, _DT, _DT, "abc"]

    def test_worktree_and_cursor_index_advances(self):
        # Cursor placeholders must start at idx = len(params) + 1 = 2
        # when a leading worktree_path filter already occupies $1.
        conds, params = _build_workflow_filters(
            worktree_path="/repo",
            after_started_at=_DT,
            after_id="abc",
        )
        assert conds == [
            "worktree_path = $1",
            "(started_at < $2 OR (started_at = $3 AND id < $4))",
        ]
        assert params == ["/repo", _DT, _DT, "abc"]
