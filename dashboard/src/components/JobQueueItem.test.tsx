import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JobQueueItem } from './JobQueueItem';
import { createMockWorkflowSummary } from '@/__tests__/fixtures';

describe('JobQueueItem', () => {
  const mockWorkflow = createMockWorkflowSummary({
    id: 'wf-001',
    issue_id: '#8',
    worktree_name: 'feature-benchmark',
    status: 'in_progress',
    current_stage: 'Developer',
  });

  it('renders issue ID and worktree name', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
    expect(screen.getByText('feature-benchmark')).toBeInTheDocument();
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

  it.each([
    { interaction: 'click', trigger: (el: Element) => fireEvent.click(el) },
    { interaction: 'Enter key', trigger: (el: Element) => fireEvent.keyDown(el, { key: 'Enter' }) },
  ])('calls onSelect on $interaction', ({ trigger }) => {
    const onSelect = vi.fn();
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={onSelect} />);
    trigger(screen.getByRole('button'));
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });
});
