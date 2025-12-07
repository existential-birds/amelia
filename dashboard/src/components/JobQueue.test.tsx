import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JobQueue } from './JobQueue';

describe('JobQueue', () => {
  const mockWorkflows = [
    { id: 'wf-001', issue_id: '#8', worktree_name: 'feature-a', status: 'in_progress' as const, current_stage: 'Developer' },
    { id: 'wf-002', issue_id: '#7', worktree_name: 'feature-b', status: 'completed' as const, current_stage: null },
    { id: 'wf-003', issue_id: '#9', worktree_name: 'feature-c', status: 'pending' as const, current_stage: null },
  ];

  it('renders all workflows', () => {
    render(<JobQueue workflows={mockWorkflows} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
    expect(screen.getByText('#7')).toBeInTheDocument();
    expect(screen.getByText('#9')).toBeInTheDocument();
  });

  it('renders section label', () => {
    render(<JobQueue workflows={mockWorkflows} />);
    expect(screen.getByText('JOB QUEUE')).toBeInTheDocument();
  });

  it('shows workflow count', () => {
    render(<JobQueue workflows={mockWorkflows} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('highlights selected workflow', () => {
    const { container } = render(
      <JobQueue workflows={mockWorkflows} selectedId="wf-001" />
    );
    expect(container.querySelector('[data-selected="true"]')).toBeInTheDocument();
  });

  it('calls onSelect when workflow is clicked', () => {
    const onSelect = vi.fn();
    render(<JobQueue workflows={mockWorkflows} onSelect={onSelect} />);

    fireEvent.click(screen.getByText('#8').closest('[role="button"]')!);
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('shows empty state when no workflows', () => {
    render(<JobQueue workflows={[]} />);
    expect(screen.getByText(/No active workflows/)).toBeInTheDocument();
  });

  it('has data-slot attribute', () => {
    const { container } = render(<JobQueue workflows={mockWorkflows} />);
    expect(container.querySelector('[data-slot="job-queue"]')).toBeInTheDocument();
  });
});
