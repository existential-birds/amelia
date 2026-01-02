import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import WorkflowDetailPage from './WorkflowDetailPage';
import { createMockWorkflowDetail } from '@/__tests__/fixtures';

// Mock modules
vi.mock('@/utils/workflow', () => ({
  formatElapsedTime: vi.fn(() => '1h 30m'),
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

  it('should render tool calls chart for completed workflows', async () => {
    const completedWorkflow = createMockWorkflowDetail({
      ...mockWorkflow,
      status: 'completed',
      tool_calls: [
        { id: 'call-1', tool_name: 'read_file', tool_input: {}, timestamp: '2025-12-07T09:00:00Z', agent: 'developer' },
        { id: 'call-2', tool_name: 'write_file', tool_input: {}, timestamp: '2025-12-07T09:01:00Z', agent: 'developer' },
      ],
    });
    renderWithRouter({ workflow: completedWorkflow });

    await waitFor(() => {
      // Tool calls section header
      expect(screen.getByText('TOOL CALLS')).toBeInTheDocument();
    });
  });

  it('should not render tool calls chart for in-progress workflows', async () => {
    renderWithRouter({ workflow: mockWorkflow });

    await waitFor(() => {
      // The header should be rendered
      expect(screen.getByText('PROJ-123')).toBeInTheDocument();
    });

    // Tool calls section should NOT be present
    expect(screen.queryByText('TOOL CALLS')).not.toBeInTheDocument();
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
