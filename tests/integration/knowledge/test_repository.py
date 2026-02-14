"""Integration tests for Knowledge Library repository.

These tests require PostgreSQL 17 with pg_vector extension.
Mark as integration to skip in unit test runs.
"""

from collections.abc import AsyncGenerator

import pytest

from amelia.knowledge.models import DocumentStatus
from amelia.knowledge.repository import KnowledgeRepository
from amelia.server.database.connection import Database


pytestmark = pytest.mark.integration


@pytest.fixture
async def knowledge_repo(test_db: Database) -> AsyncGenerator[KnowledgeRepository]:
    """Provide Knowledge repository with test database."""
    repo = KnowledgeRepository(test_db)

    # Clean up test data
    await test_db.execute("DELETE FROM documents WHERE name LIKE 'Test%'")

    yield repo

    # Cleanup after test
    await test_db.execute("DELETE FROM documents WHERE name LIKE 'Test%'")


async def test_create_document(knowledge_repo: KnowledgeRepository) -> None:
    """Should create document with pending status."""
    doc = await knowledge_repo.create_document(
        name="Test React Docs",
        filename="react.pdf",
        content_type="application/pdf",
        tags=["react", "frontend"],
    )

    assert doc.name == "Test React Docs"
    assert doc.status == DocumentStatus.PENDING
    assert doc.tags == ["react", "frontend"]
    assert doc.id is not None


async def test_get_document(knowledge_repo: KnowledgeRepository) -> None:
    """Should retrieve document by ID."""
    created = await knowledge_repo.create_document(
        name="Test Vue Docs",
        filename="vue.pdf",
        content_type="application/pdf",
    )

    retrieved = await knowledge_repo.get_document(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == "Test Vue Docs"


async def test_update_document_status(knowledge_repo: KnowledgeRepository) -> None:
    """Should update document status and error."""
    doc = await knowledge_repo.create_document(
        name="Test Failed Doc",
        filename="failed.pdf",
        content_type="application/pdf",
    )

    updated = await knowledge_repo.update_document_status(
        doc.id,
        status=DocumentStatus.FAILED,
        error="PDF is password-protected",
    )

    assert updated.status == DocumentStatus.FAILED
    assert updated.error == "PDF is password-protected"


async def test_list_documents(knowledge_repo: KnowledgeRepository) -> None:
    """Should list all documents."""
    await knowledge_repo.create_document(
        name="Test Doc 1",
        filename="doc1.pdf",
        content_type="application/pdf",
    )
    await knowledge_repo.create_document(
        name="Test Doc 2",
        filename="doc2.md",
        content_type="text/markdown",
    )

    docs = await knowledge_repo.list_documents()

    test_docs = [d for d in docs if d.name.startswith("Test")]
    assert len(test_docs) >= 2


async def test_delete_document(knowledge_repo: KnowledgeRepository) -> None:
    """Should delete document and cascade chunks."""
    doc = await knowledge_repo.create_document(
        name="Test Delete Doc",
        filename="delete.pdf",
        content_type="application/pdf",
    )

    # Insert a chunk
    await knowledge_repo.insert_chunks(
        doc.id,
        [
            {
                "chunk_index": 0,
                "content": "Test content",
                "heading_path": [],
                "token_count": 5,
                "embedding": [0.1] * 1536,
                "metadata": {},
            }
        ],
    )

    # Delete document
    await knowledge_repo.delete_document(doc.id)

    # Verify deletion
    retrieved = await knowledge_repo.get_document(doc.id)
    assert retrieved is None


async def test_search_chunks(knowledge_repo: KnowledgeRepository) -> None:
    """Should search chunks by embedding similarity."""
    # Create document
    doc = await knowledge_repo.create_document(
        name="Test Search Doc",
        filename="search.pdf",
        content_type="application/pdf",
        tags=["python", "testing"],
    )

    # Insert chunks with distinct embeddings
    # Chunk 0: high values in first half
    # Chunk 1: high values in second half
    embedding_a = [0.9] * 768 + [0.1] * 768
    embedding_b = [0.1] * 768 + [0.9] * 768

    await knowledge_repo.insert_chunks(
        doc.id,
        [
            {
                "chunk_index": 0,
                "content": "Python testing basics",
                "heading_path": ["Chapter 1", "Testing"],
                "token_count": 10,
                "embedding": embedding_a,
                "metadata": {},
            },
            {
                "chunk_index": 1,
                "content": "Advanced pytest features",
                "heading_path": ["Chapter 2", "Pytest"],
                "token_count": 15,
                "embedding": embedding_b,
                "metadata": {},
            },
        ],
    )

    # Set document to ready status
    await knowledge_repo.update_document_status(
        doc.id, status=DocumentStatus.READY, chunk_count=2, token_count=25
    )

    # Search with query similar to embedding_a
    query_embedding = [0.85] * 768 + [0.15] * 768
    results = await knowledge_repo.search_chunks(
        query_embedding=query_embedding,
        top_k=5,
        similarity_threshold=0.5,
    )

    # Should find chunks, with chunk 0 ranked higher
    test_results = [r for r in results if r.document_name == "Test Search Doc"]
    assert len(test_results) >= 1
    assert test_results[0].content == "Python testing basics"
    assert test_results[0].heading_path == ["Chapter 1", "Testing"]
    assert test_results[0].similarity > 0.5


async def test_search_chunks_with_tag_filter(knowledge_repo: KnowledgeRepository) -> None:
    """Should filter search results by document tags."""
    # Create two documents with different tags
    doc_python = await knowledge_repo.create_document(
        name="Test Python Doc",
        filename="python.pdf",
        content_type="application/pdf",
        tags=["python"],
    )
    doc_rust = await knowledge_repo.create_document(
        name="Test Rust Doc",
        filename="rust.pdf",
        content_type="application/pdf",
        tags=["rust"],
    )

    # Same embedding for both chunks
    embedding = [0.5] * 1536

    await knowledge_repo.insert_chunks(
        doc_python.id,
        [
            {
                "chunk_index": 0,
                "content": "Python content",
                "heading_path": [],
                "token_count": 5,
                "embedding": embedding,
                "metadata": {},
            }
        ],
    )
    await knowledge_repo.insert_chunks(
        doc_rust.id,
        [
            {
                "chunk_index": 0,
                "content": "Rust content",
                "heading_path": [],
                "token_count": 5,
                "embedding": embedding,
                "metadata": {},
            }
        ],
    )

    # Set both documents to ready
    await knowledge_repo.update_document_status(
        doc_python.id, status=DocumentStatus.READY, chunk_count=1, token_count=5
    )
    await knowledge_repo.update_document_status(
        doc_rust.id, status=DocumentStatus.READY, chunk_count=1, token_count=5
    )

    # Search with tag filter for python only
    results = await knowledge_repo.search_chunks(
        query_embedding=embedding,
        top_k=10,
        tags=["python"],
        similarity_threshold=0.5,
    )

    # Should only find python document
    test_results = [r for r in results if r.document_name.startswith("Test")]
    assert len(test_results) == 1
    assert test_results[0].content == "Python content"
    assert "python" in test_results[0].tags
