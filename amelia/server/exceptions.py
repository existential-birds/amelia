"""Custom exception classes for server API error handling."""


class WorkflowConflictError(Exception):
    """Raised when a workflow already exists for a worktree.

    HTTP Status: 409 Conflict
    """

    def __init__(self, worktree_path: str, workflow_id: str):
        """Initialize WorkflowConflictError.

        Args:
            worktree_path: Path to the conflicting worktree.
            workflow_id: ID of the existing workflow.
        """
        self.worktree_path = worktree_path
        self.workflow_id = workflow_id
        super().__init__(
            f"Workflow {workflow_id} already active for worktree {worktree_path}"
        )


class ConcurrencyLimitError(Exception):
    """Raised when concurrent workflow limit is exceeded.

    HTTP Status: 429 Too Many Requests
    """

    def __init__(self, max_concurrent: int, current_count: int | None = None):
        """Initialize ConcurrencyLimitError.

        Args:
            max_concurrent: Maximum allowed concurrent workflows.
            current_count: Current number of active workflows (defaults to max_concurrent).
        """
        self.max_concurrent = max_concurrent
        self.current_count = current_count if current_count is not None else max_concurrent
        super().__init__(
            f"Concurrency limit exceeded: {self.current_count}/{max_concurrent} workflows active"
        )


class InvalidStateError(Exception):
    """Raised when a workflow operation is invalid for current state.

    HTTP Status: 422 Unprocessable Entity
    """

    def __init__(
        self,
        message: str,
        workflow_id: str,
        current_status: str | None = None,
    ):
        """Initialize InvalidStateError.

        Args:
            message: Error message describing the invalid operation.
            workflow_id: ID of the workflow.
            current_status: Current workflow status (optional).
        """
        self.workflow_id = workflow_id
        self.current_status = current_status
        super().__init__(message)


class WorkflowNotFoundError(Exception):
    """Raised when workflow ID doesn't exist.

    HTTP Status: 404 Not Found
    """

    def __init__(self, workflow_id: str):
        """Initialize WorkflowNotFoundError.

        Args:
            workflow_id: ID of the missing workflow.
        """
        self.workflow_id = workflow_id
        super().__init__(f"Workflow not found: {workflow_id}")


class InvalidWorktreeError(Exception):
    """Raised when worktree path is invalid or not a git repository.

    HTTP Status: 400 Bad Request
    """

    def __init__(self, worktree_path: str, reason: str):
        """Initialize InvalidWorktreeError.

        Args:
            worktree_path: Path to the invalid worktree.
            reason: Explanation of why the worktree is invalid.
        """
        self.worktree_path = worktree_path
        self.reason = reason
        super().__init__(f"Invalid worktree '{worktree_path}': {reason}")
