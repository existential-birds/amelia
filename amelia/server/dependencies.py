"""FastAPI dependency injection providers."""

from __future__ import annotations

from amelia.server.config import ServerConfig
from amelia.server.database import ProfileRepository, SettingsRepository, WorkflowRepository
from amelia.server.database.connection import Database
from amelia.server.orchestrator.service import OrchestratorService


# Module-level config instance
_config: ServerConfig | None = None

# Module-level database instance
_database: Database | None = None

# Module-level orchestrator instance
_orchestrator: OrchestratorService | None = None


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

    Raises:
        RuntimeError: If database not initialized.
    """
    db = get_database()
    return WorkflowRepository(db)


def get_settings_repository() -> SettingsRepository:
    """Get the settings repository instance.

    Returns:
        SettingsRepository instance.

    Raises:
        RuntimeError: If database not initialized.
    """
    return SettingsRepository(get_database())


def get_profile_repository() -> ProfileRepository:
    """Get the profile repository instance.

    Returns:
        ProfileRepository instance.

    Raises:
        RuntimeError: If database not initialized.
    """
    return ProfileRepository(get_database())


def set_orchestrator(orch: OrchestratorService) -> None:
    """Set the global orchestrator instance.

    This should be called during application startup.

    Args:
        orch: OrchestratorService instance to set.
    """
    global _orchestrator
    _orchestrator = orch


def clear_orchestrator() -> None:
    """Clear the global orchestrator instance.

    This should be called during application shutdown.
    """
    global _orchestrator
    _orchestrator = None


def get_orchestrator() -> OrchestratorService:
    """Get the orchestrator instance.

    Returns:
        The current OrchestratorService instance.

    Raises:
        RuntimeError: If orchestrator not initialized.
    """
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized. Is the server running?")
    return _orchestrator


def set_config(config: ServerConfig) -> None:
    """Set the global config instance.

    This should be called during application startup.

    Args:
        config: ServerConfig instance to set.
    """
    global _config
    _config = config


def clear_config() -> None:
    """Clear the global config instance.

    This should be called during application shutdown.
    """
    global _config
    _config = None


def get_config() -> ServerConfig:
    """Get the config instance.

    Returns:
        The current ServerConfig instance.

    Raises:
        RuntimeError: If config not initialized.
    """
    if _config is None:
        raise RuntimeError("Server config not initialized. Is the server running?")
    return _config
