# Server Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the FastAPI server skeleton with configuration and health endpoints.

**Architecture:** Server package structure with pydantic-settings configuration, basic FastAPI app, health endpoints for liveness/readiness probes, and CLI command to start the server.

**Tech Stack:** FastAPI, pydantic-settings, uvicorn, structlog, psutil

---

## Task 1: Add Server Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_dependencies.py
"""Verify server dependencies are available."""
import pytest


def test_fastapi_importable():
    """FastAPI should be importable."""
    import fastapi
    assert fastapi.__version__


def test_pydantic_settings_importable():
    """Pydantic-settings should be importable."""
    import pydantic_settings
    assert pydantic_settings.__version__


def test_uvicorn_importable():
    """Uvicorn should be importable."""
    import uvicorn
    assert uvicorn


def test_structlog_importable():
    """Structlog should be importable."""
    import structlog
    assert structlog


def test_psutil_importable():
    """Psutil should be importable."""
    import psutil
    assert psutil
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_dependencies.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Add dependencies to pyproject.toml**

Add to dependencies section in `pyproject.toml`:

```toml
dependencies = [
    # ... existing deps ...
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic-settings>=2.6.0",
    "structlog>=24.4.0",
    "psutil>=6.1.0",
    "aiosqlite>=0.20.0",
    "prometheus-client>=0.21.0",
]
```

**Step 4: Sync dependencies**

Run: `uv sync`
Expected: Dependencies installed successfully

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_dependencies.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/unit/server/test_dependencies.py
git commit -m "feat(server): add FastAPI server dependencies"
```

---

## Task 2: Create Server Package Structure

**Files:**
- Create: `amelia/server/__init__.py`
- Create: `amelia/server/config.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_config.py
"""Tests for server configuration."""
import os
import pytest
from unittest.mock import patch


class TestServerConfig:
    """Tests for ServerConfig."""

    def test_default_values(self):
        """ServerConfig has sensible defaults."""
        from amelia.server.config import ServerConfig

        config = ServerConfig()

        assert config.host == "127.0.0.1"
        assert config.port == 8420
        assert config.log_retention_days == 30
        assert config.log_retention_max_events == 100_000
        assert config.max_concurrent_workflows == 5
        assert config.request_timeout_seconds == 30.0
        assert config.websocket_idle_timeout_seconds == 300.0

    def test_env_override_port(self):
        """Port can be overridden via environment variable."""
        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_PORT": "9000"}):
            config = ServerConfig()
            assert config.port == 9000

    def test_env_override_host(self):
        """Host can be overridden via environment variable."""
        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_HOST": "0.0.0.0"}):
            config = ServerConfig()
            assert config.host == "0.0.0.0"

    def test_env_override_max_concurrent(self):
        """Max concurrent workflows can be overridden."""
        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_MAX_CONCURRENT_WORKFLOWS": "10"}):
            config = ServerConfig()
            assert config.max_concurrent_workflows == 10

    def test_env_override_retention_days(self):
        """Log retention days can be overridden."""
        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_LOG_RETENTION_DAYS": "90"}):
            config = ServerConfig()
            assert config.log_retention_days == 90

    def test_database_path_default(self):
        """Database path defaults to ~/.amelia/amelia.db."""
        from amelia.server.config import ServerConfig
        from pathlib import Path

        config = ServerConfig()
        expected = Path.home() / ".amelia" / "amelia.db"
        assert config.database_path == expected

    def test_database_path_override(self):
        """Database path can be overridden."""
        from amelia.server.config import ServerConfig
        from pathlib import Path

        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": "/tmp/test.db"}):
            config = ServerConfig()
            assert config.database_path == Path("/tmp/test.db")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_config.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create server package init**

```python
# amelia/server/__init__.py
"""Amelia FastAPI server package."""
from amelia.server.config import ServerConfig

__all__ = ["ServerConfig"]
```

**Step 4: Implement ServerConfig**

