import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it.each([
    { status: 'in_progress' as const, label: 'RUNNING' },
    { status: 'completed' as const, label: 'DONE' },
    { status: 'pending' as const, label: 'QUEUED' },
    { status: 'blocked' as const, label: 'BLOCKED' },
    { status: 'failed' as const, label: 'FAILED' },
  ])('renders $label for $status status', ({ status, label }) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('has proper ARIA role and label', () => {
    render(<StatusBadge status="in_progress" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'Workflow status: running');
  });

  it('applies data-status attribute for running status', () => {
    render(<StatusBadge status="in_progress" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('data-status', 'running');
  });
});
