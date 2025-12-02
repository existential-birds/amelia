"""Sequential database migration runner."""
from pathlib import Path

import aiosqlite
from loguru import logger


class MigrationRunner:
    """Sequential SQL migration runner for SQLite.

    Migrations are SQL files named with a numeric prefix:
    - 001_initial_schema.sql
    - 002_add_indexes.sql
    - etc.

    The version number is extracted from the filename prefix.
    """

    VERSION_TABLE = "schema_version"

    def __init__(self, db_path: Path, migrations_dir: Path):
        """Initialize migration runner.

        Args:
            db_path: Path to SQLite database file.
            migrations_dir: Directory containing migration SQL files.
        """
        self._db_path = db_path
        self._migrations_dir = migrations_dir

    async def run_migrations(self) -> int:
        """Run all pending migrations.

        Returns:
            Number of migrations applied.
        """
        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as conn:
            await self._ensure_version_table(conn)
            current = await self._get_current_version_internal(conn)
            migrations = self._get_pending_migrations(current)

            applied = 0
            for version, sql_file in migrations:
                logger.info(f"Applying migration {version}: {sql_file.name}")
                sql = sql_file.read_text()
                await self._execute_migration(conn, version, sql)
                applied += 1

            return applied

    async def get_current_version(self) -> int:
        """Get current schema version.

        Returns:
            Current version number (0 if no migrations applied).
        """
        if not self._db_path.exists():
            return 0

        async with aiosqlite.connect(self._db_path) as conn:
            try:
                return await self._get_current_version_internal(conn)
            except aiosqlite.OperationalError:
                return 0

    async def _ensure_version_table(self, conn: aiosqlite.Connection) -> None:
        """Create schema_version table if it doesn't exist."""
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.VERSION_TABLE} (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.commit()

    async def _get_current_version_internal(
        self,
        conn: aiosqlite.Connection,
    ) -> int:
        """Get current version from database.

        Args:
            conn: Active database connection.

        Returns:
            Current version (0 if none).
        """
        cursor = await conn.execute(
            f"SELECT MAX(version) FROM {self.VERSION_TABLE}"
        )
        result = await cursor.fetchone()
        return result[0] if result and result[0] else 0

    def _get_pending_migrations(
        self,
        current_version: int,
    ) -> list[tuple[int, Path]]:
        """Get migrations with version > current, sorted by version.

        Args:
            current_version: Current schema version.

        Returns:
            List of (version, path) tuples for pending migrations.
        """
        if not self._migrations_dir.exists():
            return []

        migrations = []
        for sql_file in self._migrations_dir.glob("*.sql"):
            # Extract version from filename: 001_initial_schema.sql -> 1
            try:
                version = int(sql_file.stem.split("_")[0])
            except (ValueError, IndexError):
                logger.warning(f"Skipping invalid migration filename: {sql_file.name}")
                continue

            if version > current_version:
                migrations.append((version, sql_file))

        return sorted(migrations, key=lambda x: x[0])

    async def _execute_migration(
        self,
        conn: aiosqlite.Connection,
        version: int,
        sql: str,
    ) -> None:
        """Execute migration in transaction and record version.

        Args:
            conn: Database connection.
            version: Migration version number.
            sql: SQL to execute.
        """
        # Execute migration in transaction
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await conn.executescript(sql)
            await conn.execute(
                f"INSERT INTO {self.VERSION_TABLE} (version) VALUES (?)",
                (version,),
            )
            await conn.commit()
        except Exception:
            await conn.execute("ROLLBACK")
            raise
