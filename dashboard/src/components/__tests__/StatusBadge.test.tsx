import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../StatusBadge';

describe('StatusBadge queued styling', () => {
  it('should display "QUEUED" label for pending status', () => {
    render(<StatusBadge status="pending" />);
    expect(screen.getByText('QUEUED')).toBeInTheDocument();
  });

  it('should have muted styling for queued status', () => {
    render(<StatusBadge status="pending" />);
    const badge = screen.getByText('QUEUED');
    // Check for status-pending variant class which uses muted colors
    expect(badge.className).toMatch(/status-pending/);
  });

  it('should have correct aria-label for pending status', () => {
    render(<StatusBadge status="pending" />);
    expect(screen.getByRole('status')).toHaveAttribute(
      'aria-label',
      'Workflow status: pending'
    );
  });

  it('should have data-status attribute for pending', () => {
    render(<StatusBadge status="pending" />);
    expect(screen.getByRole('status')).toHaveAttribute('data-status', 'pending');
  });
});

describe('StatusBadge other statuses', () => {
  it('should display "RUNNING" for in_progress status', () => {
    render(<StatusBadge status="in_progress" />);
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
  });

  it('should display "DONE" for completed status', () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText('DONE')).toBeInTheDocument();
  });

  it('should display "FAILED" for failed status', () => {
    render(<StatusBadge status="failed" />);
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });

  it('should display "BLOCKED" for blocked status', () => {
    render(<StatusBadge status="blocked" />);
    expect(screen.getByText('BLOCKED')).toBeInTheDocument();
  });

  it('should display "CANCELLED" for cancelled status', () => {
    render(<StatusBadge status="cancelled" />);
    expect(screen.getByText('CANCELLED')).toBeInTheDocument();
  });

  it('should show pulsing indicator for running status', () => {
    render(<StatusBadge status="in_progress" />);
    const badge = screen.getByRole('status');
    const indicator = badge.querySelector('span');
    expect(indicator?.className).toMatch(/animate-pulse/);
  });
});
