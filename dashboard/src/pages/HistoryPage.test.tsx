import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HistoryPage from './HistoryPage';
import { createMockWorkflowSummary } from '@/__tests__/fixtures';
import type { WorkflowSummary } from '@/types';

// Mock loader data
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
    useNavigate: () => vi.fn(),
  };
});

import { useLoaderData } from 'react-router-dom';

const mockWorkflows: WorkflowSummary[] = [
  createMockWorkflowSummary({
    id: 'wf-001',
    issue_id: 'PROJ-123',
    worktree_path: '/tmp/worktrees/proj-123-feature',
    status: 'completed',
    created_at: '2025-12-07T08:55:00Z',
    started_at: '2025-12-07T09:00:00Z',
    total_duration_ms: 154000, // 2m 34s
    total_tokens: 15200, // 15.2K
    total_cost_usd: 0.42, // $0.42
  }),
  createMockWorkflowSummary({
    id: 'wf-002',
    issue_id: 'PROJ-124',
    worktree_path: '/tmp/worktrees/proj-124-bugfix',
    status: 'failed',
    created_at: '2025-12-07T07:55:00Z',
    started_at: '2025-12-07T08:00:00Z',
    total_duration_ms: null,
    total_tokens: null,
    total_cost_usd: null,
  }),
];

/** Render HistoryPage with mock loader data */
function renderHistory(workflows: WorkflowSummary[] = mockWorkflows) {
  vi.mocked(useLoaderData).mockReturnValue({ workflows });
  return render(
    <MemoryRouter>
      <HistoryPage />
    </MemoryRouter>
  );
}

describe('HistoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render completed workflows list', () => {
    renderHistory();

    expect(screen.getByText('PROJ-123')).toBeInTheDocument();
    expect(screen.getByText('PROJ-124')).toBeInTheDocument();
  });

  it('should show empty state when no history', () => {
    renderHistory([]);

    expect(screen.getByText(/no activity yet/i)).toBeInTheDocument();
  });

  it('should display workflow status badges', () => {
    renderHistory();

    expect(screen.getByText('DONE')).toBeInTheDocument();
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });

  it('should display duration, tokens, and cost when available', () => {
    renderHistory();

    // First workflow has all values
    expect(screen.getByText('2m 34s')).toBeInTheDocument();
    expect(screen.getByText('15.2K')).toBeInTheDocument();
    expect(screen.getByText('$0.42')).toBeInTheDocument();
  });

  it('should display "-" when duration, tokens, or cost are null', () => {
    renderHistory();

    // Second workflow has null values - should show "-" for each
    const dashElements = screen.getAllByText('-');
    expect(dashElements.length).toBeGreaterThanOrEqual(3);
  });
});
