"""Test Knowledge Library Pydantic models."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from amelia.knowledge.models import (
    Document,
    DocumentChunk,
    DocumentStatus,
    SearchResult,
    TagExtractionOutput,
)


def test_document_model_defaults() -> None:
    """Document model should have correct defaults."""
    doc_id = uuid4()
    doc = Document(
        id=doc_id,
        name="React Docs",
        filename="react-docs.pdf",
        content_type="application/pdf",
    )

    assert doc.id == doc_id
    assert doc.name == "React Docs"
    assert doc.status == DocumentStatus.PENDING
    assert doc.tags == []
    assert doc.chunk_count == 0
    assert doc.token_count == 0
    assert doc.error is None
    assert doc.raw_text is None


def test_document_chunk_model() -> None:
    """DocumentChunk model should validate correctly."""
    chunk_id = uuid4()
    chunk = DocumentChunk(
        id=chunk_id,
        document_id=uuid4(),
        chunk_index=0,
        content="# Introduction\n\nTest content here.",
        heading_path=["Introduction"],
        token_count=50,
        embedding=[0.1] * 1536,
    )

    assert chunk.id == chunk_id
    assert chunk.chunk_index == 0
    assert len(chunk.embedding) == 1536
    assert chunk.heading_path == ["Introduction"]


def test_search_result_model() -> None:
    """SearchResult model should include all required fields."""
    chunk_id = uuid4()
    result = SearchResult(
        chunk_id=chunk_id,
        document_id=uuid4(),
        document_name="React Docs",
        tags=["react", "frontend"],
        content="React is a library for building UIs",
        heading_path=["Introduction"],
        similarity=0.85,
        token_count=10,
    )

    assert result.similarity == 0.85
    assert result.tags == ["react", "frontend"]
    assert result.chunk_id == chunk_id


def test_tag_extraction_output_valid() -> None:
    """TagExtractionOutput should validate with valid tags list."""
    output = TagExtractionOutput(
        tags=["python", "async", "testing"],
        reasoning="Tags extracted based on code patterns and domain",
    )

    assert len(output.tags) == 3
    assert output.tags == ["python", "async", "testing"]
    assert output.reasoning == "Tags extracted based on code patterns and domain"


def test_tag_extraction_output_min_tags() -> None:
    """TagExtractionOutput should accept minimum 3 tags."""
    output = TagExtractionOutput(
        tags=["tag1", "tag2", "tag3"],
    )

    assert len(output.tags) == 3


def test_tag_extraction_output_max_tags() -> None:
    """TagExtractionOutput should accept maximum 15 tags."""
    tags = [f"tag{i}" for i in range(15)]
    output = TagExtractionOutput(tags=tags)

    assert len(output.tags) == 15


def test_tag_extraction_output_no_reasoning() -> None:
    """TagExtractionOutput should allow None reasoning."""
    output = TagExtractionOutput(
        tags=["python", "async", "testing", "pydantic"],
    )

    assert output.reasoning is None


def test_tag_extraction_output_too_few_tags() -> None:
    """TagExtractionOutput should reject fewer than 3 tags."""
    with pytest.raises(ValidationError) as exc_info:
        TagExtractionOutput(tags=["tag1", "tag2"])

    errors = exc_info.value.errors()
    assert any("at least 3 items" in str(error) for error in errors)


def test_tag_extraction_output_too_many_tags() -> None:
    """TagExtractionOutput should reject more than 15 tags."""
    tags = [f"tag{i}" for i in range(16)]

    with pytest.raises(ValidationError) as exc_info:
        TagExtractionOutput(tags=tags)

    errors = exc_info.value.errors()
    assert any("at most 15 items" in str(error) for error in errors)


def test_tag_extraction_output_empty_tags() -> None:
    """TagExtractionOutput should reject empty tags list."""
    with pytest.raises(ValidationError) as exc_info:
        TagExtractionOutput(tags=[])

    errors = exc_info.value.errors()
    assert any("at least 3 items" in str(error) for error in errors)
