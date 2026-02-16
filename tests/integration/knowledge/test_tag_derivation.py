"""Integration tests for tag derivation in ingestion pipeline.

These tests verify the full tag derivation pipeline end-to-end with real
components (repository, pipeline, database) and only mock external boundaries
(LLM API and embedding client).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from amelia.knowledge.embeddings import EmbeddingClient
from amelia.knowledge.ingestion import IngestionPipeline
from amelia.knowledge.models import DocumentStatus, TagExtractionOutput
from amelia.knowledge.repository import KnowledgeRepository
from amelia.server.database.connection import Database

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_tag_derivation_end_to_end(
    test_db: Database,
    tmp_path: Path,
) -> None:
    """Should derive tags and store them during real ingestion."""
    # Create real repository
    repo = KnowledgeRepository(test_db)

    # Create document
    doc = await repo.create_document(
        name="Kubernetes Guide",
        filename="k8s-guide.md",
        content_type="text/markdown",
    )

    # Create test markdown file
    test_file = tmp_path / "k8s-guide.md"
    test_file.write_text("""
# Kubernetes Deployment Guide

## Introduction
This guide covers deploying applications to Kubernetes clusters.

## Prerequisites
- Docker installed
- kubectl configured

## Deployment Steps
1. Create a deployment YAML
2. Apply the configuration
""")

    # Mock embedding client
    mock_embedding = AsyncMock(spec=EmbeddingClient)
    mock_embedding.embed_batch.return_value = [[0.1] * 1536] * 3  # 3 chunks

    # Create pipeline with tag derivation enabled
    pipeline = IngestionPipeline(
        repository=repo,
        embedding_client=mock_embedding,
        tag_derivation_model="openai/gpt-oss-120b",
        tag_derivation_driver="api",
    )

    # Mock only the LLM call for tag extraction
    with patch("amelia.knowledge.ingestion.extract_structured") as mock_extract:
        mock_extract.return_value = TagExtractionOutput(
            tags=["kubernetes", "deployment", "docker", "containers", "kubectl"],
            reasoning="Document is a technical guide for deploying to Kubernetes",
        )

        # Run full ingestion
        result = await pipeline.ingest_document(
            document_id=doc.id,
            file_path=test_file,
            content_type="text/markdown",
        )

    # Verify document has derived tags
    assert result.status == DocumentStatus.READY
    assert len(result.tags) == 5
    assert "kubernetes" in result.tags
    assert "deployment" in result.tags
    assert "docker" in result.tags
    assert "containers" in result.tags
    assert "kubectl" in result.tags

    # Verify tags are persisted in database
    retrieved = await repo.get_document(doc.id)
    assert retrieved is not None
    assert retrieved.tags == result.tags
    assert "kubernetes" in retrieved.tags


@pytest.mark.asyncio
async def test_tag_derivation_disabled(
    test_db: Database,
    tmp_path: Path,
) -> None:
    """Should not derive tags when tag_derivation_model is None."""
    # Create real repository
    repo = KnowledgeRepository(test_db)

    # Create document with initial tags
    doc = await repo.create_document(
        name="Python Guide",
        filename="python.md",
        content_type="text/markdown",
        tags=["python", "programming"],
    )

    # Create test markdown file
    test_file = tmp_path / "python.md"
    test_file.write_text("""
# Python Programming Guide

## Introduction
Learn Python basics.
""")

    # Mock embedding client
    mock_embedding = AsyncMock(spec=EmbeddingClient)
    mock_embedding.embed_batch.return_value = [[0.1] * 1536] * 2

    # Create pipeline with tag derivation DISABLED
    pipeline = IngestionPipeline(
        repository=repo,
        embedding_client=mock_embedding,
        tag_derivation_model=None,  # Disabled
        tag_derivation_driver="api",
    )

    # Run ingestion - should not call extract_structured
    with patch("amelia.knowledge.ingestion.extract_structured") as mock_extract:
        result = await pipeline.ingest_document(
            document_id=doc.id,
            file_path=test_file,
            content_type="text/markdown",
        )

        # Verify extract_structured was never called
        mock_extract.assert_not_called()

    # Verify only original tags remain (no derived tags added)
    assert result.status == DocumentStatus.READY
    assert result.tags == ["python", "programming"]

    # Verify in database
    retrieved = await repo.get_document(doc.id)
    assert retrieved is not None
    assert retrieved.tags == ["python", "programming"]


@pytest.mark.asyncio
async def test_tag_derivation_failure_non_blocking(
    test_db: Database,
    tmp_path: Path,
) -> None:
    """Should continue ingestion even if tag derivation fails."""
    # Create real repository
    repo = KnowledgeRepository(test_db)

    # Create document
    doc = await repo.create_document(
        name="React Guide",
        filename="react.md",
        content_type="text/markdown",
    )

    # Create test markdown file
    test_file = tmp_path / "react.md"
    test_file.write_text("""
