import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import WorkflowsPage from './WorkflowsPage';
import type { WorkflowSummary, WorkflowDetail } from '@/types';
import type { EventDrivenPipeline } from '@/utils/pipeline';

// Mock modules
vi.mock('@/utils/workflow', () => ({
  getActiveWorkflow: vi.fn(),
  formatElapsedTime: vi.fn(),
}));

vi.mock('@/utils/pipeline', () => ({
  buildPipelineFromEvents: vi.fn(),
}));

// Mock useVirtualizer to render all items (JSDOM doesn't support scroll dimensions)
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count, estimateSize }: { count: number; estimateSize: (index: number) => number }) => {
    const items = Array.from({ length: count }, (_, index) => ({
      index,
      key: index,
      size: estimateSize(index),
      start: Array.from({ length: index }, (_, i) => estimateSize(i)).reduce((a, b) => a + b, 0),
    }));
    return {
      getVirtualItems: () => items,
      getTotalSize: () => items.reduce((acc, item) => acc + item.size, 0),
      scrollToIndex: vi.fn(),
    };
  },
}));

import { getActiveWorkflow, formatElapsedTime } from '@/utils/workflow';
import { buildPipelineFromEvents } from '@/utils/pipeline';

// Mock data
const mockWorkflowSummary: WorkflowSummary = {
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_path: '/tmp/worktrees/proj-123-feature',
  profile: null,
  status: 'in_progress',
  created_at: '2025-12-07T08:55:00Z',
  started_at: '2025-12-07T09:00:00Z',
  current_stage: 'developer',
  total_cost_usd: null,
  total_tokens: null,
  total_duration_ms: null,
};

const mockWorkflowDetail: WorkflowDetail = {
  ...mockWorkflowSummary,
  completed_at: null,
  failure_reason: null,
  token_usage: null,
  recent_events: [
    { id: 'e1', workflow_id: '1', sequence: 1, timestamp: '2025-12-07T09:01:00Z', event_type: 'stage_started', agent: 'developer', message: 'Started coding', level: 'info' },
  ],
  // Agentic execution fields
  goal: null,
  plan_markdown: null,
  plan_path: null,
};

// Event-driven pipeline mock data (new format)
const mockPipeline: EventDrivenPipeline = {
  nodes: [
    {
      id: 'architect',
      type: 'agent',
      position: { x: 0, y: 0 },
      data: { agentType: 'architect', status: 'completed', iterations: [], isExpanded: false },
    },
    {
      id: 'developer',
      type: 'agent',
      position: { x: 200, y: 0 },
      data: { agentType: 'developer', status: 'active', iterations: [], isExpanded: false },
    },
    {
      id: 'reviewer',
      type: 'agent',
      position: { x: 400, y: 0 },
      data: { agentType: 'reviewer', status: 'pending', iterations: [], isExpanded: false },
    },
  ],
  edges: [
    { id: 'architect-developer', source: 'architect', target: 'developer', data: { status: 'completed' } },
    { id: 'developer-reviewer', source: 'developer', target: 'reviewer', data: { status: 'active' } },
  ],
};

// Second workflow for testing selection behavior
const mockSecondWorkflowSummary: WorkflowSummary = {
  id: 'wf-002',
  issue_id: 'PROJ-456',
  worktree_path: '/tmp/worktrees/proj-456-bugfix',
  profile: null,
  status: 'blocked',
  created_at: '2025-12-07T07:55:00Z',
  started_at: '2025-12-07T08:00:00Z',
  current_stage: 'reviewer',
  total_cost_usd: null,
  total_tokens: null,
  total_duration_ms: null,
};

