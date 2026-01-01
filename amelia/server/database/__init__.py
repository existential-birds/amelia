"""Database package for Amelia server.

Provide SQLite database connectivity and repository patterns for workflow
persistence. Handle connection pooling, session management, and CRUD
operations for workflow state.

Exports:
    Database: Database connection manager with async session factory.
    WorkflowRepository: Repository for workflow CRUD operations.
    WorkflowNotFoundError: Raised when a workflow lookup fails.
"""

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.exceptions import WorkflowNotFoundError


__all__ = [
    "Database",
    "WorkflowRepository",
    "WorkflowNotFoundError",
]
