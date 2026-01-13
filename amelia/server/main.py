"""FastAPI application setup and configuration.

Note: Imports are intentionally placed after _check_dependencies() to provide
a user-friendly error message when langgraph-checkpoint-sqlite is missing.
This typically happens when running `amelia server` without `uv run`.
"""
# ruff: noqa: E402, PLC0415
import sys


def _check_dependencies() -> None:
    """Check that required dependencies are available.

    Raises:
        SystemExit: If required dependencies are missing.
    """
    missing = []
    try:
        import langgraph.checkpoint.sqlite.aio  # noqa: F401
    except ModuleNotFoundError:
        missing.append("langgraph-checkpoint-sqlite")

    if missing:
        print(
            f"\n[ERROR] Missing required dependencies: {', '.join(missing)}\n\n"
            "The Amelia server requires these packages to be installed.\n\n"
            "If you installed Amelia as a tool, reinstall with:\n\n"
            "    uv tool install --reinstall git+https://github.com/existential-birds/amelia.git\n\n"
            "If you're running from source, use:\n\n"
            "    uv run amelia server\n\n"
            "Or install the missing packages directly:\n\n"
            f"    pip install {' '.join(missing)}\n",
            file=sys.stderr,
        )
        sys.exit(1)


_check_dependencies()

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from amelia import __version__
from amelia.logging import configure_logging, log_server_startup
from amelia.server.config import ServerConfig
from amelia.server.database import WorkflowRepository
from amelia.server.database.connection import Database
from amelia.server.database.prompt_repository import PromptRepository
from amelia.server.dependencies import (
    clear_database,
    clear_orchestrator,
    set_database,
    set_orchestrator,
)
from amelia.server.events.bus import EventBus
from amelia.server.lifecycle.health_checker import WorktreeHealthChecker
from amelia.server.lifecycle.retention import LogRetentionService
from amelia.server.lifecycle.server import ServerLifecycle
from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.routes import health_router, websocket_router, workflows_router
from amelia.server.routes.prompts import get_prompt_repository, router as prompts_router
from amelia.server.routes.websocket import connection_manager
from amelia.server.routes.workflows import configure_exception_handlers


# Module-level config storage for DI
_config: ServerConfig | None = None


def get_config() -> ServerConfig:
    """FastAPI dependency that provides the server configuration.

    Returns:
        The current ServerConfig instance.

    Raises:
        RuntimeError: If config is not initialized (server not started).
    """
    if _config is None:
        raise RuntimeError("Server config not initialized. Is the server running?")
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan events.

    Sets start_time on startup for uptime calculation.
    Initializes configuration, database, orchestrator, and lifecycle components.
    """
    global _config

    # Configure logging (needed when uvicorn loads app directly, e.g. with --reload)
    log_level = os.environ.get("AMELIA_LOG_LEVEL", "INFO").upper()
    configure_logging(level=log_level)

    # Initialize configuration
    _config = ServerConfig()

    # Connect to database and ensure schema exists
    database = Database(_config.database_path)
    await database.connect()
    await database.ensure_schema()
    await database.initialize_prompts()

    # Set the database in dependencies module for DI
    set_database(database)

    # Create repository for orchestrator
    repository = WorkflowRepository(database)

    # Create event bus
    event_bus = EventBus()
    # Wire WebSocket broadcasting and repository
    event_bus.set_connection_manager(connection_manager)
    connection_manager.set_repository(repository)

    # Create and register orchestrator
    orchestrator = OrchestratorService(
        event_bus=event_bus,
        repository=repository,
        max_concurrent=_config.max_concurrent,
        checkpoint_path=str(_config.checkpoint_path),
    )
    set_orchestrator(orchestrator)

    # Create lifecycle components
    log_retention = LogRetentionService(
        db=database,
        config=_config,
        checkpoint_path=_config.checkpoint_path,
    )
    lifecycle = ServerLifecycle(
        orchestrator=orchestrator,
        log_retention=log_retention,
    )
    health_checker = WorktreeHealthChecker(orchestrator=orchestrator)

    # Start lifecycle components
    await lifecycle.startup()
    await health_checker.start()

    # Log server startup with styled banner
    log_server_startup(
        host=_config.host,
        port=_config.port,
        database_path=str(_config.database_path),
        version=__version__,
    )

    app.state.start_time = datetime.now(UTC)
    yield

    # Shutdown - stop components in reverse order
    # Wait for pending broadcast tasks before closing connections
    await event_bus.cleanup()
    # Close WebSocket connections
    await connection_manager.close_all(code=1001, reason="Server shutting down")

    await health_checker.stop()
    await lifecycle.shutdown()
    clear_orchestrator()
    await database.close()
    clear_database()
    _config = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    application = FastAPI(
        title="Amelia API",
        description="Agentic coding orchestrator REST API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Configure exception handlers
    configure_exception_handlers(application)

    # Mount routes
    application.include_router(health_router, prefix="/api")
    application.include_router(workflows_router, prefix="/api")
    application.include_router(websocket_router)  # No prefix - route is /ws/events
    application.include_router(prompts_router)  # Already has /api/prompts prefix

    # Set up prompt repository dependency
    def get_prompt_repo() -> PromptRepository:
        from amelia.server.dependencies import get_database
        return PromptRepository(get_database())

    application.dependency_overrides[get_prompt_repository] = get_prompt_repo

    # Serve dashboard static files
    # Priority: bundled static files (installed package) > dev build (dashboard/dist)
    bundled_static_dir = Path(__file__).parent / "static"
    dev_dashboard_dir = Path(__file__).parent.parent.parent / "dashboard" / "dist"

    # Determine dashboard directory (None if not built)
    if (bundled_static_dir / "index.html").exists():
        dashboard_dir = bundled_static_dir
    elif dev_dashboard_dir.exists():
        dashboard_dir = dev_dashboard_dir
    else:
        dashboard_dir = None

    # Mount assets if dashboard exists
    if dashboard_dir is not None:
        assets_dir = dashboard_dir / "assets"
        if assets_dir.exists():
            application.mount(
                "/assets", StaticFiles(directory=assets_dir), name="assets"
            )

    # Single SPA fallback route - handles both "built" and "not built" cases at runtime
    @application.api_route(
        "/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    async def serve_dashboard(full_path: str) -> Response:
        """Serve dashboard index.html or return build instructions.

        This route handles all non-API paths:
        - If dashboard is built: serves index.html for SPA client-side routing
        - If dashboard is not built: returns JSON with build instructions
        """
        # Skip API and WebSocket routes - let 404 handler deal with them
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Serve dashboard if built
        if dashboard_dir is not None:
            index_file = dashboard_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file)

        # Dashboard not built - return instructions
        return JSONResponse({
            "message": "Dashboard not built",
            "instructions": "Run 'cd dashboard && pnpm run build' to build the dashboard",
        })

    return application


# Create app instance
app = create_app()
