"""FastAPI dependency injection providers."""

from amelia.server.database import WorkflowRepository
from amelia.server.database.connection import Database


# Module-level database instance
_database: Database | None = None


def set_database(db: Database) -> None:
    """Set the global database instance.

    This should be called during application startup.

    Args:
        db: Database instance to set.
    """
    global _database
    _database = db


def clear_database() -> None:
    """Clear the global database instance.

    This should be called during application shutdown.
    """
    global _database
    _database = None


def get_database() -> Database:
    """Get the database instance.

    Returns:
        The current Database instance.

    Raises:
        RuntimeError: If database not initialized.
    """
    if _database is None:
        raise RuntimeError("Database not initialized. Is the server running?")
    return _database


def get_repository() -> WorkflowRepository:
    """Get the workflow repository dependency.

    Returns:
        WorkflowRepository instance.
    """
    db = get_database()
    return WorkflowRepository(db)
