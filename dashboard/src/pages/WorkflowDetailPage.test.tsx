import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import WorkflowDetailPage from './WorkflowDetailPage';
import type { WorkflowDetail } from '@/types';

// Mock data matching actual WorkflowDetail type
const mockWorkflow: WorkflowDetail = {
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_name: 'proj-123-feature',
  worktree_path: '/tmp/worktrees/proj-123',
  status: 'in_progress',
  started_at: '2025-12-07T09:00:00Z',
  completed_at: null,
  current_stage: 'developer',
  failure_reason: null,
  plan: {
    tasks: [
      { id: 't1', description: 'Setup', agent: 'developer', dependencies: [], status: 'completed' },
      { id: 't2', description: 'Implement', agent: 'developer', dependencies: ['t1'], status: 'in_progress' },
    ],
    execution_order: ['t1', 't2'],
  },
  token_usage: {},
  recent_events: [],
};

// Mock loader data
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
  };
});

import { useLoaderData } from 'react-router-dom';

describe('WorkflowDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render workflow header with issue_id', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflow: mockWorkflow });

    render(
      <MemoryRouter>
        <WorkflowDetailPage />
      </MemoryRouter>
    );

    expect(screen.getByText('PROJ-123')).toBeInTheDocument();
  });

  it('should render workflow progress', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflow: mockWorkflow });

    render(
      <MemoryRouter>
        <WorkflowDetailPage />
      </MemoryRouter>
    );

    // WorkflowProgress uses data-slot="workflow-progress"
    expect(document.querySelector('[data-slot="workflow-progress"]')).toBeInTheDocument();
  });

  it('should render activity log', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflow: mockWorkflow });

    render(
      <MemoryRouter>
        <WorkflowDetailPage />
      </MemoryRouter>
    );

    expect(document.querySelector('[data-slot="activity-log"]')).toBeInTheDocument();
  });
});
