"""Knowledge Library API routes."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from loguru import logger
from pydantic import BaseModel

from amelia.knowledge.models import Document, SearchResult
from amelia.knowledge.repository import KnowledgeRepository
from amelia.knowledge.search import knowledge_search
from amelia.knowledge.service import KnowledgeService
from amelia.server.dependencies import get_knowledge_repository, get_knowledge_service


router = APIRouter(prefix="/knowledge", tags=["knowledge"])

ALLOWED_CONTENT_TYPES = {"application/pdf", "text/markdown"}
# Browsers often send these for .md files instead of text/markdown
_MARKDOWN_FALLBACK_TYPES = {"text/plain", "application/octet-stream"}
_MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}


class SearchRequest(BaseModel):
    """Semantic search request body.

    Attributes:
        query: Natural language search query.
        top_k: Maximum results (default 5).
        tags: Optional tags to filter documents.
    """

    query: str
    top_k: int = 5
    tags: list[str] | None = None


class DocumentListResponse(BaseModel):
    """Response for document list endpoint.

    Attributes:
        documents: List of documents.
    """

    documents: list[Document]


@router.post("/documents", response_model=Document)
async def upload_document(
    file: UploadFile = File(...),
    name: str = Form(...),
    tags: str = Form(""),
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> Document:
    """Upload a document for ingestion.

    Accepts PDF or Markdown files. Creates a document record and queues
    background ingestion (parsing, chunking, embedding).

    Args:
        file: Uploaded file (PDF or Markdown).
        name: User-provided document name.
        tags: Comma-separated tags for filtering.
        repository: Knowledge repository.
        service: Knowledge service for background ingestion.

    Returns:
        Created document with pending status.

    Raises:
        HTTPException: 400 if file type is unsupported.
    """
    content_type = file.content_type or "application/octet-stream"
    ext = Path(file.filename or "").suffix.lower()

    # Accept markdown files even when browser sends text/plain or octet-stream
    if content_type not in ALLOWED_CONTENT_TYPES:
        if content_type in _MARKDOWN_FALLBACK_TYPES and ext in _MARKDOWN_EXTENSIONS:
            content_type = "text/markdown"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {content_type}. Allowed: PDF, Markdown.",
            )

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    doc = await repository.create_document(
        name=name,
        filename=file.filename or "unknown",
        content_type=content_type,
        tags=tag_list,
    )

    # Save uploaded file to temp location for background ingestion
    suffix = Path(file.filename or "").suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    service.queue_ingestion(
        document_id=doc.id,
        file_path=tmp_path,
        content_type=content_type,
    )

    logger.info("Document uploaded", document_id=doc.id, name=name)
    return doc


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
) -> DocumentListResponse:
    """List all documents.

    Args:
        repository: Knowledge repository.

    Returns:
        All documents ordered by creation date (newest first).
    """
    documents = await repository.list_documents()
    return DocumentListResponse(documents=documents)


@router.get("/documents/{document_id}", response_model=Document)
async def get_document(
    document_id: str,
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
) -> Document:
    """Get document by ID.

    Args:
        document_id: Document UUID.
        repository: Knowledge repository.

    Returns:
        Document details.

    Raises:
        HTTPException: 404 if document not found.
    """
    doc = await repository.get_document(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    return doc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
) -> None:
    """Delete document and all associated chunks.

    Args:
        document_id: Document UUID.
        repository: Knowledge repository.

    Raises:
        HTTPException: 404 if document not found.
    """
    doc = await repository.get_document(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    await repository.delete_document(document_id)
    logger.info("Document deleted via API", document_id=document_id)


@router.post("/search", response_model=list[SearchResult])
async def search_documents(
    request: SearchRequest,
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> list[SearchResult]:
    """Semantic search across documents.

    Embeds the query and searches the vector index for matching chunks.

    Args:
        request: Search parameters (query, top_k, tags).
        repository: Knowledge repository.
        service: Knowledge service (provides embedding client).

    Returns:
        Ranked search results above similarity threshold.
    """
    results = await knowledge_search(
        query=request.query,
        embedding_client=service._pipeline.embedding_client,
        repository=repository,
        top_k=request.top_k,
        tags=request.tags,
    )
    return results
