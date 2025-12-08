import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
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
    tasks: [
      { id: 't1', agent: 'architect', description: 'Plan', status: 'completed', dependencies: [] },
      { id: 't2', agent: 'developer', description: 'Code', status: 'in_progress', dependencies: ['t1'] },
    ],
  },
  token_usage: {},
  recent_events: [
    { id: 'e1', timestamp: '2025-12-07T09:01:00Z', event_type: 'stage_started', agent: 'developer', message: 'Started coding' },
  ],
};

const mockPipeline = {
  nodes: [
    { id: 't1', label: 'architect', subtitle: 'Plan', status: 'completed' as const },
    { id: 't2', label: 'developer', subtitle: 'Code', status: 'active' as const },
  ],
  edges: [{ from: 't1', to: 't2', label: '', status: 'completed' as const }],
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
        loader: () => ({ workflow: mockWorkflowDetail }),
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
      // Find all instances of PROJ-123 and get the one inside a button (job queue item)
      const allMatches = screen.getAllByText('PROJ-123');
      const workflowButton = allMatches.find(el => el.closest('[role="button"]'))?.closest('[role="button"]');
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
});
