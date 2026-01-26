"""Shared fixtures and helpers for route unit tests."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI


@asynccontextmanager
async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
    """No-op lifespan context manager for test FastAPI apps."""
    yield


def patch_lifespan(app: FastAPI) -> FastAPI:
    """Disable the real lifespan on a FastAPI app for unit testing."""
    app.router.lifespan_context = noop_lifespan
    return app
