"""Tests for database package exports."""


def test_database_exportable_from_package():
    """Database class is exported from database package."""
    from amelia.server.database import Database
    assert Database is not None


def test_migration_runner_exportable():
    """MigrationRunner is exported from database package."""
    from amelia.server.database import MigrationRunner
    assert MigrationRunner is not None


def test_database_available_from_server_package():
    """Database is accessible from server package."""
    from amelia.server import Database
    assert Database is not None
