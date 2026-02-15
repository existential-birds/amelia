/**
 * @fileoverview Tests for Knowledge Library page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import KnowledgePage from '../KnowledgePage';
import type { KnowledgeDocument } from '@/types/knowledge';

// Mock React Router
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
    useRevalidator: () => ({ revalidate: vi.fn() }),
  };
});

import { useLoaderData } from 'react-router-dom';

const mockDocuments: KnowledgeDocument[] = [
  {
    id: 'doc-1',
    name: 'React Docs',
    filename: 'react.pdf',
    content_type: 'application/pdf',
    tags: ['react', 'frontend'],
    status: 'ready',
    error: null,
    chunk_count: 42,
    token_count: 8500,
    raw_text: null,
    metadata: {},
    created_at: '2026-02-15T00:00:00Z',
    updated_at: '2026-02-15T00:00:00Z',
  },
];

beforeEach(() => {
  vi.resetAllMocks();
});

function renderPage(documents: KnowledgeDocument[] = []) {
  vi.mocked(useLoaderData).mockReturnValue({ documents });
  return render(
    <MemoryRouter>
      <KnowledgePage />
    </MemoryRouter>
  );
}

describe('KnowledgePage', () => {
  it('renders page header', () => {
    renderPage();
    expect(screen.getByText('Library')).toBeInTheDocument();
    expect(screen.getByText('KNOWLEDGE')).toBeInTheDocument();
  });

  it('shows search empty state by default', () => {
    renderPage();
    expect(screen.getByText('Search your knowledge library')).toBeInTheDocument();
  });

  it('shows document count in header', () => {
    renderPage(mockDocuments);
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('renders search and documents tabs', () => {
    renderPage();
    expect(screen.getByRole('tab', { name: /search/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /documents/i })).toBeInTheDocument();
  });

  it('shows documents in Documents tab', async () => {
    const user = userEvent.setup();
    renderPage(mockDocuments);
    await user.click(screen.getByRole('tab', { name: /documents/i }));
    expect(await screen.findByText('React Docs')).toBeInTheDocument();
  });

  it('shows empty state in Documents tab when no documents', async () => {
    const user = userEvent.setup();
    renderPage([]);
    await user.click(screen.getByRole('tab', { name: /documents/i }));
    expect(await screen.findByText('No documents')).toBeInTheDocument();
  });
});
