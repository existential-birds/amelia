/**
 * @fileoverview Tests for WorkflowsPage pending workflow actions.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import WorkflowsPage from '../WorkflowsPage';
import { api } from '../../api/client';
import type { WorkflowSummary, WorkflowDetail } from '../../types';

// Mock the API module
vi.mock('../../api/client');

// Mock the hooks module
vi.mock('../../hooks', () => ({
  useElapsedTime: () => '0h 00m',
  useAutoRevalidation: () => {},
}));

// Mock React Router
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
    useNavigate: () => vi.fn(),
    useParams: () => ({}),
    useRevalidator: () => ({ revalidate: vi.fn(), state: 'idle' }),
  };
});

import { useLoaderData } from 'react-router-dom';

// Helper to render with router context
const renderWithRouter = (component: React.ReactNode) => {
  return render(<MemoryRouter>{component}</MemoryRouter>);
};

describe('WorkflowsPage pending workflow actions', () => {
  const pendingWorkflow: WorkflowSummary = {
    id: 'wf-pending',
    issue_id: 'ISSUE-123',
    worktree_path: '/tmp/worktrees/repo',
    profile: null,
    status: 'pending',
    created_at: '2025-12-07T08:55:00Z',
    started_at: null,
    current_stage: null,
    total_cost_usd: null,
    total_tokens: null,
    total_duration_ms: null,
  };

  const pendingWorkflowDetail: WorkflowDetail = {
    ...pendingWorkflow,
    worktree_path: '/path/to/repo',
    completed_at: null,
    failure_reason: null,
    token_usage: null,
    recent_events: [],
    goal: null,
    plan_markdown: null,
    plan_path: null,
  };

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [],
      detail: null,
      detailError: null,
    });
  });

  it('should show Start button for pending workflows', async () => {
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [pendingWorkflow],
      detail: pendingWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    // Wait for workflows to load
    const startButton = await screen.findByRole('button', { name: /start/i });
    expect(startButton).toBeInTheDocument();
  });

  it('should show Cancel button for pending workflows', async () => {
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [pendingWorkflow],
      detail: pendingWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    const cancelButton = await screen.findByRole('button', { name: /cancel/i });
    expect(cancelButton).toBeInTheDocument();
  });

  it('should call startWorkflow when Start clicked', async () => {
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [pendingWorkflow],
      detail: pendingWorkflowDetail,
      detailError: null,
    });
    vi.mocked(api.startWorkflow).mockResolvedValue({
      workflow_id: 'wf-pending',
      status: 'started',
    });

    renderWithRouter(<WorkflowsPage />);

    const startButton = await screen.findByRole('button', { name: /start/i });
    fireEvent.click(startButton);

    await waitFor(() => {
      expect(api.startWorkflow).toHaveBeenCalledWith('wf-pending');
    });
  });

  it('should show "queued" for pending workflows', async () => {
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [pendingWorkflow],
      detail: pendingWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    // Look for the "queued" text in the pending workflow controls section
    // Use getAllByText since there are multiple elements containing "queued"
    const queuedElements = await screen.findAllByText(/queued/i);
    expect(queuedElements.length).toBeGreaterThan(0);
    // At least one should be the status text in the PendingWorkflowControls
    expect(queuedElements.some(el => el.className.includes('text-muted-foreground'))).toBe(true);
  });

  it('should show plan status indicator for pending workflows with plan', async () => {
    const plannedWorkflow: WorkflowSummary = {
      ...pendingWorkflow,
      id: 'wf-planned',
    };
    const plannedWorkflowDetail: WorkflowDetail = {
      ...pendingWorkflowDetail,
      id: 'wf-planned',
      plan_markdown: '# Plan\n\nThis is the plan.',
    };

    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [plannedWorkflow],
      detail: plannedWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    // Look for plan indicator
    const planIndicator = await screen.findByText(/plan ready/i);
    expect(planIndicator).toBeInTheDocument();
  });

  it('should not show Start/Cancel buttons for non-pending workflows', async () => {
    const runningWorkflow: WorkflowSummary = {
      ...pendingWorkflow,
      id: 'wf-running',
      status: 'in_progress',
      started_at: new Date().toISOString(),
    };
    const runningWorkflowDetail: WorkflowDetail = {
      ...pendingWorkflowDetail,
      id: 'wf-running',
      status: 'in_progress',
      started_at: new Date().toISOString(),
    };

    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [runningWorkflow],
      detail: runningWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    // Wait for the workflow to render - use findAllByText since text may appear multiple times
    const issueElements = await screen.findAllByText('ISSUE-123');
    expect(issueElements.length).toBeGreaterThan(0);

    // Start/Cancel buttons should not be present (only shown for pending workflows)
    expect(screen.queryByRole('button', { name: /^start$/i })).not.toBeInTheDocument();
  });
});

describe('WorkflowsPage planning status', () => {
  const planningWorkflow: WorkflowSummary = {
    id: 'wf-planning',
    issue_id: 'ISSUE-456',
    worktree_path: '/tmp/worktrees/repo',
    profile: null,
    status: 'pending',
    created_at: '2025-12-07T08:55:00Z',
    started_at: null,
    current_stage: 'architect',
    total_cost_usd: null,
    total_tokens: null,
    total_duration_ms: null,
  };

  const planningWorkflowDetail: WorkflowDetail = {
    ...planningWorkflow,
    worktree_path: '/path/to/repo',
    completed_at: null,
    failure_reason: null,
    token_usage: null,
    recent_events: [],
    goal: null,
    plan_markdown: null,
    plan_path: null,
  };

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [],
      detail: null,
      detailError: null,
    });
  });

  it('should show PlanningIndicator when status is planning', async () => {
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [planningWorkflow],
      detail: planningWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    // PlanningIndicator should be shown with "PLANNING" heading
    // Use findByRole with heading role since PlanningIndicator renders h4
    const planningIndicator = await screen.findByRole('heading', { name: 'PLANNING' });
    expect(planningIndicator).toBeInTheDocument();

    // Should show the architect analyzing message
    expect(screen.getByText(/Architect is analyzing/)).toBeInTheDocument();
  });

  it('should NOT show PendingWorkflowControls when status is planning', async () => {
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [planningWorkflow],
      detail: planningWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    // Wait for PlanningIndicator to appear
    // Use findByRole with heading role since PlanningIndicator renders h4
    await screen.findByRole('heading', { name: 'PLANNING' });

    // PendingWorkflowControls should NOT be shown (no QUEUED WORKFLOW heading)
    expect(screen.queryByText('QUEUED WORKFLOW')).not.toBeInTheDocument();

    // Start button should NOT be present (Start button is in PendingWorkflowControls)
    expect(screen.queryByRole('button', { name: /^start$/i })).not.toBeInTheDocument();
  });

  it('should show PendingWorkflowControls when status is pending (not planning)', async () => {
    const pendingWorkflow: WorkflowSummary = {
      ...planningWorkflow,
      id: 'wf-pending',
      status: 'pending',
      current_stage: null,
    };
    const pendingWorkflowDetail: WorkflowDetail = {
      ...planningWorkflowDetail,
      id: 'wf-pending',
      status: 'pending',
      current_stage: null,
    };

    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [pendingWorkflow],
      detail: pendingWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    // Should show QUEUED WORKFLOW heading (from PendingWorkflowControls)
    const queuedHeading = await screen.findByText('QUEUED WORKFLOW');
    expect(queuedHeading).toBeInTheDocument();

    // Should NOT show PLANNING heading (PlanningIndicator)
    expect(screen.queryByText('PLANNING')).not.toBeInTheDocument();
  });

  it('should not block worktree for planning workflows', async () => {
    // Scenario: One workflow is planning, another pending workflow is on the same worktree
    // The pending workflow should still be able to start (planning doesn't block)
    const pendingWorkflow: WorkflowSummary = {
      id: 'wf-pending',
      issue_id: 'ISSUE-789',
      worktree_path: '/tmp/worktrees/repo',
      profile: null,
      status: 'pending',
      created_at: '2025-12-07T09:00:00Z',
      started_at: null,
      current_stage: null,
      total_cost_usd: null,
      total_tokens: null,
      total_duration_ms: null,
    };
    const pendingWorkflowDetail: WorkflowDetail = {
      ...pendingWorkflow,
      worktree_path: '/tmp/worktrees/repo',
      completed_at: null,
      failure_reason: null,
      token_usage: null,
      recent_events: [],
      goal: null,
      plan_markdown: null,
      plan_path: null,
    };

    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [planningWorkflow, pendingWorkflow],
      detail: pendingWorkflowDetail,
      detailError: null,
    });

    renderWithRouter(<WorkflowsPage />);

    // Start button should be enabled (planning workflow doesn't block the worktree)
    const startButton = await screen.findByRole('button', { name: /start/i });
    expect(startButton).not.toBeDisabled();
  });
});