const mockSecondWorkflowDetail: WorkflowDetail = {
  ...mockSecondWorkflowSummary,
  completed_at: null,
  failure_reason: null,
  token_usage: null,
  recent_events: [
    { id: 'e2', workflow_id: 'wf-002', sequence: 1, timestamp: '2025-12-07T08:01:00Z', event_type: 'stage_started', agent: 'reviewer', message: 'Started review', level: 'info' },
  ],
  // Agentic execution fields
  goal: 'Fix the login bug',
  plan_markdown: '## Plan\n\n1. Identify the issue\n2. Fix the bug',
  plan_path: null,
};

/**
 * Helper to render WorkflowsPage with router context and loader data
 */
function renderWithRouter(
  loaderData: { workflows: WorkflowSummary[]; detail: WorkflowDetail | null },
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
    vi.mocked(buildPipelineFromEvents).mockReturnValue(mockPipeline);
    vi.mocked(formatElapsedTime).mockReturnValue('2h 15m');
  });

  it('should render WorkflowEmptyState when no workflows and no detail', async () => {
    vi.mocked(getActiveWorkflow).mockReturnValue(null);

    renderWithRouter({ workflows: [], detail: null }, '/workflows');

    await waitFor(() => {
      expect(screen.getByText(/no active workflows/i)).toBeInTheDocument();
    });
  });

  it('should display workflow detail when no active workflows but detail exists (past workflow)', async () => {
    vi.mocked(getActiveWorkflow).mockReturnValue(null);

    // Simulate viewing a past workflow when no active workflows exist
    renderWithRouter({ workflows: [], detail: mockWorkflowDetail }, '/workflows/wf-001');

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
    renderWithRouter({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      // PageHeader uses banner role
      const pageHeader = screen.getByRole('banner');
      expect(pageHeader).toBeInTheDocument();

      // Scope assertions to the page header to verify text appears in the correct location
      expect(within(pageHeader).getByText('PROJ-123')).toBeInTheDocument();
      expect(within(pageHeader).getByText('/tmp/worktrees/proj-123-feature')).toBeInTheDocument();
    });
  });

  it('should display workflow pipeline canvas when detail exists', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      // WorkflowCanvas renders pipeline nodes with proper display names
      expect(screen.getByText('Architect')).toBeInTheDocument();
      expect(screen.getByText('Developer')).toBeInTheDocument();
    });
  });

  it('should display job queue and activity log side by side', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      // JobQueue renders the section title
      expect(screen.getByText('JOB QUEUE')).toBeInTheDocument();
      // ActivityLog renders stage headers based on events
      expect(screen.getByText('Implementation (Developer)')).toBeInTheDocument();
    });
  });

  it('should not show loading skeleton when detail is pre-loaded from loader', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      // Should not see loading text when detail is pre-loaded
      expect(screen.queryByText('Loading activity...')).not.toBeInTheDocument();
      // Should see actual activity log with stage headers
      expect(screen.getByText('Implementation (Developer)')).toBeInTheDocument();
    });
  });

  it('should highlight selected workflow in job queue', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      // Query the job queue button directly by its accessible name
      const workflowButton = screen.getByRole('button', { name: /PROJ-123/ });
      expect(workflowButton).toBeInTheDocument();
      expect(workflowButton).toHaveAttribute('data-selected', 'true');
    });
  });

  it('should call buildPipelineFromEvents with workflow events', async () => {
    renderWithRouter({ workflows: [mockWorkflowSummary], detail: mockWorkflowDetail }, '/workflows');

    await waitFor(() => {
      expect(buildPipelineFromEvents).toHaveBeenCalledWith(
        mockWorkflowDetail.recent_events,
        { showDefaultPipeline: true }
      );
    });
  });

  it('should show active workflow detail when clicking back after selecting another workflow', async () => {
    const user = userEvent.setup();

    // Render with two workflows, active workflow is wf-001
    renderWithRouter(
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

    // Verify buildPipelineFromEvents was called with the active workflow's events
    expect(buildPipelineFromEvents).toHaveBeenLastCalledWith(
      mockWorkflowDetail.recent_events,
      { showDefaultPipeline: true }
    );
  });
});
