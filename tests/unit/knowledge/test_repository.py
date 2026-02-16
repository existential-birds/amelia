"""Unit tests for Knowledge Library repository."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from amelia.knowledge.models import Document
from amelia.knowledge.repository import KnowledgeRepository


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Database instance."""
    db = MagicMock()
    db.fetch_one = AsyncMock()
    db.fetch_all = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def knowledge_repo(mock_db: MagicMock) -> KnowledgeRepository:
    """Create KnowledgeRepository with mock database."""
    return KnowledgeRepository(mock_db)


class TestUpdateDocumentTags:
    """Tests for update_document_tags method."""

    async def test_update_document_tags(
        self, knowledge_repo: KnowledgeRepository, mock_db: MagicMock
    ) -> None:
        """Should update document tags and return updated document."""
        # Arrange
        document_id = "doc-123"
        new_tags = ["python", "testing", "pytest"]

        # Mock database row return (asyncpg.Record)
        mock_row = {
            "id": document_id,
            "name": "Test Document",
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "tags": new_tags,
            "status": "ready",
            "error": None,
            "chunk_count": 10,
            "token_count": 1000,
            "raw_text": "Sample text content",
            "metadata": {},
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-02T00:00:00",
        }
        mock_db.fetch_one.return_value = mock_row

        # Act
        result = await knowledge_repo.update_document_tags(document_id, new_tags)

        # Assert
        mock_db.fetch_one.assert_called_once()
        call_args = mock_db.fetch_one.call_args
        assert "UPDATE documents" in call_args[0][0]
        assert "SET tags = $2" in call_args[0][0]
        assert "updated_at = NOW()" in call_args[0][0]
        assert "WHERE id = $1" in call_args[0][0]
        assert call_args[0][1] == document_id
        assert call_args[0][2] == new_tags

        # Verify returned document
        assert isinstance(result, Document)
        assert result.id == document_id
        assert result.tags == new_tags
        assert result.name == "Test Document"

    async def test_update_document_tags_not_found(
        self, knowledge_repo: KnowledgeRepository, mock_db: MagicMock
    ) -> None:
        """Should raise ValueError when document not found."""
        # Arrange
        document_id = "nonexistent-doc"
        new_tags = ["tag1", "tag2"]
        mock_db.fetch_one.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match=f"Document not found: {document_id}"):
            await knowledge_repo.update_document_tags(document_id, new_tags)

    async def test_update_document_tags_empty_list(
        self, knowledge_repo: KnowledgeRepository, mock_db: MagicMock
    ) -> None:
        """Should handle empty tag list (clear all tags)."""
        # Arrange
        document_id = uuid4()
        new_tags = []

        mock_row = {
            "id": document_id,
            "name": "Document With No Tags",
            "filename": "no_tags.md",
            "content_type": "text/markdown",
            "tags": new_tags,
            "status": "ready",
            "error": None,
            "chunk_count": 5,
            "token_count": 500,
            "raw_text": "Content",
            "metadata": {},
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-02T00:00:00",
        }
        mock_db.fetch_one.return_value = mock_row

        # Act
        result = await knowledge_repo.update_document_tags(document_id, new_tags)

        # Assert
        assert result.tags == []
        mock_db.fetch_one.assert_called_once()
