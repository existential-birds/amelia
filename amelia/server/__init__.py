"""Amelia FastAPI server package.

Provide the HTTP server that manages workflow execution, persists state,
and streams events to connected clients. Include database access, exception
types, and configuration management.

Exports:
    ServerConfig: Configuration model for server settings.
    Database: SQLite database connection and session management.
    ConcurrencyLimitError: Too many concurrent workflows.
    InvalidStateError: Invalid workflow state transition attempted.
    WorkflowConflictError: Workflow already exists for repository.
    WorkflowNotFoundError: Requested workflow does not exist.
"""
from amelia.server.config import ServerConfig
from amelia.server.database import Database
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)


__all__ = [
    "ServerConfig",
    "Database",
    "ConcurrencyLimitError",
    "InvalidStateError",
    "WorkflowConflictError",
    "WorkflowNotFoundError",
]
