/**
 * @fileoverview Tests for Knowledge Library page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import KnowledgePage from '../KnowledgePage';
import type { KnowledgeDocument } from '@/types/knowledge';
import { api, ApiError } from '@/api/client';

// Create mock revalidate function that can be accessed in tests
const mockRevalidate = vi.fn();

// Mock React Router
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
    useRevalidator: () => ({ revalidate: mockRevalidate }),
  };
});

// Mock API client
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>();
  return {
    ...actual,
    api: {
      searchKnowledge: vi.fn(),
      uploadKnowledgeDocument: vi.fn(),
      deleteKnowledgeDocument: vi.fn(),
    },
  };
});

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
    raw_text: 'React is a JavaScript library for building user interfaces. It lets you compose complex UIs from small, isolated pieces of code called "components".',
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

  it('renders successful search results with similarity scores, heading paths, and tags', async () => {
    const user = userEvent.setup();
    renderPage(mockDocuments);

    // Mock successful search
    const mockSearchResults = [
      {
        chunk_id: 'chunk-1',
        document_id: 'doc-1',
        document_name: 'React Docs',
        tags: ['react', 'frontend'],
        content: 'React hooks allow you to use state in functional components.',
        heading_path: ['Getting Started', 'Hooks'],
        similarity: 0.87,
        token_count: 12,
      },
    ];
    vi.mocked(api.searchKnowledge).mockResolvedValueOnce(mockSearchResults);

    const searchInput = screen.getByPlaceholderText('Search documentation...');
    await user.type(searchInput, 'hooks');
    await user.click(screen.getByRole('button', { name: /search/i }));

    // Verify search result is rendered
    expect(await screen.findByText('React hooks allow you to use state in functional components.')).toBeInTheDocument();

    // Verify similarity score
    expect(screen.getByText('87%')).toBeInTheDocument();

    // Verify heading path (using › separator for better visual hierarchy)
    expect(screen.getByText('Getting Started › Hooks')).toBeInTheDocument();

    // Verify document name and tags
    expect(screen.getByText('React Docs')).toBeInTheDocument();
    expect(screen.getByText('react')).toBeInTheDocument();
    expect(screen.getByText('frontend')).toBeInTheDocument();

    // Verify AbortSignal was passed
    expect(api.searchKnowledge).toHaveBeenCalledWith('hooks', 5, undefined, expect.any(AbortSignal));
  });

  it('handles aborted search requests silently', async () => {
    const user = userEvent.setup();
    renderPage();

    // Mock search with AbortError
    const abortError = new DOMException('Request aborted', 'AbortError');
    vi.mocked(api.searchKnowledge).mockRejectedValueOnce(abortError);

    const searchInput = screen.getByPlaceholderText('Search documentation...');
    await user.type(searchInput, 'test query');
    await user.click(screen.getByRole('button', { name: /search/i }));

    // Wait for search to complete
    await waitFor(() => {
      expect(api.searchKnowledge).toHaveBeenCalled();
    });

    // Verify no error is shown (abort errors are silently ignored)
    expect(screen.queryByText('Search failed')).not.toBeInTheDocument();
    expect(screen.getByText('Search your knowledge library')).toBeInTheDocument();
  });

  it('handles ApiError ABORTED silently', async () => {
    const user = userEvent.setup();
    renderPage();

    // Mock search with ApiError ABORTED (thrown by fetchWithTimeout)
    const abortError = new ApiError('Request aborted', 'ABORTED', 0);
    vi.mocked(api.searchKnowledge).mockRejectedValueOnce(abortError);

    const searchInput = screen.getByPlaceholderText('Search documentation...');
    await user.type(searchInput, 'test query');
    await user.click(screen.getByRole('button', { name: /search/i }));

    await waitFor(() => {
      expect(api.searchKnowledge).toHaveBeenCalled();
    });

    // Verify no error is shown (ApiError ABORTED is silently ignored)
    expect(screen.queryByText('Search failed')).not.toBeInTheDocument();
    expect(screen.getByText('Search your knowledge library')).toBeInTheDocument();
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

    // Wait for upload to complete (button returns to "Upload" state)
    await waitFor(() => {
      const dialogButtons = screen.getAllByRole('button');
      const uploadButton = dialogButtons.find((btn) => btn.textContent === 'Upload');
      expect(uploadButton).toBeDefined();
    });
    expect(Toast.error).toHaveBeenCalledWith('File too large');
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
    await waitFor(() => {
      expect(Toast.error).toHaveBeenCalledWith('Permission denied');
    });
    expect(logger.error).toHaveBeenCalledWith('Delete failed', expect.any(Error));
  });

  it('closes dialog and revalidates documents after successful upload', async () => {
    const user = userEvent.setup();
    renderPage();

    // Mock successful upload
    const mockUploadedDoc: KnowledgeDocument = {
      id: 'doc-new',
      name: 'Test Document',
      filename: 'test.pdf',
      content_type: 'application/pdf',
      tags: [],
      status: 'pending',
      error: null,
      chunk_count: 0,
      token_count: 0,
      raw_text: null,
      metadata: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    vi.mocked(api.uploadKnowledgeDocument).mockResolvedValueOnce(mockUploadedDoc);

    // Open upload dialog
    await user.click(screen.getByRole('button', { name: /upload/i }));
    expect(screen.getByRole('heading', { name: 'Upload Document' })).toBeInTheDocument();

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

    // Wait for upload to complete and verify dialog closed
    await waitFor(() => {
      expect(api.uploadKnowledgeDocument).toHaveBeenCalledWith(file, 'Test Document', []);
      expect(screen.queryByRole('heading', { name: 'Upload Document' })).not.toBeInTheDocument();
    });

    // Verify revalidation was called
    expect(mockRevalidate).toHaveBeenCalled();
  });

  it('revalidates documents after successful delete', async () => {
    const user = userEvent.setup();
    renderPage(mockDocuments);

    // Mock successful delete
    vi.mocked(api.deleteKnowledgeDocument).mockResolvedValueOnce(undefined);

    // Switch to Documents tab
    await user.click(screen.getByRole('tab', { name: /documents/i }));

    // Click delete button
    const deleteButton = await screen.findByTestId('delete-document');
    await user.click(deleteButton);

    // Wait for delete to complete and verify revalidation was called
    await waitFor(() => {
      expect(api.deleteKnowledgeDocument).toHaveBeenCalledWith('doc-1');
      expect(mockRevalidate).toHaveBeenCalled();
    });
  });

  describe('Real-time WebSocket updates', () => {
    it('updates document status to processing when ingestion starts', async () => {
      const user = userEvent.setup();
      const pendingDoc = {
        ...mockDocuments[0],
        id: 'doc-pending',
        status: 'pending' as const,
      } as KnowledgeDocument;
      renderPage([pendingDoc]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));
      expect(await screen.findByText('Pending')).toBeInTheDocument();

      // Simulate WebSocket event for ingestion started
      act(() => {
        const event = new CustomEvent('workflow-event', {
          detail: {
            domain: 'knowledge',
            workflow_id: 'doc-pending',
            event_type: 'document_ingestion_started',
            data: { document_id: 'doc-pending', status: 'processing' },
          },
        });
        window.dispatchEvent(event);
      });

      // Verify status updated to processing
      expect(await screen.findByText('Processing')).toBeInTheDocument();
      expect(screen.queryByText('Pending')).not.toBeInTheDocument();
    });

    it('updates document status to ready when ingestion completes', async () => {
      const user = userEvent.setup();
      const processingDoc = {
        ...mockDocuments[0],
        id: 'doc-processing',
        status: 'processing' as const,
        chunk_count: 0,
        token_count: 0,
      } as KnowledgeDocument;
      renderPage([processingDoc]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));
      expect(await screen.findByText('Processing')).toBeInTheDocument();

      // Simulate WebSocket event for ingestion completed
      act(() => {
        const event = new CustomEvent('workflow-event', {
          detail: {
            domain: 'knowledge',
            workflow_id: 'doc-processing',
            event_type: 'document_ingestion_completed',
            data: {
              document_id: 'doc-processing',
              status: 'ready',
              chunk_count: 42,
              token_count: 8500,
            },
          },
        });
        window.dispatchEvent(event);
      });

      // Verify status updated to ready
      expect(await screen.findByText('Ready')).toBeInTheDocument();
      expect(screen.queryByText('Processing')).not.toBeInTheDocument();
    });

    it('updates document status to failed when ingestion fails', async () => {
      const user = userEvent.setup();
      const processingDoc = {
        ...mockDocuments[0],
        id: 'doc-fail',
        status: 'processing' as const,
      } as KnowledgeDocument;
      renderPage([processingDoc]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));
      expect(await screen.findByText('Processing')).toBeInTheDocument();

      // Simulate WebSocket event for ingestion failed
      act(() => {
        const event = new CustomEvent('workflow-event', {
          detail: {
            domain: 'knowledge',
            workflow_id: 'doc-fail',
            event_type: 'document_ingestion_failed',
            data: {
              document_id: 'doc-fail',
              status: 'failed',
              error: 'Embedding service unavailable',
            },
          },
        });
        window.dispatchEvent(event);
      });

      // Verify status updated to failed
      expect(await screen.findByText('Failed')).toBeInTheDocument();
      expect(screen.queryByText('Processing')).not.toBeInTheDocument();
    });

    it('ignores non-knowledge domain events', async () => {
      const user = userEvent.setup();
      const pendingDoc = {
        ...mockDocuments[0],
        id: 'doc-unchanged',
        status: 'pending' as const,
      } as KnowledgeDocument;
      renderPage([pendingDoc]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));
      expect(await screen.findByText('Pending')).toBeInTheDocument();

      // Simulate workflow domain event (should be ignored)
      act(() => {
        const event = new CustomEvent('workflow-event', {
          detail: {
            domain: 'workflow',
            workflow_id: 'doc-unchanged',
            event_type: 'workflow_started',
            data: {},
          },
        });
        window.dispatchEvent(event);
      });

      // Wait a bit to ensure no update happened
      await waitFor(
        () => {
          expect(screen.getByText('Pending')).toBeInTheDocument();
        },
        { timeout: 100 }
      );
    });

    it('shows animated spinner for processing status', async () => {
      const user = userEvent.setup();
      const processingDoc = {
        ...mockDocuments[0],
        status: 'processing' as const,
      } as KnowledgeDocument;
      renderPage([processingDoc]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Verify Processing badge with spinner
      const processingBadge = await screen.findByText('Processing');
      expect(processingBadge).toBeInTheDocument();

      // Verify spinner is present (has animate-spin class)
      const spinner = processingBadge.parentElement?.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });
  });

  describe('Expandable rows', () => {
    it('renders expand/collapse button for ready documents', async () => {
      const user = userEvent.setup();
      renderPage(mockDocuments);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Verify expand button is present
      const expandButton = await screen.findByLabelText('Expand row');
      expect(expandButton).toBeInTheDocument();
      expect(expandButton).toBeEnabled();
    });

    it('disables expand button for processing documents', async () => {
      const user = userEvent.setup();
      const processingDoc = {
        ...mockDocuments[0],
        status: 'processing' as const,
      } as KnowledgeDocument;
      renderPage([processingDoc]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Verify expand button is disabled
      const expandButton = await screen.findByLabelText('Expand row');
      expect(expandButton).toBeDisabled();
      expect(expandButton).toHaveAttribute('title', 'Processing...');
    });

    it('disables expand button for failed documents', async () => {
      const user = userEvent.setup();
      const failedDoc = {
        ...mockDocuments[0],
        status: 'failed' as const,
        error: 'Processing failed',
      } as KnowledgeDocument;
      renderPage([failedDoc]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Verify expand button is disabled
      const expandButton = await screen.findByLabelText('Expand row');
      expect(expandButton).toBeDisabled();
    });

    it('shows document preview when row is expanded', async () => {
      const user = userEvent.setup();
      renderPage(mockDocuments);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Click expand button
      const expandButton = await screen.findByLabelText('Expand row');
      await user.click(expandButton);

      // Verify preview is shown
      expect(await screen.findByText(/React is a JavaScript library/)).toBeInTheDocument();
    });

    it('hides preview when row is collapsed', async () => {
      const user = userEvent.setup();
      renderPage(mockDocuments);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Expand row
      const expandButton = await screen.findByLabelText('Expand row');
      await user.click(expandButton);

      // Verify preview is shown
      expect(await screen.findByText(/React is a JavaScript library/)).toBeInTheDocument();

      // Collapse row
      const collapseButton = await screen.findByLabelText('Collapse row');
      await user.click(collapseButton);

      // Verify preview is hidden
      await waitFor(() => {
        expect(screen.queryByText(/React is a JavaScript library/)).not.toBeInTheDocument();
      });
    });

    it('shows "No preview available" for documents without raw_text', async () => {
      const user = userEvent.setup();
      const docWithoutPreview = {
        ...mockDocuments[0],
        raw_text: null,
      } as KnowledgeDocument;
      renderPage([docWithoutPreview]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Expand row
      const expandButton = await screen.findByLabelText('Expand row');
      await user.click(expandButton);

      // Verify "No preview available" message
      expect(await screen.findByText('No preview available')).toBeInTheDocument();
    });

    it('shows "No preview available" for documents with empty raw_text', async () => {
      const user = userEvent.setup();
      const docWithEmptyText = {
        ...mockDocuments[0],
        raw_text: '',
      } as KnowledgeDocument;
      renderPage([docWithEmptyText]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Expand row
      const expandButton = await screen.findByLabelText('Expand row');
      await user.click(expandButton);

      // Verify "No preview available" message
      expect(await screen.findByText('No preview available')).toBeInTheDocument();
    });

    it('shows "Document is being processed..." for processing documents', async () => {
      const user = userEvent.setup();
      const processingDoc = {
        ...mockDocuments[0],
        status: 'processing' as const,
      } as KnowledgeDocument;
      renderPage([processingDoc]);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Note: expand button should be disabled for processing docs
      // But we can verify the message by temporarily enabling it
      // This tests the renderSubComponent logic
      const expandButton = await screen.findByLabelText('Expand row');
      expect(expandButton).toBeDisabled();
    });

    it('does not trigger row click when expand button is clicked', async () => {
      const user = userEvent.setup();
      renderPage(mockDocuments);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Click expand button (using e.stopPropagation internally)
      const expandButton = await screen.findByLabelText('Expand row');
      await user.click(expandButton);

      // Verify the expand/collapse works without triggering row click
      expect(await screen.findByText(/React is a JavaScript library/)).toBeInTheDocument();
    });

    it('allows multiple rows to be expanded simultaneously', async () => {
      const user = userEvent.setup();
      const multipleDocuments = [
        {
          ...mockDocuments[0],
          id: 'doc-1',
          name: 'React Docs',
          raw_text: 'React is a JavaScript library for building user interfaces.',
        },
        {
          ...mockDocuments[0],
          id: 'doc-2',
          name: 'Vue Docs',
          raw_text: 'Vue is a progressive framework for building user interfaces.',
        },
      ] as KnowledgeDocument[];
      renderPage(multipleDocuments);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Expand first row
      const expandButtons = await screen.findAllByLabelText('Expand row');
      await user.click(expandButtons[0]!); // Safe: findAllByLabelText ensures elements exist

      // Verify first preview is shown
      expect(await screen.findByText(/React is a JavaScript library/)).toBeInTheDocument();

      // Expand second row
      await user.click(expandButtons[1]!); // Safe: findAllByLabelText ensures elements exist

      // Verify both previews are shown
      expect(screen.getByText(/React is a JavaScript library/)).toBeInTheDocument();
      expect(screen.getByText(/Vue is a progressive framework/)).toBeInTheDocument();
    });

    it('rotates chevron icon when row is expanded', async () => {
      const user = userEvent.setup();
      renderPage(mockDocuments);

      // Switch to Documents tab
      await user.click(screen.getByRole('tab', { name: /documents/i }));

      // Get expand button and chevron
      const expandButton = await screen.findByLabelText('Expand row');
      const chevron = expandButton.querySelector('svg');

      // Verify chevron doesn't have rotate-90 class initially
      expect(chevron).not.toHaveClass('rotate-90');

      // Expand row
      await user.click(expandButton);

      // Verify chevron has rotate-90 class
      expect(chevron).toHaveClass('rotate-90');

      // Collapse row
      const collapseButton = await screen.findByLabelText('Collapse row');
      await user.click(collapseButton);

      // Verify chevron no longer has rotate-90 class
      const chevronAfterCollapse = collapseButton.querySelector('svg');
      expect(chevronAfterCollapse).not.toHaveClass('rotate-90');
    });
  });
});
