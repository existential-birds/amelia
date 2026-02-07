"""Database package for Amelia server.

Provides PostgreSQL database connectivity and repository patterns for workflow
persistence. Handles connection pooling, schema migration, and CRUD
operations for workflow state.
"""

from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator
from amelia.server.database.profile_repository import ProfileRecord, ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.database.settings_repository import ServerSettings, SettingsRepository


__all__ = [
    "Database",
    "Migrator",
    "ProfileRecord",
    "ProfileRepository",
    "ServerSettings",
    "SettingsRepository",
    "WorkflowRepository",
]
