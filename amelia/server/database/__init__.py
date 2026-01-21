"""Database package for Amelia server.

Provide SQLite database connectivity and repository patterns for workflow
persistence. Handle connection pooling, session management, and CRUD
operations for workflow state.

Exports:
    Database: Database connection manager with async session factory.
    WorkflowRepository: Repository for workflow CRUD operations.
    WorkflowNotFoundError: Raised when a workflow lookup fails.
    SettingsRepository: Repository for server settings CRUD operations.
    ServerSettings: Server settings data class.
    ProfileRepository: Repository for profile CRUD operations.
    ProfileRecord: Profile data record for database operations.
"""

from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRecord, ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.database.settings_repository import ServerSettings, SettingsRepository
from amelia.server.exceptions import WorkflowNotFoundError


__all__ = [
    "Database",
    "ProfileRecord",
    "ProfileRepository",
    "ServerSettings",
    "SettingsRepository",
    "WorkflowNotFoundError",
    "WorkflowRepository",
]
