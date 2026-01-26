"""Custom exception classes for server API error handling."""


class WorkflowConflictError(Exception):
    """Raised when a workflow conflict occurs.

    HTTP Status: 409 Conflict

    Can be raised for:
    - Worktree already has an active workflow
    - Plan already exists (use force to overwrite)
    - Architect is currently running
    """

    worktree_path: str | None
    workflow_id: str | None

    def __init__(
        self,
        message_or_worktree: str,
        workflow_id: str | None = None,
    ):
        """Initialize WorkflowConflictError.

        Args:
            message_or_worktree: Either a custom message, or the path to the
                conflicting worktree (when workflow_id is provided).
            workflow_id: ID of the existing workflow (when using worktree conflict mode).
        """
        if workflow_id is not None:
            # Worktree conflict mode: (worktree_path, workflow_id)
            self.worktree_path = message_or_worktree
            self.workflow_id = workflow_id
            message = f"Workflow {workflow_id} already active for worktree {message_or_worktree}"
        else:
            # Message-only mode: custom conflict message
            self.worktree_path = None
            self.workflow_id = None
            message = message_or_worktree
        super().__init__(message)


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


class FileOperationError(Exception):
    """Raised when a file operation fails.

    HTTP Status: Varies (400 Bad Request or 404 Not Found)
    """

    def __init__(self, message: str, code: str, status_code: int = 400):
        self.code = code
        self.status_code = status_code
        super().__init__(message)
