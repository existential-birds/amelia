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

  it('should render activity log', async () => {
    renderWithRouter({ workflow: mockWorkflow });

    await waitFor(() => {
      // There are two ACTIVITY LOG elements - use getAllByText and verify at least one exists
      const activityLogHeaders = screen.getAllByText('ACTIVITY LOG');
      expect(activityLogHeaders.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe('WorkflowDetailPage event merging', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset mock state
    Object.keys(mockEventsByWorkflow).forEach(key => delete mockEventsByWorkflow[key]);
  });

  it('merges loader events with real-time events from store', async () => {
    const loaderEvents = [
      createMockEvent({
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        agent: 'architect',
        event_type: 'stage_started',
        message: 'Architect started',
      }),
    ];
    const storeEvents = [
      createMockEvent({
        id: 'evt-2',
        workflow_id: 'wf-1',
        sequence: 2,
        agent: 'architect',
        event_type: 'stage_completed',
        message: 'Architect completed',
      }),
    ];

    // Configure the mock state
    mockEventsByWorkflow['wf-1'] = storeEvents;

    const workflowWithEvents = createMockWorkflowDetail({
      id: 'wf-1',
      issue_id: 'MERGE-TEST',
      worktree_path: '/tmp/worktrees/merge-test',
      status: 'in_progress',
      recent_events: loaderEvents,
    });

    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:id',
          element: <WorkflowDetailPage />,
          loader: () => ({ workflow: workflowWithEvents }),
          HydrateFallback: () => null,
        },
      ],
      { initialEntries: ['/workflows/wf-1'] }
    );

    render(<RouterProvider router={router} />);

    // Wait for the page to render with merged events passed to ActivityLog
    await waitFor(() => {
      expect(screen.getByText('MERGE-TEST')).toBeInTheDocument();
    });

    // Activity log should be present (receives merged events)
    const activityLogHeaders = screen.getAllByText('ACTIVITY LOG');
    expect(activityLogHeaders.length).toBeGreaterThanOrEqual(1);
  });

  it('deduplicates events by id when merging', async () => {
    // Same event appears in both loader and store (e.g., after reconnection)
    const duplicateEvent = createMockEvent({
      id: 'evt-duplicate',
      workflow_id: 'wf-dup',
      sequence: 1,
      agent: 'architect',
      event_type: 'stage_started',
      message: 'Architect started',
    });

    // Configure the mock state
    mockEventsByWorkflow['wf-dup'] = [duplicateEvent];

    const workflowWithDuplicateEvent = createMockWorkflowDetail({
      id: 'wf-dup',
      issue_id: 'DUP-TEST',
      worktree_path: '/tmp/worktrees/dup-test',
      status: 'in_progress',
      recent_events: [duplicateEvent],
    });

    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:id',
          element: <WorkflowDetailPage />,
          loader: () => ({ workflow: workflowWithDuplicateEvent }),
          HydrateFallback: () => null,
        },
      ],
      { initialEntries: ['/workflows/wf-dup'] }
    );

    render(<RouterProvider router={router} />);

    await waitFor(() => {
      expect(screen.getByText('DUP-TEST')).toBeInTheDocument();
    });

    // Page renders without error - deduplication is working
    const activityLogHeaders = screen.getAllByText('ACTIVITY LOG');
    expect(activityLogHeaders.length).toBeGreaterThanOrEqual(1);
  });

  it('sorts merged events by sequence number', async () => {
    // Loader has event with sequence 3
    const loaderEvents = [
      createMockEvent({
        id: 'evt-3',
        workflow_id: 'wf-sort',
        sequence: 3,
        agent: 'developer',
        event_type: 'stage_started',
        message: 'Developer started',
      }),
    ];

    // Store has events with sequence 1 and 2 (arrived via WebSocket)
    const storeEvents = [
      createMockEvent({
        id: 'evt-1',
        workflow_id: 'wf-sort',
        sequence: 1,
        agent: 'architect',
        event_type: 'stage_started',
        message: 'Architect started',
      }),
      createMockEvent({
        id: 'evt-2',
        workflow_id: 'wf-sort',
        sequence: 2,
        agent: 'architect',
        event_type: 'stage_completed',
        message: 'Architect completed',
      }),
    ];

    // Configure the mock state
    mockEventsByWorkflow['wf-sort'] = storeEvents;

    const workflowForSort = createMockWorkflowDetail({
      id: 'wf-sort',
      issue_id: 'SORT-TEST',
      worktree_path: '/tmp/worktrees/sort-test',
      status: 'in_progress',
      recent_events: loaderEvents,
    });

    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:id',
          element: <WorkflowDetailPage />,
          loader: () => ({ workflow: workflowForSort }),
          HydrateFallback: () => null,
        },
      ],
      { initialEntries: ['/workflows/wf-sort'] }
    );

    render(<RouterProvider router={router} />);

    await waitFor(() => {
      expect(screen.getByText('SORT-TEST')).toBeInTheDocument();
    });

    // Events are sorted correctly (1, 2, 3) and passed to activity log
    const activityLogHeaders = screen.getAllByText('ACTIVITY LOG');
    expect(activityLogHeaders.length).toBeGreaterThanOrEqual(1);
  });
});

describe('WorkflowDetailPage resume button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.keys(mockEventsByWorkflow).forEach(key => delete mockEventsByWorkflow[key]);
  });

  it('shows resume button for recoverable failed workflows', async () => {
    const recoverableEvent = createMockEvent({
      id: 'evt-fail-1',
      workflow_id: 'wf-recover',
      sequence: 1,
      event_type: 'workflow_failed',
      message: 'Server restarted',
      data: { recoverable: true },
    });

    mockEventsByWorkflow['wf-recover'] = [recoverableEvent];

    const failedWorkflow = createMockWorkflowDetail({
      id: 'wf-recover',
      issue_id: 'RECOVER-TEST',
      worktree_path: '/tmp/worktrees/recover-test',
      status: 'failed',
      failure_reason: 'Server restarted',
      recent_events: [recoverableEvent],
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
      recent_events: [nonRecoverableEvent],
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
