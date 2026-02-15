"""FastAPI application setup and configuration.

Note: Imports are intentionally placed after _check_dependencies() to provide
a user-friendly error message when asyncpg/PostgreSQL dependencies are missing.
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
        import asyncpg  # noqa: F401
    except ModuleNotFoundError:
        missing.append("asyncpg")

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
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from amelia import __version__
from amelia.drivers.base import DriverInterface
from amelia.drivers.factory import (
    cleanup_driver_session,
    get_driver as factory_get_driver,
)
from amelia.logging import configure_logging, log_server_startup
from amelia.pipelines.implementation.state import rebuild_implementation_state
from amelia.sandbox.proxy import ProviderConfig, create_proxy_router
from amelia.sandbox.teardown import teardown_all_sandbox_containers
from amelia.server.config import ServerConfig
from amelia.server.database import ProfileRepository, SettingsRepository, WorkflowRepository
from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator
from amelia.server.database.prompt_repository import PromptRepository
from amelia.server.dependencies import (
    clear_config,
    clear_database,
    clear_knowledge_service,
    clear_orchestrator,
    get_profile_repository,
    set_config,
    set_database,
    set_knowledge_service,
    set_orchestrator,
)
from amelia.server.events.bus import EventBus
from amelia.server.lifecycle.health_checker import WorktreeHealthChecker
from amelia.server.lifecycle.retention import LogRetentionService
from amelia.server.lifecycle.server import ServerLifecycle
from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.routes import (
    config_router,
    files_router,
    health_router,
    knowledge_router,
    paths_router,
    usage_router,
    websocket_router,
    workflows_router,
)
from amelia.server.routes.brainstorm import (
    get_brainstorm_service,
    get_cwd,
    get_driver,
    router as brainstorm_router,
)
from amelia.server.routes.oracle import (
    get_event_bus as oracle_get_event_bus,
    router as oracle_router,
)
from amelia.server.routes.prompts import get_prompt_repository, router as prompts_router
from amelia.server.routes.settings import router as settings_router
from amelia.server.routes.websocket import connection_manager
from amelia.server.routes.workflows import configure_exception_handlers
from amelia.knowledge.embeddings import EmbeddingClient
from amelia.knowledge.ingestion import IngestionPipeline
from amelia.knowledge.repository import KnowledgeRepository
from amelia.knowledge.service import KnowledgeService
from amelia.server.services.brainstorm import BrainstormService


def create_driver_cleanup_callback() -> Callable[[str, str], Awaitable[bool]]:
    """Create async callback for cleaning up driver sessions.

    Returns:
        Async callback that takes (driver_type, driver_session_id) and returns bool.
    """

    async def cleanup(driver_type: str, driver_session_id: str) -> bool:
        return await cleanup_driver_session(driver_type, driver_session_id)

    return cleanup


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan events.

    Sets start_time on startup for uptime calculation.
    Initializes configuration, database, orchestrator, and lifecycle components.
    """
    # Rebuild ImplementationState forward references before any instantiation.
    # ServerExecutionState no longer has forward refs (execution_state field removed).
    rebuild_implementation_state()

    # Configure logging (needed when uvicorn loads app directly, e.g. with --reload)
    log_level = os.environ.get("AMELIA_LOG_LEVEL", "INFO").upper()
    configure_logging(level=log_level)

    # Initialize configuration
    config = ServerConfig()
    set_config(config)

    # Connect to database and run migrations
    database = Database(config.database_url, min_size=config.db_pool_min_size, max_size=config.db_pool_max_size)
    try:
        await database.connect()
    except ConnectionError:
        logger.error("Failed to connect to database. Is PostgreSQL running? Try: docker compose up -d postgres")
        raise
    migrator = Migrator(database)
    await migrator.run()
    await migrator.initialize_prompts()

    # Initialize settings with defaults
    settings_repo = SettingsRepository(database)
    await settings_repo.ensure_defaults()

    # Get server settings for orchestrator configuration
    server_settings = await settings_repo.get_server_settings()

    # Set the database in dependencies module for DI
    set_database(database)

    # Create repositories
    repository = WorkflowRepository(database)
    profile_repo = ProfileRepository(database)

    # Create event bus
    event_bus = EventBus()
    # Wire WebSocket broadcasting and repository
    event_bus.set_connection_manager(connection_manager)
    connection_manager.set_repository(repository)
    connection_manager.set_stream_tool_results(server_settings.stream_tool_results)

    # Create and register orchestrator
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    exit_stack = AsyncExitStack()

    # Register proxy cleanup early so it runs even if startup fails
    # proxy_cleanup is always set by create_app() before lifespan runs
    exit_stack.push_async_callback(app.state.proxy_cleanup)

    checkpointer = await exit_stack.enter_async_context(
        AsyncPostgresSaver.from_conn_string(config.database_url)
    )
    await checkpointer.setup()

    orchestrator = OrchestratorService(
        event_bus=event_bus,
        repository=repository,
        profile_repo=profile_repo,
        max_concurrent=server_settings.max_concurrent,
        checkpointer=checkpointer,
    )
    set_orchestrator(orchestrator)

    # Create brainstorm repository and service
    brainstorm_repo = BrainstormRepository(database)
    brainstorm_service = BrainstormService(
        repository=brainstorm_repo,
        event_bus=event_bus,
        driver_cleanup=create_driver_cleanup_callback(),
        profile_repo=profile_repo,
    )
    app.state.brainstorm_service = brainstorm_service
    app.state.event_bus = event_bus

    # Create knowledge service
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_api_key:
        embedding_client = EmbeddingClient(api_key=openrouter_api_key)
        knowledge_repo = KnowledgeRepository(database.pool)
        ingestion_pipeline = IngestionPipeline(
            repository=knowledge_repo,
            embedding_client=embedding_client,
        )
        knowledge_service = KnowledgeService(
            event_bus=event_bus,
            ingestion_pipeline=ingestion_pipeline,
        )
        set_knowledge_service(knowledge_service)
    else:
        knowledge_service = None
        logger.warning("OPENROUTER_API_KEY not set, knowledge service disabled")

    # Create lifecycle components
    log_retention = LogRetentionService(
        db=database, config=server_settings, checkpointer=checkpointer
    )
    lifecycle = ServerLifecycle(
        orchestrator=orchestrator,
        log_retention=log_retention,
    )
    health_checker = WorktreeHealthChecker(orchestrator=orchestrator)
    app.state.lifecycle = lifecycle

    # Start lifecycle components
    await lifecycle.startup()
    await health_checker.start()

    # Log server startup with styled banner
    log_server_startup(
        host=config.host,
        port=config.port,
        database_url=config.database_url,
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
    if knowledge_service is not None:
        await knowledge_service.cleanup()
        clear_knowledge_service()
    await teardown_all_sandbox_containers()
    clear_orchestrator()
    await exit_stack.aclose()  # Also cleans up proxy HTTP client

    await database.close()
    clear_database()
    clear_config()


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

    # Add CORS middleware to restrict origins to the dashboard
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8420",
            "http://localhost:8420",
            "http://127.0.0.1:8421",
            "http://localhost:8421",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routes
    application.include_router(config_router, prefix="/api")
    application.include_router(files_router, prefix="/api")
    application.include_router(health_router, prefix="/api")
    application.include_router(paths_router, prefix="/api")
    application.include_router(usage_router, prefix="/api")
    application.include_router(workflows_router, prefix="/api")
    application.include_router(brainstorm_router, prefix="/api/brainstorm")
    application.include_router(oracle_router, prefix="/api/oracle")
    application.include_router(knowledge_router, prefix="/api")
    application.include_router(websocket_router)  # No prefix - route is /ws/events
    application.include_router(prompts_router)  # Already has /api/prompts prefix
    application.include_router(settings_router)  # Already has /api prefix

    # Set up prompt repository dependency
    def get_prompt_repo() -> PromptRepository:
        from amelia.server.dependencies import get_database
        return PromptRepository(get_database())

    application.dependency_overrides[get_prompt_repository] = get_prompt_repo

    # Set up brainstorm service dependency
    def get_brainstorm_svc() -> BrainstormService:
        service: BrainstormService = application.state.brainstorm_service
        return service

    application.dependency_overrides[get_brainstorm_service] = get_brainstorm_svc

    # Set up driver dependency for brainstorm routes
    async def get_brainstorm_driver() -> DriverInterface:
        """Get driver for brainstorming using active profile from database.

        Fetches the active profile from the ProfileRepository and returns
        the configured driver using the 'brainstormer' agent config.
        Falls back to CLI driver if no active profile or no brainstormer config.
        """
        profile_repo = get_profile_repository()
        active_profile = await profile_repo.get_active_profile()
        if active_profile is None:
            # No active profile - use CLI driver as default
            return factory_get_driver("cli")
        try:
            agent_config = active_profile.get_agent_config("brainstormer")
            return factory_get_driver(agent_config.driver, model=agent_config.model)
        except ValueError:
            # No brainstormer config - fallback to CLI driver
            return factory_get_driver("cli")

    application.dependency_overrides[get_driver] = get_brainstorm_driver

    # Set up cwd dependency for brainstorm routes
    async def get_brainstorm_cwd() -> str:
        """Get working directory from active profile in database.

        Fetches the active profile and returns its working_dir.
        Falls back to os.getcwd() if no active profile or working_dir not set.
        """
        profile_repo = get_profile_repository()
        active_profile = await profile_repo.get_active_profile()
        if active_profile is None or not active_profile.working_dir:
            return os.getcwd()
        return active_profile.working_dir

    application.dependency_overrides[get_cwd] = get_brainstorm_cwd

    # Set up Oracle dependencies
    def get_oracle_event_bus() -> EventBus:
        """Get EventBus for Oracle consultations."""
        bus: EventBus = application.state.event_bus
        return bus

    application.dependency_overrides[oracle_get_event_bus] = get_oracle_event_bus

    # Mount sandbox proxy routes
    async def _resolve_provider(profile_name: str) -> ProviderConfig | None:
        """Resolve LLM provider config from profile name.

        Looks up the profile in the database, finds the developer agent's
        provider setting, and returns the corresponding upstream URL and API key.
        """
        profile_repo = get_profile_repository()
        profile = await profile_repo.get_profile(profile_name)
        if profile is None:
            return None

        # Use developer agent config to determine provider
        try:
            agent_config = profile.get_agent_config("developer")
        except ValueError:
            return None

        provider = agent_config.options.get("provider", "openrouter")

        # Map provider to upstream config
        # NOTE: Only OpenAI-compatible providers (using /chat/completions endpoint)
        # are supported. Anthropic uses /messages and requires different auth headers.
        # TODO(#420): Move provider registry to database-stored configuration
        provider_registry: dict[str, str] = {
            "openrouter": "https://openrouter.ai/api/v1",
            "openai": "https://api.openai.com/v1",
        }
        api_key_env_vars: dict[str, str] = {
            "openrouter": "OPENROUTER_API_KEY",
            "openai": "OPENAI_API_KEY",
        }

        base_url = provider_registry.get(provider)
        env_var = api_key_env_vars.get(provider)
        if base_url is None or env_var is None:
            return None

        api_key = os.environ.get(env_var, "")
        if not api_key:
            return None

        return ProviderConfig(base_url=base_url, api_key=api_key)

    proxy = create_proxy_router(resolve_provider=_resolve_provider)
    application.include_router(proxy.router, prefix="/proxy/v1")
    application.state.proxy_cleanup = proxy.cleanup

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