```python
# amelia/server/config.py
"""Server configuration with environment variable support."""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Server configuration with environment variable support.

    All settings can be overridden via environment variables with AMELIA_ prefix.
    Example: AMELIA_PORT=9000 overrides the port setting.
    """

    model_config = SettingsConfigDict(
        env_prefix="AMELIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server binding
    host: str = Field(
        default="127.0.0.1",
        description="Host to bind the server to",
    )
    port: int = Field(
        default=8420,
        ge=1,
        le=65535,
        description="Port to bind the server to",
    )

    # Concurrency
    max_concurrent_workflows: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum concurrent workflows",
    )

    # Log retention
    log_retention_days: int = Field(
        default=30,
        ge=1,
        description="Days to retain event logs",
    )
    log_retention_max_events: int = Field(
        default=100_000,
        ge=1000,
        description="Maximum events per workflow",
    )

    # Timeouts
    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="HTTP request timeout",
    )
    websocket_idle_timeout_seconds: float = Field(
        default=300.0,
        gt=0,
        description="WebSocket idle timeout (5 min default)",
    )
    workflow_start_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Max time to start a workflow",
    )

    # Rate limiting
    rate_limit_requests_per_minute: int = Field(
        default=60,
        ge=1,
        description="Rate limit: requests per minute",
    )
    rate_limit_burst_size: int = Field(
        default=10,
        ge=1,
        description="Rate limit: burst size",
    )

    # Database
    database_path: Path = Field(
        default_factory=lambda: Path.home() / ".amelia" / "amelia.db",
        description="Path to SQLite database file",
    )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_config.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/__init__.py amelia/server/config.py tests/unit/server/test_config.py
git commit -m "feat(server): add ServerConfig with pydantic-settings"
```

---

## Task 3: Create FastAPI Application Skeleton

**Files:**
- Create: `amelia/server/main.py`
- Create: `amelia/server/routes/__init__.py`
- Create: `amelia/server/routes/health.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_app.py
"""Tests for FastAPI application setup."""
import pytest
from fastapi.testclient import TestClient


class TestAppSetup:
    """Tests for FastAPI app configuration."""

    def test_app_title(self):
        """App has correct title."""
        from amelia.server.main import app

        assert app.title == "Amelia API"

    def test_app_version(self):
        """App has version set."""
        from amelia.server.main import app
        from amelia import __version__

        assert app.version == __version__

    def test_docs_url(self):
        """Swagger docs available at /api/docs."""
        from amelia.server.main import app

        assert app.docs_url == "/api/docs"

    def test_openapi_url(self):
        """OpenAPI schema at /api/openapi.json."""
        from amelia.server.main import app

        assert app.openapi_url == "/api/openapi.json"


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.fixture
    def client(self):
        """FastAPI test client."""
        from amelia.server.main import app
        return TestClient(app)

    def test_health_live_returns_200(self, client):
        """Liveness probe returns 200."""
        response = client.get("/api/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_health_ready_returns_200(self, client):
        """Readiness probe returns 200 when ready."""
        response = client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    def test_health_returns_detailed_info(self, client):
        """Main health endpoint returns detailed info."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "status" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "active_workflows" in data
        assert "websocket_connections" in data
        assert "memory_mb" in data
        assert "database" in data

        # Status should be healthy or degraded
        assert data["status"] in ("healthy", "degraded")

    def test_health_includes_database_status(self, client):
        """Health check includes database status."""
        response = client.get("/api/health")
        data = response.json()

        assert "database" in data
        assert "status" in data["database"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_app.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create routes package**

```python
# amelia/server/routes/__init__.py
"""API route modules."""
from amelia.server.routes.health import router as health_router

__all__ = ["health_router"]
```

**Step 4: Implement health endpoints**

```python
# amelia/server/routes/health.py
"""Health check endpoints for liveness and readiness probes."""
from datetime import datetime

import psutil
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from amelia import __version__


router = APIRouter(prefix="/health", tags=["health"])

# Server start time for uptime calculation
_start_time = datetime.utcnow()


@router.get("/live")
async def liveness() -> dict:
    """Minimal liveness check - is the server responding?

    Returns:
        Simple alive status.
    """
    return {"status": "alive"}


