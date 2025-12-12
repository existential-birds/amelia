import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JobQueue } from './JobQueue';
import { createMockWorkflowSummary } from '@/__tests__/fixtures';

describe('JobQueue', () => {
  const mockWorkflows = [
    createMockWorkflowSummary({ id: 'wf-001', issue_id: '#8', worktree_name: 'feature-a', status: 'in_progress', current_stage: 'Developer' }),
    createMockWorkflowSummary({ id: 'wf-002', issue_id: '#7', worktree_name: 'feature-b', status: 'completed', current_stage: null }),
    createMockWorkflowSummary({ id: 'wf-003', issue_id: '#9', worktree_name: 'feature-c', status: 'pending', current_stage: null }),
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

  it('highlights selected workflow', () => {
    render(<JobQueue workflows={mockWorkflows} selectedId="wf-001" />);
    const selectedButton = screen.getByText('#8').closest('button');
    expect(selectedButton).toHaveAttribute('data-selected', 'true');
  });

  it('calls onSelect when workflow is clicked', () => {
    const onSelect = vi.fn();
    render(<JobQueue workflows={mockWorkflows} onSelect={onSelect} />);

    const button = screen.getByText('#8').closest('button');
    expect(button).not.toBeNull();
    fireEvent.click(button!);
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('shows empty state when no workflows', () => {
    render(<JobQueue workflows={[]} />);
    expect(screen.getByText(/No active workflows/)).toBeInTheDocument();
  });
});
