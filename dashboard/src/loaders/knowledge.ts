/**
 * @fileoverview Loader for the Knowledge Library page.
 */
import { api } from '@/api/client';
import type { KnowledgeDocument } from '@/types/knowledge';

/**
 * Loader data type for KnowledgePage.
 */
export interface KnowledgeLoaderData {
  /** All knowledge documents. */
  documents: KnowledgeDocument[];
}

/**
 * Loader for the Knowledge Library page.
 * Fetches all documents on navigation.
 *
 * @returns KnowledgeLoaderData with documents.
 */
export async function knowledgeLoader(): Promise<KnowledgeLoaderData> {
  const documents = await api.getKnowledgeDocuments();
  return { documents };
}
