"""Test that Knowledge Library dependencies are available."""


def test_docling_available():
    """Docling should be importable."""
    import docling  # noqa: F401


def test_pgvector_available():
    """pgvector should be importable."""
    import pgvector  # noqa: F401
