import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import WorkflowsPage from './WorkflowsPage';
import type { WorkflowSummary, WorkflowDetail } from '@/types';

// Mock modules
vi.mock('@/utils/workflow', () => ({
  getActiveWorkflow: vi.fn(),
  formatElapsedTime: vi.fn(),
}));

vi.mock('@/utils/pipeline', () => ({
  buildPipeline: vi.fn(),
}));

import { getActiveWorkflow, formatElapsedTime } from '@/utils/workflow';
import { buildPipeline } from '@/utils/pipeline';

// Mock data
const mockWorkflowSummary: WorkflowSummary = {
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_name: 'proj-123-feature',
  status: 'in_progress',
  started_at: '2025-12-07T09:00:00Z',
  current_stage: 'developer',
};

const mockWorkflowDetail: WorkflowDetail = {
  ...mockWorkflowSummary,
  worktree_path: '/path/to/worktree',
  completed_at: null,
  failure_reason: null,
  plan: {
    execution_order: ['t1', 't2'],
    tasks: [
      { id: 't1', agent: 'architect', description: 'Plan', status: 'completed', dependencies: [] },
      { id: 't2', agent: 'developer', description: 'Code', status: 'in_progress', dependencies: ['t1'] },
    ],
  },
  token_usage: {},
  recent_events: [
    { id: 'e1', workflow_id: '1', sequence: 1, timestamp: '2025-12-07T09:01:00Z', event_type: 'stage_started', agent: 'developer', message: 'Started coding' },
  ],
};

const mockPipeline = {
  nodes: [
    { id: 't1', label: 'architect', subtitle: 'Plan', status: 'completed' as const },
    { id: 't2', label: 'developer', subtitle: 'Code', status: 'active' as const },
  ],
  edges: [{ from: 't1', to: 't2', label: '', status: 'completed' as const }],
};

// Second workflow for testing selection behavior
const mockSecondWorkflowSummary: WorkflowSummary = {
  id: 'wf-002',
  issue_id: 'PROJ-456',
  worktree_name: 'proj-456-bugfix',
  status: 'blocked',
  started_at: '2025-12-07T08:00:00Z',
  current_stage: 'reviewer',
};

const mockSecondWorkflowDetail: WorkflowDetail = {
  ...mockSecondWorkflowSummary,
  worktree_path: '/path/to/second/worktree',
  completed_at: null,
  failure_reason: null,
  plan: {
    execution_order: ['t1'],
    tasks: [
      { id: 't1', agent: 'reviewer', description: 'Review', status: 'in_progress', dependencies: [] },
    ],
  },
  token_usage: {},
  recent_events: [
    { id: 'e2', workflow_id: 'wf-002', sequence: 1, timestamp: '2025-12-07T08:01:00Z', event_type: 'stage_started', agent: 'reviewer', message: 'Started review' },
  ],
};

/**
 * Helper to render WorkflowsPage with router context and loader data
 */
function renderWithRouter(loaderData: { workflows: WorkflowSummary[]; activeDetail: WorkflowDetail | null }) {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <WorkflowsPage />,
        loader: () => loaderData,
        HydrateFallback: () => null,
      },
      {
        path: '/workflows/:id',
        element: <div>Detail Page</div>,
        loader: ({ params }) => {
          // Return the appropriate detail based on the workflow ID
          if (params.id === 'wf-002') {
            return { workflow: mockSecondWorkflowDetail };
          }
          return { workflow: mockWorkflowDetail };
        },
        HydrateFallback: () => null,
      },
    ],
    { initialEntries: ['/'] }
  );

  return render(<RouterProvider router={router} />);
}

