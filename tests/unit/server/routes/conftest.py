"""Shared fixtures and helpers for route unit tests."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI

from amelia.server.database.settings_repository import ServerSettings


_DEFAULT_TIMESTAMP = datetime(2024, 1, 1, 12, 0, 0)


def _make_server_settings(**overrides: object) -> ServerSettings:
    """Build ServerSettings with sensible defaults, overridable per-field."""
    defaults = dict(
        log_retention_days=30,
        checkpoint_retention_days=0,
        websocket_idle_timeout_seconds=300.0,
        workflow_start_timeout_seconds=60.0,
        max_concurrent=5,
        pr_polling_enabled=False,
        created_at=_DEFAULT_TIMESTAMP,
        updated_at=_DEFAULT_TIMESTAMP,
    )
    return ServerSettings(**{**defaults, **overrides})  # type: ignore[arg-type]


@asynccontextmanager
async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
    """No-op lifespan context manager for test FastAPI apps."""
    yield


def patch_lifespan(app: FastAPI) -> FastAPI:
    """Disable the real lifespan on a FastAPI app for unit testing."""
    app.router.lifespan_context = noop_lifespan
    return app
