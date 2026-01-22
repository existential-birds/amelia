import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { JobQueueItem } from './JobQueueItem';
import { createMockWorkflowSummary } from '@/__tests__/fixtures';

describe('JobQueueItem', () => {
  const mockWorkflow = createMockWorkflowSummary({
    id: 'wf-001',
    issue_id: '#8',
    worktree_path: '/tmp/worktrees/feature-benchmark',
    status: 'in_progress',
    current_stage: 'Developer',
  });

  it('renders issue ID and repo name (extracted from worktree path)', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
    // New design shows repo name extracted from path, not full path
    expect(screen.getByText('feature-benchmark')).toBeInTheDocument();
  });

  it('renders status label inline', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    // New design uses inline status text instead of StatusBadge
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
  });

  it('renders current stage when available', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    expect(screen.getByText('Developer')).toBeInTheDocument();
  });

  it('shows selected state with data-selected attribute', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={true} onSelect={() => {}} />);
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('data-selected', 'true');
  });

  it('calls onSelect on click', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={onSelect} />);
    await user.click(screen.getByRole('button'));
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('calls onSelect on Enter key (native button behavior)', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={onSelect} />);
    const button = screen.getByRole('button');
    button.focus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('calls onSelect on Space key (native button behavior)', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={onSelect} />);
    const button = screen.getByRole('button');
    button.focus();
    await user.keyboard(' ');
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('handles empty worktree_path gracefully', () => {
    const workflow = createMockWorkflowSummary({ worktree_path: '' });
    render(<JobQueueItem workflow={workflow} selected={false} onSelect={() => {}} />);
    // Should show 'unknown' instead of empty string or crashing
    expect(screen.getByText('unknown')).toBeInTheDocument();
  });

  it('handles root path worktree_path gracefully', () => {
    const workflow = createMockWorkflowSummary({ worktree_path: '/' });
    render(<JobQueueItem workflow={workflow} selected={false} onSelect={() => {}} />);
    expect(screen.getByText('unknown')).toBeInTheDocument();
  });
});
