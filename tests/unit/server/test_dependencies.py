"""Verify server dependencies are available."""


def test_fastapi_importable():
    """FastAPI should be importable."""
    import fastapi  # noqa: PLC0415

    assert fastapi.__version__


def test_pydantic_settings_importable():
    """Pydantic-settings should be importable."""
    import pydantic_settings  # noqa: PLC0415

    assert pydantic_settings.__version__


def test_uvicorn_importable():
    """Uvicorn should be importable."""
    import uvicorn  # noqa: PLC0415

    assert uvicorn


def test_psutil_importable():
    """Psutil should be importable."""
    import psutil  # noqa: PLC0415

    assert psutil
