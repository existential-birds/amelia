"""Test that Knowledge Library dependencies are available."""


def test_docling_available() -> None:
    """Docling should be importable."""
    import docling  # noqa: F401


def test_pgvector_available() -> None:
    """pgvector should be importable."""
    import pgvector  # noqa: F401  # type: ignore[import-untyped]
