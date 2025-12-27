import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import WorkflowDetailPage from './WorkflowDetailPage';
import { createMockWorkflowDetail } from '@/__tests__/fixtures';

// Mock modules
vi.mock('@/utils/workflow', () => ({
  formatElapsedTime: vi.fn(() => '1h 30m'),
}));

vi.mock('@/utils/pipeline', () => ({
  buildPipeline: vi.fn(() => ({
    nodes: [
      { id: 'architect', label: 'Architect', status: 'completed' as const },
      { id: 'developer', label: 'Developer', status: 'active' as const, subtitle: 'In progress...' },
      { id: 'reviewer', label: 'Reviewer', status: 'pending' as const },
    ],
    edges: [
      { from: 'architect', to: 'developer', label: '', status: 'completed' as const },
      { from: 'developer', to: 'reviewer', label: '', status: 'active' as const },
    ],
  })),
}));

const mockWorkflow = createMockWorkflowDetail({
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_name: 'proj-123-feature',
  worktree_path: '/tmp/worktrees/proj-123',
  status: 'in_progress',
  started_at: '2025-12-07T09:00:00Z',
  current_stage: 'developer',
});

/**
 * Helper to render WorkflowDetailPage with data router context
 */
function renderWithRouter(loaderData: { workflow: typeof mockWorkflow | null }) {
  const router = createMemoryRouter(
    [
      {
        path: '/workflows/:id',
        element: <WorkflowDetailPage />,
        loader: () => loaderData,
        HydrateFallback: () => null,
      },
    ],
    { initialEntries: ['/workflows/wf-001'] }
  );

  return render(<RouterProvider router={router} />);
}

describe('WorkflowDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render workflow header with issue_id', async () => {
    renderWithRouter({ workflow: mockWorkflow });

    await waitFor(() => {
      expect(screen.getByText('PROJ-123')).toBeInTheDocument();
    });
  });

  it('should render pipeline visualization', async () => {
    renderWithRouter({ workflow: mockWorkflow });

    await waitFor(() => {
      // Pipeline section header
      expect(screen.getByText('PIPELINE')).toBeInTheDocument();
    });
  });

  it('should render activity log', async () => {
    renderWithRouter({ workflow: mockWorkflow });

    await waitFor(() => {
      // There are two ACTIVITY LOG elements - use getAllByText and verify at least one exists
      const activityLogHeaders = screen.getAllByText('ACTIVITY LOG');
      expect(activityLogHeaders.length).toBeGreaterThanOrEqual(1);
    });
  });
});
