import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HistoryPage from './HistoryPage';
import type { WorkflowSummary } from '@/types';

const mockWorkflows: WorkflowSummary[] = [
  {
    id: 'wf-001',
    issue_id: 'PROJ-123',
    worktree_name: 'proj-123-feature',
    status: 'completed',
    started_at: '2025-12-07T09:00:00Z',
    current_stage: null,
  },
  {
    id: 'wf-002',
    issue_id: 'PROJ-124',
    worktree_name: 'proj-124-bugfix',
    status: 'failed',
    started_at: '2025-12-07T08:00:00Z',
    current_stage: null,
  },
];

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

describe('HistoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render completed workflows list', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: mockWorkflows });

    render(
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    );

    expect(screen.getByText('PROJ-123')).toBeInTheDocument();
    expect(screen.getByText('PROJ-124')).toBeInTheDocument();
  });

  it('should show empty state when no history', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });

    render(
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/no activity yet/i)).toBeInTheDocument();
  });

  it('should display workflow status badges', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: mockWorkflows });

    render(
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    );

    expect(screen.getByText('DONE')).toBeInTheDocument();
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });
});
