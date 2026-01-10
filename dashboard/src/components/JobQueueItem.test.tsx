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

  it('renders issue ID and worktree name', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
    expect(screen.getByText('/tmp/worktrees/feature-benchmark')).toBeInTheDocument();
  });

  it('renders status indicator via StatusBadge', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    expect(screen.getByRole('status')).toHaveTextContent('RUNNING');
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
});
