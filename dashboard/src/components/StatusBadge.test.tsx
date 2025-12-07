import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders RUNNING label for in_progress status', () => {
    render(<StatusBadge status="in_progress" />);
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
  });

  it('renders DONE label for completed status', () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText('DONE')).toBeInTheDocument();
  });

  it('renders QUEUED label for pending status', () => {
    render(<StatusBadge status="pending" />);
    expect(screen.getByText('QUEUED')).toBeInTheDocument();
  });

  it('renders BLOCKED label for blocked status', () => {
    render(<StatusBadge status="blocked" />);
    expect(screen.getByText('BLOCKED')).toBeInTheDocument();
  });

  it('renders FAILED label for failed status', () => {
    render(<StatusBadge status="failed" />);
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });

  it('has proper ARIA role and label', () => {
    render(<StatusBadge status="in_progress" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'Workflow status: running');
  });

  it('applies data-status attribute for running status', () => {
    const { container } = render(<StatusBadge status="in_progress" />);
    expect(container.querySelector('[data-status="running"]')).toBeInTheDocument();
  });
});
