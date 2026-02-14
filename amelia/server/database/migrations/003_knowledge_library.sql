-- 003_knowledge_library.sql
-- Knowledge Library schema: documents, chunks, vector search

CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: metadata and raw text storage
CREATE TABLE documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    tags         TEXT[] NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending',
    error        TEXT,
    chunk_count  INT NOT NULL DEFAULT 0,
    token_count  INT NOT NULL DEFAULT 0,
    raw_text     TEXT,
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Document chunks table: embedded vectors for semantic search
CREATE TABLE document_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    content      TEXT NOT NULL,
    heading_path TEXT[],
    token_count  INT NOT NULL,
    embedding    vector(1536),
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_documents_tags ON documents USING GIN(tags);
CREATE INDEX idx_documents_status ON documents(status);

-- Comments
COMMENT ON TABLE documents IS 'Uploaded documentation files with metadata';
COMMENT ON TABLE document_chunks IS 'Text chunks with embeddings for semantic search';
COMMENT ON COLUMN document_chunks.embedding IS 'OpenAI text-embedding-3-small (1536 dims)';