@router.get("/ready")
async def readiness() -> Response:
    """Readiness check - is the server ready to accept requests?

    Returns:
        Ready status or 503 if shutting down.
    """
    # TODO: Check lifecycle.is_shutting_down when implemented
    return JSONResponse(content={"status": "ready"})


@router.get("")
async def health() -> dict:
    """Detailed health check with server metrics.

    Returns:
        Comprehensive health status including:
        - Server status (healthy/degraded)
        - Version info
        - Uptime
        - Active workflow count
        - WebSocket connection count
        - Memory usage
        - Database status
    """
    process = psutil.Process()
    uptime = (datetime.utcnow() - _start_time).total_seconds()

    # TODO: Get actual counts when services are implemented
    active_workflows = 0
    websocket_connections = 0

    # TODO: Implement actual database health check
    db_status = {"status": "healthy", "mode": "wal"}

    overall_status = "healthy" if db_status["status"] == "healthy" else "degraded"

    return {
        "status": overall_status,
        "version": __version__,
        "uptime_seconds": uptime,
        "active_workflows": active_workflows,
        "websocket_connections": websocket_connections,
        "memory_mb": round(process.memory_info().rss / 1024 / 1024, 2),
        "cpu_percent": process.cpu_percent(),
        "database": db_status,
    }
```

**Step 5: Implement main app**

```python
# amelia/server/main.py
"""FastAPI application setup and configuration."""
from fastapi import FastAPI

from amelia import __version__
from amelia.server.routes import health_router


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
    )

    # Mount health routes
    application.include_router(health_router, prefix="/api")

    return application


# Create app instance
app = create_app()
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_app.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/main.py amelia/server/routes/__init__.py amelia/server/routes/health.py tests/unit/server/test_app.py
git commit -m "feat(server): add FastAPI app with health endpoints"
```

---

## Task 4: Add CLI Server Command

**Files:**
- Modify: `amelia/main.py`
- Create: `amelia/server/cli.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_cli.py
"""Tests for server CLI commands."""
import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner


