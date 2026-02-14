"""Test Knowledge Library Pydantic models."""



from amelia.knowledge.models import Document, DocumentChunk, DocumentStatus, SearchResult


def test_document_model_defaults():
    """Document model should have correct defaults."""
    doc = Document(
        id="doc-123",
        name="React Docs",
        filename="react-docs.pdf",
        content_type="application/pdf",
    )

    assert doc.id == "doc-123"
    assert doc.name == "React Docs"
    assert doc.status == DocumentStatus.PENDING
    assert doc.tags == []
    assert doc.chunk_count == 0
    assert doc.token_count == 0
    assert doc.error is None
    assert doc.raw_text is None


def test_document_chunk_model():
    """DocumentChunk model should validate correctly."""
    chunk = DocumentChunk(
        id="chunk-123",
        document_id="doc-123",
        chunk_index=0,
        content="# Introduction\n\nTest content here.",
        heading_path=["Introduction"],
        token_count=50,
        embedding=[0.1] * 1536,
    )

    assert chunk.id == "chunk-123"
    assert chunk.chunk_index == 0
    assert len(chunk.embedding) == 1536
    assert chunk.heading_path == ["Introduction"]


def test_search_result_model():
    """SearchResult model should include all required fields."""
    result = SearchResult(
        chunk_id="chunk-123",
        document_id="doc-123",
        document_name="React Docs",
        tags=["react", "frontend"],
        content="React is a library for building UIs",
        heading_path=["Introduction"],
        similarity=0.85,
        token_count=10,
    )

    assert result.similarity == 0.85
    assert result.tags == ["react", "frontend"]
    assert result.chunk_id == "chunk-123"
