import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowHeader } from './WorkflowHeader';

describe('WorkflowHeader', () => {
  const mockWorkflow = {
    id: 'wf-001',
    issue_id: '#8',
    worktree_name: 'feature-benchmark',
    status: 'in_progress' as const,
  };

  it('renders issue ID', () => {
    render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
  });

  it('renders worktree name', () => {
    render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(screen.getByText('feature-benchmark')).toBeInTheDocument();
  });

  it('renders StatusBadge', () => {
    render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(screen.getByRole('status')).toHaveTextContent('RUNNING');
  });

  it('has proper semantic structure with banner role', () => {
    render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('shows elapsed time when provided', () => {
    render(<WorkflowHeader workflow={mockWorkflow} elapsedTime="2:34" />);
    expect(screen.getByText('2:34')).toBeInTheDocument();
  });

  it('has data-slot attribute', () => {
    const { container } = render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(container.querySelector('[data-slot="workflow-header"]')).toBeInTheDocument();
  });
});
