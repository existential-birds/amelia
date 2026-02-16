# Sample Knowledge Document

This is a sample document for testing the Knowledge Library feature.

## Getting Started

The knowledge library allows you to upload and search documentation using semantic search.
Documents are parsed into chunks and embedded with vector representations for similarity matching.

## Key Concepts

### Document Ingestion

When a document is uploaded, it goes through a pipeline:
1. **Parsing** - Extract text content from PDF or Markdown files
2. **Chunking** - Split content into meaningful sections based on headings
3. **Embedding** - Generate vector representations using an embedding model
4. **Indexing** - Store vectors in pgvector for fast similarity search

### Semantic Search

Semantic search finds relevant content by comparing the meaning of your query
against all indexed chunks, returning the most similar results ranked by score.

## Configuration

The knowledge library uses pgvector for vector storage and supports
filtering results by document tags for more targeted searches.
