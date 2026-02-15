/**
 * Knowledge Library types mirroring Python Pydantic models.
 */

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface KnowledgeDocument {
  id: string;
  name: string;
  filename: string;
  content_type: string;
  tags: string[];
  status: DocumentStatus;
  error: string | null;
  chunk_count: number;
  token_count: number;
  raw_text: string | null;
  metadata: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_name: string;
  tags: string[];
  content: string;
  heading_path: string[];
  similarity: number;
  token_count: number;
}

export interface KnowledgeDocumentListResponse {
  documents: KnowledgeDocument[];
}

// TODO: Add SSE endpoint for real-time ingestion progress tracking
export interface IngestionProgressEvent {
  document_id: string;
  stage: 'parsing' | 'chunking' | 'embedding' | 'storing';
  progress: number;
  chunks_processed: number;
  total_chunks: number;
}
