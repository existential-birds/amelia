"""Integration tests for Knowledge Library repository.

These tests require PostgreSQL 17 with pg_vector extension.
Mark as integration to skip in unit test runs.
"""

import pytest

from amelia.knowledge.models import Document, DocumentChunk, DocumentStatus
from amelia.knowledge.repository import KnowledgeRepository
from amelia.server.database.connection import Database

pytestmark = pytest.mark.integration


@pytest.fixture
async def knowledge_repo(test_db: Database):
    """Provide Knowledge repository with test database."""
    repo = KnowledgeRepository(test_db)

    # Clean up test data
    await test_db.execute("DELETE FROM documents WHERE name LIKE 'Test%'")

    yield repo

    # Cleanup after test
    await test_db.execute("DELETE FROM documents WHERE name LIKE 'Test%'")


async def test_create_document(knowledge_repo):
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


async def test_get_document(knowledge_repo):
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


async def test_update_document_status(knowledge_repo):
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


async def test_list_documents(knowledge_repo):
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


async def test_delete_document(knowledge_repo):
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
