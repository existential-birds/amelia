"""Amelia CLI thin client package.

Provide HTTP client utilities for communicating with the Amelia server
from CLI commands. Include error handling, git context extraction, and
typed API wrappers for workflow management.

Exports:
    AmeliaClient: Async HTTP client for the Amelia server API.
    AmeliaClientError: Base exception for client errors.
    ServerUnreachableError: Server connection failure.
    WorkflowConflictError: Workflow already exists for repository.
    RateLimitError: Server rate limit exceeded.
    WorkflowNotFoundError: Requested workflow does not exist.
    InvalidRequestError: Malformed request to server.
    get_worktree_context: Extract git repository context for requests.
"""
from amelia.client.api import (
    AmeliaClient,
    AmeliaClientError,
    InvalidRequestError,
    RateLimitError,
    ServerUnreachableError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.client.git import get_worktree_context


__all__ = [
    "get_worktree_context",
    "AmeliaClient",
    "AmeliaClientError",
    "ServerUnreachableError",
    "WorkflowConflictError",
    "RateLimitError",
    "WorkflowNotFoundError",
    "InvalidRequestError",
]
