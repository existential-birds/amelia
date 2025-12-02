"""Verify server dependencies are available."""


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
