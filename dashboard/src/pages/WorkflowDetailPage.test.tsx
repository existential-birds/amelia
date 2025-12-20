import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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
      { id: 't1', label: 'developer', subtitle: 'Setup', status: 'completed' as const },
      { id: 't2', label: 'developer', subtitle: 'Implement', status: 'active' as const },
    ],
    edges: [{ from: 't1', to: 't2', label: '', status: 'completed' as const }],
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
  plan: {
    tasks: [
      { id: 't1', description: 'Setup', dependencies: [], status: 'completed' },
      { id: 't2', description: 'Implement', dependencies: ['t1'], status: 'in_progress' },
    ],
    execution_order: ['t1', 't2'],
  },
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
      {
        path: '/workflows',
        element: <div>Workflows List</div>,
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

  it('should render workflow progress', async () => {
    renderWithRouter({ workflow: mockWorkflow });

    await waitFor(() => {
      // WorkflowProgress component shows task completion
      expect(screen.getByText(/of 2 stages/)).toBeInTheDocument();
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

  it('should render structured empty state with action when workflow is missing', async () => {
    renderWithRouter({ workflow: null });

    // Check for title and description
    expect(await screen.findByText('Workflow Not Found')).toBeInTheDocument();
    expect(screen.getByText('The requested workflow could not be loaded.')).toBeInTheDocument();

    // Check for action button
    const button = screen.getByRole('button', { name: /back to workflows/i });
    expect(button).toBeInTheDocument();

    // Verify navigation
    fireEvent.click(button);
    expect(await screen.findByText('Workflows List')).toBeInTheDocument();
  });
});
