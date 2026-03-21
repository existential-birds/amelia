/**
 * @fileoverview Tests for WorkflowsPage pending workflow actions.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import WorkflowsPage from '../WorkflowsPage';
import { api } from '../../api/client';
import { createMockWorkflowSummary, createMockWorkflowDetail } from '@/__tests__/fixtures';
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

const pendingWorkflow = createMockWorkflowSummary({
  id: 'wf-pending',
  issue_id: 'ISSUE-123',
  worktree_path: '/tmp/worktrees/repo',
  status: 'pending',
  started_at: null,
});

const pendingWorkflowDetail = createMockWorkflowDetail({
  id: 'wf-pending',
  issue_id: 'ISSUE-123',
  worktree_path: '/path/to/repo',
  status: 'pending',
  started_at: null,
  goal: null,
});

/** Render WorkflowsPage with mock loader data */
function renderPage(
  workflows: WorkflowSummary[] = [],
  detail: WorkflowDetail | null = null,
) {
  vi.mocked(useLoaderData).mockReturnValue({
    workflows,
    detail,
    detailError: null,
  });
  return render(
    <MemoryRouter>
      <WorkflowsPage />
    </MemoryRouter>
  );
}

describe('WorkflowsPage pending workflow actions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useLoaderData).mockReturnValue({
      workflows: [],
      detail: null,
      detailError: null,
    });
  });

  it('should show Start button for pending workflows', async () => {
    renderPage([pendingWorkflow], pendingWorkflowDetail);

    const startButton = await screen.findByRole('button', { name: /start/i });
    expect(startButton).toBeInTheDocument();
  });

  it('should show Cancel button for pending workflows', async () => {
    renderPage([pendingWorkflow], pendingWorkflowDetail);

    const cancelButton = await screen.findByRole('button', { name: /cancel/i });
    expect(cancelButton).toBeInTheDocument();
  });

  it('should call startWorkflow when Start clicked', async () => {
    vi.mocked(api.startWorkflow).mockResolvedValue({
      workflow_id: 'wf-pending',
      status: 'started',
    });

    renderPage([pendingWorkflow], pendingWorkflowDetail);

    const startButton = await screen.findByRole('button', { name: /start/i });
    fireEvent.click(startButton);

    await waitFor(() => {
      expect(api.startWorkflow).toHaveBeenCalledWith('wf-pending');
    });
  });

  it('should show "queued" for pending workflows', async () => {
    renderPage([pendingWorkflow], pendingWorkflowDetail);

    // Look for the "queued" text in the pending workflow controls section
    const queuedElements = await screen.findAllByText(/queued/i);
    expect(queuedElements.length).toBeGreaterThan(0);
    // At least one should be the status text in the PendingWorkflowControls
    expect(queuedElements.some(el => el.className.includes('text-muted-foreground'))).toBe(true);
  });

  it('should show plan status indicator for pending workflows with plan', async () => {
    const plannedWorkflow = createMockWorkflowSummary({
      ...pendingWorkflow,
      id: 'wf-planned',
    });
    const plannedWorkflowDetail = createMockWorkflowDetail({
      ...pendingWorkflowDetail,
      id: 'wf-planned',
      plan_markdown: '# Plan\n\nThis is the plan.',
    });

    renderPage([plannedWorkflow], plannedWorkflowDetail);

    // Look for plan indicator
    const planIndicator = await screen.findByText(/plan ready/i);
    expect(planIndicator).toBeInTheDocument();
  });

  it('should not show Start/Cancel buttons for non-pending workflows', async () => {
    const runningWorkflow = createMockWorkflowSummary({
      id: 'wf-running',
      issue_id: 'ISSUE-123',
      status: 'in_progress',
      started_at: new Date().toISOString(),
    });
    const runningWorkflowDetail = createMockWorkflowDetail({
      id: 'wf-running',
      issue_id: 'ISSUE-123',
      status: 'in_progress',
      started_at: new Date().toISOString(),
    });

    renderPage([runningWorkflow], runningWorkflowDetail);

    // Wait for the workflow to render
    const issueElements = await screen.findAllByText('ISSUE-123');
    expect(issueElements.length).toBeGreaterThan(0);

    // Start/Cancel buttons should not be present (only shown for pending workflows)
    expect(screen.queryByRole('button', { name: /^start$/i })).not.toBeInTheDocument();
  });
});
