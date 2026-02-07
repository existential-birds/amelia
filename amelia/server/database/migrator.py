"""Schema migration runner for PostgreSQL."""

from importlib import resources

from loguru import logger

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.server.database.connection import Database


class Migrator:
    """Runs versioned SQL migrations on startup."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def run(self) -> None:
        """Apply pending migrations."""
        await self._ensure_migrations_table()
        current = await self._current_version()
        migrations = self._load_migrations()

        for version, sql in migrations:
            if version > current:
                logger.info("Applying migration", version=version)
                await self._db.execute(sql)
                await self._db.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", version
                )
                logger.info("Migration applied", version=version)

    async def _ensure_migrations_table(self) -> None:
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

    async def _current_version(self) -> int:
        result = await self._db.fetch_scalar(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        )
        return int(result) if result is not None else 0

    def _load_migrations(self) -> list[tuple[int, str]]:
        """Load SQL migration files from the migrations directory."""
        migrations_dir = resources.files("amelia.server.database") / "migrations"
        result = []
        for path in sorted(migrations_dir.iterdir(), key=lambda p: str(p)):
            name = path.name
            if name.endswith(".sql") and name[:3].isdigit():
                version = int(name[:3])
                sql = path.read_text(encoding="utf-8")
                result.append((version, sql))
        return sorted(result, key=lambda x: x[0])

    async def initialize_prompts(self) -> None:
        """Seed prompts table from defaults. Idempotent."""
        for prompt_id, default in PROMPT_DEFAULTS.items():
            existing = await self._db.fetch_one(
                "SELECT 1 FROM prompts WHERE id = $1", prompt_id
            )
            if not existing:
                await self._db.execute(
                    """INSERT INTO prompts (id, agent, name, description, current_version_id)
                       VALUES ($1, $2, $3, $4, NULL)""",
                    prompt_id,
                    default.agent,
                    default.name,
                    default.description,
                )
