/**
 * @fileoverview Tests for Knowledge Library page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import KnowledgePage from '../KnowledgePage';
import type { KnowledgeDocument } from '@/types/knowledge';
import { api } from '@/api/client';

// Mock React Router
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
    useRevalidator: () => ({ revalidate: vi.fn() }),
  };
});

// Mock API client
vi.mock('@/api/client', () => ({
  api: {
    searchKnowledge: vi.fn(),
    uploadKnowledgeDocument: vi.fn(),
    deleteKnowledgeDocument: vi.fn(),
  },
}));

// Mock Toast component
vi.mock('@/components/Toast', () => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}));

// Mock logger
vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

import { useLoaderData } from 'react-router-dom';
import * as Toast from '@/components/Toast';
import { logger } from '@/lib/logger';

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

  it('shows error state when search fails', async () => {
    const user = userEvent.setup();
    renderPage();

    // Mock search failure
    vi.mocked(api.searchKnowledge).mockRejectedValueOnce(new Error('Search service unavailable'));

    const searchInput = screen.getByPlaceholderText('Search documentation...');
    await user.type(searchInput, 'test query');
    await user.click(screen.getByRole('button', { name: /search/i }));

    expect(await screen.findByText('Search failed')).toBeInTheDocument();
    expect(await screen.findByText('Search service unavailable')).toBeInTheDocument();
  });

  it('shows toast when upload fails', async () => {
    const user = userEvent.setup();
    renderPage();

    // Mock upload failure
    vi.mocked(api.uploadKnowledgeDocument).mockRejectedValueOnce(new Error('File too large'));

    // Open upload dialog
    await user.click(screen.getByRole('button', { name: /upload/i }));

    // Create a test file
    const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
    const fileInput = screen.getByLabelText('File');
    await user.upload(fileInput, file);

    // Fill in name
    const nameInput = screen.getByLabelText('Name');
    await user.clear(nameInput);
    await user.type(nameInput, 'Test Document');

    // Submit - find the dialog's upload button
    const dialogButtons = screen.getAllByRole('button');
    const uploadButton = dialogButtons.find((btn) => btn.textContent === 'Upload');
    expect(uploadButton).toBeDefined();
    await user.click(uploadButton!);

    // Wait for async upload to complete and verify side effects occurred
    await vi.waitFor(() => {
      expect(Toast.error).toHaveBeenCalledWith('File too large');
    });
    expect(logger.error).toHaveBeenCalledWith('Upload failed', expect.any(Error));
  });

  it('shows toast when delete fails', async () => {
    const user = userEvent.setup();
    renderPage(mockDocuments);

    // Mock delete failure
    vi.mocked(api.deleteKnowledgeDocument).mockRejectedValueOnce(new Error('Permission denied'));

    // Switch to Documents tab
    await user.click(screen.getByRole('tab', { name: /documents/i }));

    // Click delete button
    const deleteButton = await screen.findByTestId('delete-document');
    await user.click(deleteButton);

    // Wait for async delete to complete and verify side effects occurred
    await vi.waitFor(() => {
      expect(Toast.error).toHaveBeenCalledWith('Permission denied');
    });
    expect(logger.error).toHaveBeenCalledWith('Delete failed', expect.any(Error));
  });
});
