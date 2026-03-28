import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import WorkflowsPage from './WorkflowsPage';
import { createMockWorkflowSummary, createMockWorkflowDetail } from '@/__tests__/fixtures';
import type { WorkflowSummary, WorkflowDetail } from '@/types';

// Mock modules
vi.mock('@/utils/workflow', () => ({
  getActiveWorkflow: vi.fn(),
  formatElapsedTime: vi.fn(),
}));

import { getActiveWorkflow, formatElapsedTime } from '@/utils/workflow';

// Mock data using fixture factories
const mockWorkflowSummary = createMockWorkflowSummary({
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_path: '/tmp/worktrees/proj-123-feature',
  status: 'in_progress',
  created_at: '2025-12-07T08:55:00Z',
  started_at: '2025-12-07T09:00:00Z',
});

const mockWorkflowDetail = createMockWorkflowDetail({
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_path: '/tmp/worktrees/proj-123-feature',
  status: 'in_progress',
  created_at: '2025-12-07T08:55:00Z',
  started_at: '2025-12-07T09:00:00Z',
  goal: null,
});

// Second workflow for testing selection behavior
const mockSecondWorkflowSummary = createMockWorkflowSummary({
  id: 'wf-002',
  issue_id: 'PROJ-456',
  worktree_path: '/tmp/worktrees/proj-456-bugfix',
  status: 'blocked',
  created_at: '2025-12-07T07:55:00Z',
  started_at: '2025-12-07T08:00:00Z',
});

const mockSecondWorkflowDetail = createMockWorkflowDetail({
  id: 'wf-002',
  issue_id: 'PROJ-456',
  worktree_path: '/tmp/worktrees/proj-456-bugfix',
  status: 'blocked',
  created_at: '2025-12-07T07:55:00Z',
  started_at: '2025-12-07T08:00:00Z',
  goal: 'Fix the login bug',
  plan_markdown: '## Plan\n\n1. Identify the issue\n2. Fix the bug',
});

/**
 * Helper to render WorkflowsPage with router context and loader data
 */
function renderPage(
  loaderData: { workflows: WorkflowSummary[]; detail: WorkflowDetail | null; detailError?: string | null },
  initialPath = '/'
) {
  const router = createMemoryRouter(
    [
      {
        path: '/workflows',
        children: [
          {
            index: true,
            element: <WorkflowsPage />,
            loader: () => loaderData,
            HydrateFallback: () => null,
          },
          {
            path: ':id',
            element: <WorkflowsPage />,
            loader: ({ params }) => {
              // Return the appropriate detail based on the workflow ID
              // When workflows is empty (past workflow case), use loaderData.detail directly
              if (loaderData.workflows.length === 0 && loaderData.detail) {
                return { workflows: loaderData.workflows, detail: loaderData.detail };
              }
              // Otherwise, look up by ID for switching between workflows
              if (params.id === 'wf-002') {
                return { workflows: loaderData.workflows, detail: mockSecondWorkflowDetail };
              }
              return { workflows: loaderData.workflows, detail: mockWorkflowDetail };
            },
            HydrateFallback: () => null,
          },
        ],
      },
    ],
    { initialEntries: [initialPath] }
  );

  return render(<RouterProvider router={router} />);
}

describe('WorkflowsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getActiveWorkflow).mockReturnValue(mockWorkflowSummary);
    vi.mocked(formatElapsedTime).mockReturnValue('2h 15m');
  });

  it('should render WorkflowEmptyState when no workflows and no detail', async () => {
    vi.mocked(getActiveWorkflow).mockReturnValue(null);

    renderPage({ workflows: [], detail: null }, '/workflows');

    await waitFor(() => {
      expect(screen.getByText(/no active workflows/i)).toBeInTheDocument();
    });
  });

  it('should display workflow detail when no active workflows but detail exists (past workflow)', async () => {
    vi.mocked(getActiveWorkflow).mockReturnValue(null);

    // Simulate viewing a past workflow when no active workflows exist
    renderPage({ workflows: [], detail: mockWorkflowDetail }, '/workflows/wf-001');

    await waitFor(() => {
      // Should NOT show the WorkflowEmptyState component (uses data-slot="empty-state")
      const emptyState = document.querySelector('[data-slot="empty-state"]');
      expect(emptyState).not.toBeInTheDocument();
      // Should show the workflow detail in the header
      const pageHeader = screen.getByRole('banner');
      expect(within(pageHeader).getByText('PROJ-123')).toBeInTheDocument();
    });
  });

  it('should display workflow header with issue info when detail exists', async () => {
    renderPage({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      // PageHeader uses banner role
      const pageHeader = screen.getByRole('banner');
      expect(pageHeader).toBeInTheDocument();

      // Scope assertions to the page header to verify text appears in the correct location
      expect(within(pageHeader).getByText('PROJ-123')).toBeInTheDocument();
      expect(within(pageHeader).getByText('/tmp/worktrees/proj-123-feature')).toBeInTheDocument();
    });
  });

  it('should display job queue', async () => {
    renderPage({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      expect(screen.getByText('JOB QUEUE')).toBeInTheDocument();
    });
  });

  it('should show job queue alongside error banner when detailError is set', async () => {
    renderPage(
      { workflows: [mockWorkflowSummary], detail: null, detailError: 'Network error' },
      '/workflows'
    );

    await waitFor(() => {
      expect(screen.getByText(/Failed to load workflow details/)).toBeInTheDocument();
      expect(screen.getByText('JOB QUEUE')).toBeInTheDocument();
    });
  });

  it('should highlight selected workflow in job queue', async () => {
    renderPage({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      // Query the job queue button directly by its accessible name
      const workflowButton = screen.getByRole('button', { name: /PROJ-123/ });
      expect(workflowButton).toBeInTheDocument();
      expect(workflowButton).toHaveAttribute('data-selected', 'true');
    });
  });

  it('should show active workflow detail when clicking back after selecting another workflow', async () => {
    const user = userEvent.setup();

    // Render with two workflows, active workflow is wf-001
    renderPage(
      {
        workflows: [mockWorkflowSummary, mockSecondWorkflowSummary],
        detail: mockWorkflowDetail,
      },
      '/workflows'
    );

    // Wait for initial render showing active workflow (PROJ-123)
    await waitFor(() => {
      const pageHeader = screen.getByRole('banner');
      expect(within(pageHeader).getByText('PROJ-123')).toBeInTheDocument();
    });

    // Click the second workflow (PROJ-456) - should navigate to /workflows/wf-002
    const secondWorkflowButton = screen.getByRole('button', { name: /PROJ-456/ });
    await user.click(secondWorkflowButton);

    // Wait for the workflow detail to display (loaded via URL param)
    await waitFor(() => {
      const pageHeader = screen.getByRole('banner');
      expect(within(pageHeader).getByText('PROJ-456')).toBeInTheDocument();
    });

    // Click back to the active workflow (PROJ-123) - should navigate to /workflows/wf-001
    const firstWorkflowButton = screen.getByRole('button', { name: /PROJ-123/ });
    await user.click(firstWorkflowButton);

    // Should show PROJ-123 detail from loader
    await waitFor(() => {
      const pageHeader = screen.getByRole('banner');
      expect(within(pageHeader).getByText('PROJ-123')).toBeInTheDocument();
    });
  });
});