class TestServerCLI:
    """Tests for 'amelia server' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_server_command_exists(self, runner):
        """'amelia server' command is registered."""
        from amelia.main import app

        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        assert "Start the Amelia API server" in result.stdout

    def test_server_default_port(self, runner):
        """Server uses default port 8420."""
        from amelia.main import app

        with patch("uvicorn.run") as mock_run:
            # Exit immediately to avoid blocking
            mock_run.side_effect = KeyboardInterrupt()
            result = runner.invoke(app, ["server"])

            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["port"] == 8420

    def test_server_custom_port(self, runner):
        """Server respects --port flag."""
        from amelia.main import app

        with patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            result = runner.invoke(app, ["server", "--port", "9000"])

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["port"] == 9000

    def test_server_bind_all_flag(self, runner):
        """--bind-all binds to 0.0.0.0."""
        from amelia.main import app

        with patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            result = runner.invoke(app, ["server", "--bind-all"])

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["host"] == "0.0.0.0"

    def test_server_bind_all_shows_warning(self, runner):
        """--bind-all shows security warning."""
        from amelia.main import app

        with patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            result = runner.invoke(app, ["server", "--bind-all"])

            assert "Warning" in result.stdout or "warning" in result.stdout.lower()

    def test_server_default_localhost(self, runner):
        """Server defaults to localhost binding."""
        from amelia.main import app

        with patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            result = runner.invoke(app, ["server"])

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["host"] == "127.0.0.1"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_cli.py -v`
Expected: FAIL (server command not found)

**Step 3: Create server CLI module**

```python
# amelia/server/cli.py
"""CLI commands for the Amelia server."""
from typing import Annotated

import typer
import uvicorn
from rich.console import Console

from amelia.server.config import ServerConfig


console = Console()

server_app = typer.Typer(
    name="server",
    help="Amelia API server commands.",
)


@server_app.callback(invoke_without_command=True)
def server(
    ctx: typer.Context,
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to listen on"),
    ] = 8420,
    bind_all: Annotated[
        bool,
        typer.Option(
            "--bind-all",
            help="Bind to all interfaces (0.0.0.0). WARNING: Exposes server to network.",
        ),
    ] = False,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Enable auto-reload for development"),
    ] = False,
) -> None:
    """Start the Amelia API server.

    By default, binds to localhost (127.0.0.1) only.
    Use --bind-all to expose to the network (not recommended without auth).
    """
    # Skip if subcommand is invoked
    if ctx.invoked_subcommand is not None:
        return

    host = "0.0.0.0" if bind_all else "127.0.0.1"

    if bind_all:
        console.print(
            "[yellow]Warning:[/yellow] Server accessible to all network clients. "
            "No authentication enabled.",
            style="bold yellow",
        )

    console.print(f"Starting Amelia server on http://{host}:{port}")
    console.print(f"API docs: http://{host}:{port}/api/docs")

    try:
        uvicorn.run(
            "amelia.server.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
        )
    except KeyboardInterrupt:
        console.print("\nServer stopped.")


@server_app.command("cleanup")
def cleanup(
    retention_days: Annotated[
        int,
        typer.Option("--retention-days", help="Days to retain logs"),
    ] = 30,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be deleted without deleting"),
    ] = False,
) -> None:
    """Run log retention cleanup manually.

    Useful if server was killed without graceful shutdown.
    """
    console.print(f"Running cleanup (retention: {retention_days} days, dry_run: {dry_run})")
    # TODO: Implement when LogRetentionService is available
    console.print("[yellow]Cleanup not yet implemented[/yellow]")
```

**Step 4: Register server command in main CLI**

Add to `amelia/main.py` after the existing imports:

```python
from amelia.server.cli import server_app

# After app = typer.Typer(...):
app.add_typer(server_app, name="server")
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_cli.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/cli.py amelia/main.py tests/unit/server/test_cli.py
git commit -m "feat(cli): add 'amelia server' command to start API server"
```

---

## Task 5: Add Structured Logging

**Files:**
- Create: `amelia/server/logging.py`
- Modify: `amelia/server/main.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_logging.py
"""Tests for structured logging configuration."""
import json
import pytest
from io import StringIO


class TestStructuredLogging:
    """Tests for structlog configuration."""

    def test_configure_logging_returns_logger(self):
        """configure_logging returns a bound logger."""
        from amelia.server.logging import configure_logging

        logger = configure_logging()
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")

    def test_log_output_is_json(self, capsys):
        """Log output is JSON formatted."""
        from amelia.server.logging import configure_logging

        logger = configure_logging()
        logger.info("test message", key="value")

        # Structlog outputs to stderr by default
        captured = capsys.readouterr()
        # The log should be parseable as JSON
        # Note: This depends on structlog configuration
        assert "test message" in captured.err or "test message" in captured.out

    def test_log_includes_timestamp(self):
        """Log entries include ISO timestamp."""
        from amelia.server.logging import configure_logging, capture_logs

        logger = configure_logging()

        with capture_logs() as logs:
            logger.info("test")

        assert len(logs) >= 1
        log_entry = logs[0]
        assert "timestamp" in log_entry

    def test_log_includes_level(self):
        """Log entries include log level."""
        from amelia.server.logging import configure_logging, capture_logs

        logger = configure_logging()

        with capture_logs() as logs:
            logger.warning("test warning")

        assert len(logs) >= 1
        log_entry = logs[0]
        assert log_entry.get("level") == "warning"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_logging.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement structured logging**

```python
# amelia/server/logging.py
"""Structured logging configuration for the server."""
from contextlib import contextmanager
from typing import Any, Generator

import structlog


# Captured logs for testing
_captured_logs: list[dict[str, Any]] = []
_capturing = False


def _capture_processor(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor that captures logs for testing."""
    if _capturing:
        _captured_logs.append(event_dict.copy())
    return event_dict


def configure_logging(json_output: bool = True) -> structlog.stdlib.BoundLogger:
    """Configure structured logging for the server.

    Args:
        json_output: If True, output JSON. If False, output console format.

    Returns:
        Configured structlog logger.
    """
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _capture_processor,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