# React Component Guide

## Introduction
Learn React components.
""")

    # Mock embedding client
    mock_embedding = AsyncMock(spec=EmbeddingClient)
    mock_embedding.embed_batch.return_value = [[0.1] * 1536] * 2

    # Create pipeline with tag derivation enabled
    pipeline = IngestionPipeline(
        repository=repo,
        embedding_client=mock_embedding,
        tag_derivation_model="openai/gpt-oss-120b",
        tag_derivation_driver="api",
    )

    # Mock extract_structured to raise an exception
    with patch("amelia.knowledge.ingestion.extract_structured") as mock_extract:
        mock_extract.side_effect = Exception("LLM API error")

        # Run ingestion - should complete despite tag derivation failure
        result = await pipeline.ingest_document(
            document_id=doc.id,
            file_path=test_file,
            content_type="text/markdown",
        )

    # Verify ingestion succeeded with no tags
    assert result.status == DocumentStatus.READY
    assert result.tags == []
    assert result.chunk_count > 0

    # Verify in database
    retrieved = await repo.get_document(doc.id)
    assert retrieved is not None
    assert retrieved.status == DocumentStatus.READY
    assert retrieved.tags == []


@pytest.mark.asyncio
async def test_tag_derivation_merges_with_existing_tags(
    test_db: Database,
    tmp_path: Path,
) -> None:
    """Should merge derived tags with existing user-provided tags."""
    # Create real repository
    repo = KnowledgeRepository(test_db)

    # Create document with initial user-provided tags
    doc = await repo.create_document(
        name="AWS Lambda Guide",
        filename="lambda.md",
        content_type="text/markdown",
        tags=["aws", "serverless"],  # User-provided tags
    )

    # Create test markdown file
    test_file = tmp_path / "lambda.md"
    test_file.write_text("""
# AWS Lambda Deployment Guide

## Introduction
Deploy serverless functions to AWS Lambda using Python.

## Prerequisites
- AWS account
- Python 3.12
""")

    # Mock embedding client
    mock_embedding = AsyncMock(spec=EmbeddingClient)
    mock_embedding.embed_batch.return_value = [[0.1] * 1536] * 3

    # Create pipeline with tag derivation enabled
    pipeline = IngestionPipeline(
        repository=repo,
        embedding_client=mock_embedding,
        tag_derivation_model="openai/gpt-oss-120b",
        tag_derivation_driver="api",
    )

    # Mock LLM to derive additional tags
    with patch("amelia.knowledge.ingestion.extract_structured") as mock_extract:
        mock_extract.return_value = TagExtractionOutput(
            tags=["lambda", "python", "deployment", "cloud", "functions"],
            reasoning="Guide covers Lambda deployment with Python",
        )

        # Run ingestion
        result = await pipeline.ingest_document(
            document_id=doc.id,
            file_path=test_file,
            content_type="text/markdown",
        )

    # Verify derived tags are added (total should include both user and derived)
    assert result.status == DocumentStatus.READY
    assert len(result.tags) > 2  # More than just the 2 user tags

    # Verify both user tags and derived tags are present
    assert "aws" in result.tags  # User-provided
    assert "serverless" in result.tags  # User-provided
    assert "lambda" in result.tags  # Derived
    assert "python" in result.tags  # Derived

    # Verify in database
    retrieved = await repo.get_document(doc.id)
    assert retrieved is not None
    assert "aws" in retrieved.tags
    assert "serverless" in retrieved.tags
    assert "lambda" in retrieved.tags
