import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import WorkflowDetailPage from './WorkflowDetailPage';
import { createMockWorkflowDetail, createMockEvent } from '@/__tests__/fixtures';

// Mock the workflow store - supports both selector and no-selector usage patterns
const mockEventsByWorkflow: Record<string, unknown[]> = {};
const mockPendingActions: string[] = [];
vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn((selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      eventsByWorkflow: mockEventsByWorkflow,
      pendingActions: mockPendingActions,
      addPendingAction: vi.fn(),
      removePendingAction: vi.fn(),
    };
    return selector ? selector(state) : state;
  }),
}));

// Mock modules
vi.mock('@/utils/workflow', () => ({
  formatElapsedTime: vi.fn(() => '1h 30m'),
}));

const mockResumeWorkflow = vi.fn();
vi.mock('@/hooks/useWorkflowActions', () => ({
  useWorkflowActions: vi.fn(() => ({
    approveWorkflow: vi.fn(),
    rejectWorkflow: vi.fn(),
    cancelWorkflow: vi.fn(),
    resumeWorkflow: mockResumeWorkflow,
    isActionPending: vi.fn(() => false),
  })),
}));

const mockWorkflow = createMockWorkflowDetail({
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_path: '/tmp/worktrees/proj-123-feature',
  status: 'in_progress',
  started_at: '2025-12-07T09:00:00Z',
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
    // Reset mock state
    Object.keys(mockEventsByWorkflow).forEach(key => delete mockEventsByWorkflow[key]);
  });

  it('should render workflow header with issue_id', async () => {
    renderWithRouter({ workflow: mockWorkflow });

    await waitFor(() => {
      expect(screen.getByText('PROJ-123')).toBeInTheDocument();
    });
  });

  it('should not render activity log section', async () => {
    renderWithRouter({ workflow: mockWorkflow });

    await waitFor(() => {
      expect(screen.getByText('PROJ-123')).toBeInTheDocument();
    });

    expect(screen.queryByText('ACTIVITY LOG')).not.toBeInTheDocument();
  });
});

describe('WorkflowDetailPage resume button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.keys(mockEventsByWorkflow).forEach(key => delete mockEventsByWorkflow[key]);
  });

  it('shows resume button for recoverable failed workflows (API flag)', async () => {
    const failedWorkflow = createMockWorkflowDetail({
      id: 'wf-recover',
      issue_id: 'RECOVER-TEST',
      worktree_path: '/tmp/worktrees/recover-test',
      status: 'failed',
      failure_reason: 'Server restarted',
      recoverable: true,
    });

    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:id',
          element: <WorkflowDetailPage />,
          loader: () => ({ workflow: failedWorkflow }),
          HydrateFallback: () => null,
        },
      ],
      { initialEntries: ['/workflows/wf-recover'] }
    );

    render(<RouterProvider router={router} />);

    await waitFor(() => {
      expect(screen.getByText('RECOVERY')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument();
    });
  });

  it('shows resume button via real-time store events fallback', async () => {
    const recoverableEvent = createMockEvent({
      id: 'evt-fail-rt',
      workflow_id: 'wf-recover-rt',
      sequence: 1,
      event_type: 'workflow_failed',
      message: 'Server restarted',
      data: { recoverable: true },
    });

    mockEventsByWorkflow['wf-recover-rt'] = [recoverableEvent];

    const failedWorkflow = createMockWorkflowDetail({
      id: 'wf-recover-rt',
      issue_id: 'RECOVER-RT',
      worktree_path: '/tmp/worktrees/recover-rt',
      status: 'failed',
      failure_reason: 'Server restarted',
      // No recoverable flag — simulates store events arriving before API refresh
    });

    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:id',
          element: <WorkflowDetailPage />,
          loader: () => ({ workflow: failedWorkflow }),
          HydrateFallback: () => null,
        },
      ],
      { initialEntries: ['/workflows/wf-recover-rt'] }
    );

    render(<RouterProvider router={router} />);

    await waitFor(() => {
      expect(screen.getByText('RECOVERY')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument();
    });
  });

  it('does not show resume button for non-recoverable failed workflows', async () => {
    const nonRecoverableEvent = createMockEvent({
      id: 'evt-fail-2',
      workflow_id: 'wf-norecov',
      sequence: 1,
      event_type: 'workflow_failed',
      message: 'Max retries exceeded',
    });

    mockEventsByWorkflow['wf-norecov'] = [nonRecoverableEvent];

    const failedWorkflow = createMockWorkflowDetail({
      id: 'wf-norecov',
      issue_id: 'NORECOV-TEST',
      worktree_path: '/tmp/worktrees/norecov-test',
      status: 'failed',
      failure_reason: 'Max retries exceeded',
    });

    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:id',
          element: <WorkflowDetailPage />,
          loader: () => ({ workflow: failedWorkflow }),
          HydrateFallback: () => null,
        },
      ],
      { initialEntries: ['/workflows/wf-norecov'] }
    );

    render(<RouterProvider router={router} />);

    await waitFor(() => {
      expect(screen.getByText('NORECOV-TEST')).toBeInTheDocument();
    });

    expect(screen.queryByText('RECOVERY')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /resume/i })).not.toBeInTheDocument();
  });

  it('respects API recoverable: false even when store events say recoverable', async () => {
    const recoverableEvent = createMockEvent({
      id: 'evt-stale',
      workflow_id: 'wf-stale',
      sequence: 1,
      event_type: 'workflow_failed',
      message: 'Server restarted',
      data: { recoverable: true },
    });

    mockEventsByWorkflow['wf-stale'] = [recoverableEvent];

    const failedWorkflow = createMockWorkflowDetail({
      id: 'wf-stale',
      issue_id: 'STALE-TEST',
      worktree_path: '/tmp/worktrees/stale-test',
      status: 'failed',
      failure_reason: 'Server restarted',
      recoverable: false, // API explicitly says not recoverable
    });

    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:id',
          element: <WorkflowDetailPage />,
          loader: () => ({ workflow: failedWorkflow }),
          HydrateFallback: () => null,
        },
      ],
      { initialEntries: ['/workflows/wf-stale'] }
    );

    render(<RouterProvider router={router} />);

    await waitFor(() => {
      expect(screen.getByText('STALE-TEST')).toBeInTheDocument();
    });

    // API says not recoverable, store events should NOT override
    expect(screen.queryByText('RECOVERY')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /resume/i })).not.toBeInTheDocument();
  });

  it('does not show resume button for non-failed workflows', async () => {
    const inProgressWorkflow = createMockWorkflowDetail({
      id: 'wf-active',
      issue_id: 'ACTIVE-TEST',
      worktree_path: '/tmp/worktrees/active-test',
      status: 'in_progress',
    });

    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:id',
          element: <WorkflowDetailPage />,
          loader: () => ({ workflow: inProgressWorkflow }),
          HydrateFallback: () => null,
        },
      ],
      { initialEntries: ['/workflows/wf-active'] }
    );

    render(<RouterProvider router={router} />);

    await waitFor(() => {
      expect(screen.getByText('ACTIVE-TEST')).toBeInTheDocument();
    });

    expect(screen.queryByText('RECOVERY')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /resume/i })).not.toBeInTheDocument();
  });
});