@contextmanager
def capture_logs() -> Generator[list[dict[str, Any]], None, None]:
    """Context manager to capture log entries for testing.

    Yields:
        List of captured log entries as dicts.
    """
    global _capturing, _captured_logs
    _captured_logs = []
    _capturing = True
    try:
        yield _captured_logs
    finally:
        _capturing = False


# Default logger instance
logger = configure_logging()
```

**Step 4: Update server init**

```python
# amelia/server/__init__.py
"""Amelia FastAPI server package."""
from amelia.server.config import ServerConfig
from amelia.server.logging import configure_logging, logger

__all__ = ["ServerConfig", "configure_logging", "logger"]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_logging.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/logging.py amelia/server/__init__.py tests/unit/server/test_logging.py
git commit -m "feat(server): add structured logging with structlog"
```

---

## Task 6: Integration Test - Server Startup

**Files:**
- Create: `tests/integration/test_server_startup.py`

**Step 1: Write the integration test**

```python
# tests/integration/test_server_startup.py
"""Integration tests for server startup."""
import pytest
import asyncio
from unittest.mock import patch
import httpx


class TestServerStartup:
    """Integration tests for full server startup."""

    @pytest.fixture
    async def server(self):
        """Start server in background for testing."""
        import uvicorn
        from amelia.server.main import app

        config = uvicorn.Config(app, host="127.0.0.1", port=8421, log_level="warning")
        server = uvicorn.Server(config)

        # Run server in background task
        task = asyncio.create_task(server.serve())

        # Wait for server to be ready
        async with httpx.AsyncClient() as client:
            for _ in range(50):  # 5 second timeout
                try:
                    response = await client.get("http://127.0.0.1:8421/api/health/live")
                    if response.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)

        yield "http://127.0.0.1:8421"

        # Shutdown
        server.should_exit = True
        await task

    @pytest.mark.asyncio
    async def test_server_starts_and_responds(self, server):
        """Server starts and responds to health checks."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/health/live")

            assert response.status_code == 200
            assert response.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_metrics(self, server):
        """Health endpoint returns system metrics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ("healthy", "degraded")
            assert "memory_mb" in data
            assert "uptime_seconds" in data

    @pytest.mark.asyncio
    async def test_docs_endpoint_available(self, server):
        """Swagger docs are accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/docs")

            assert response.status_code == 200
            assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    @pytest.mark.asyncio
    async def test_openapi_schema_available(self, server):
        """OpenAPI schema is accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/openapi.json")

            assert response.status_code == 200
            schema = response.json()
            assert schema["info"]["title"] == "Amelia API"
```

**Step 2: Run integration test**

Run: `uv run pytest tests/integration/test_server_startup.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_server_startup.py
git commit -m "test(server): add integration tests for server startup"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `uv run pytest tests/unit/server/ -v` - All unit tests pass
- [ ] `uv run pytest tests/integration/test_server_startup.py -v` - Integration tests pass
- [ ] `uv run ruff check amelia/server` - No linting errors
- [ ] `uv run mypy amelia/server` - No type errors
- [ ] `uv run amelia server --help` - Shows help text
- [ ] `uv run amelia server` - Server starts on http://127.0.0.1:8420
- [ ] `curl http://127.0.0.1:8420/api/health` - Returns JSON health status
- [ ] `curl http://127.0.0.1:8420/api/docs` - Shows Swagger UI

---

## Summary

This plan creates the server foundation:

| Component | File | Purpose |
|-----------|------|---------|
| Dependencies | `pyproject.toml` | FastAPI, uvicorn, structlog, psutil |
| Config | `amelia/server/config.py` | Pydantic-settings configuration |
| App | `amelia/server/main.py` | FastAPI application factory |
| Health | `amelia/server/routes/health.py` | Liveness/readiness probes |
| CLI | `amelia/server/cli.py` | `amelia server` command |
| Logging | `amelia/server/logging.py` | Structured JSON logging |

**Next PR:** Database Foundation & Migrations (Plan 2)
