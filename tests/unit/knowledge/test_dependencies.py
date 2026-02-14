"""Test that Knowledge Library dependencies are available."""


def test_docling_available() -> None:
    """Docling should be importable."""
    import docling  # noqa: F401


def test_pgvector_available() -> None:
    """pgvector should be importable."""
    import pgvector  # type: ignore[import-untyped]  # noqa: F401