describe('WorkflowsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getActiveWorkflow).mockReturnValue(mockWorkflowSummary);
    vi.mocked(buildPipeline).mockReturnValue(mockPipeline);
    vi.mocked(formatElapsedTime).mockReturnValue('2h 15m');
  });

  it('should render WorkflowEmptyState when no workflows', async () => {
    vi.mocked(getActiveWorkflow).mockReturnValue(null);

    renderWithRouter({ workflows: [], activeDetail: null });

    await waitFor(() => {
      expect(screen.getByText(/no active workflows/i)).toBeInTheDocument();
    });
  });

  it('should display workflow header with issue info when activeDetail exists', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], activeDetail: mockWorkflowDetail });

    await waitFor(() => {
      // PageHeader uses banner role
      const pageHeader = screen.getByRole('banner');
      expect(pageHeader).toBeInTheDocument();

      // Scope assertions to the page header to verify text appears in the correct location
      expect(within(pageHeader).getByText('PROJ-123')).toBeInTheDocument();
      expect(within(pageHeader).getByText('proj-123-feature')).toBeInTheDocument();
    });
  });

  it('should display workflow pipeline canvas when activeDetail exists', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], activeDetail: mockWorkflowDetail });

    await waitFor(() => {
      // WorkflowCanvas renders pipeline nodes
      expect(screen.getByText('architect')).toBeInTheDocument();
      expect(screen.getByText('developer')).toBeInTheDocument();
    });
  });

  it('should display job queue and activity log side by side', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], activeDetail: mockWorkflowDetail });

    await waitFor(() => {
      // JobQueue renders the section title
      expect(screen.getByText('JOB QUEUE')).toBeInTheDocument();
      // ActivityLog renders the section title
      expect(screen.getByText('ACTIVITY LOG')).toBeInTheDocument();
    });
  });

  it('should not show loading skeleton when activeDetail is pre-loaded from loader', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], activeDetail: mockWorkflowDetail });

    await waitFor(() => {
      // Should not see loading text when detail is pre-loaded
      expect(screen.queryByText('Loading activity...')).not.toBeInTheDocument();
      // Should see actual activity log
      expect(screen.getByText('ACTIVITY LOG')).toBeInTheDocument();
    });
  });

  it('should highlight selected workflow in job queue', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], activeDetail: mockWorkflowDetail });

    await waitFor(() => {
      // Query the job queue button directly by its accessible name
      const workflowButton = screen.getByRole('button', { name: /PROJ-123/ });
      expect(workflowButton).toBeInTheDocument();
      expect(workflowButton).toHaveAttribute('data-selected', 'true');
    });
  });

  it('should call buildPipeline with workflow detail', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], activeDetail: mockWorkflowDetail });

    await waitFor(() => {
      expect(buildPipeline).toHaveBeenCalledWith(mockWorkflowDetail);
    });
  });

  it('should show active workflow detail when clicking back after selecting another workflow', async () => {
    const user = userEvent.setup();

    // Render with two workflows, active workflow is wf-001
    renderWithRouter({
      workflows: [mockWorkflowSummary, mockSecondWorkflowSummary],
      activeDetail: mockWorkflowDetail,
    });

    // Wait for initial render showing active workflow (PROJ-123)
    await waitFor(() => {
      const pageHeader = screen.getByRole('banner');
      expect(within(pageHeader).getByText('PROJ-123')).toBeInTheDocument();
    });

    // Click the second workflow (PROJ-456) - should trigger fetch
    const secondWorkflowButton = screen.getByRole('button', { name: /PROJ-456/ });
    await user.click(secondWorkflowButton);

    // Wait for the fetched workflow detail to display
    await waitFor(() => {
      const pageHeader = screen.getByRole('banner');
      expect(within(pageHeader).getByText('PROJ-456')).toBeInTheDocument();
    });

    // Click back to the active workflow (PROJ-123) - should show pre-loaded activeDetail
    const firstWorkflowButton = screen.getByRole('button', { name: /PROJ-123/ });
    await user.click(firstWorkflowButton);

    // BUG: Currently shows PROJ-456 (stale fetcher data) instead of PROJ-123 (activeDetail)
    await waitFor(() => {
      const pageHeader = screen.getByRole('banner');
      expect(within(pageHeader).getByText('PROJ-123')).toBeInTheDocument();
    });

    // Verify buildPipeline was called with the active workflow detail, not the fetched one
    expect(buildPipeline).toHaveBeenLastCalledWith(mockWorkflowDetail);
  });
});
