import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityLogItem } from './ActivityLogItem';

describe('ActivityLogItem', () => {
  const mockEvent = {
    id: 'evt-001',
    workflow_id: 'wf-001',
    sequence: 1,
    timestamp: '2025-12-01T14:32:07Z',
    agent: 'ARCHITECT',
    event_type: 'stage_started' as const,
    message: 'Issue #8 parsed. Creating task DAG for benchmark framework.',
  };

  it('renders timestamp in HH:MM:SS format', () => {
    render(<ActivityLogItem event={mockEvent} />);
    expect(screen.getByText('14:32:07')).toBeInTheDocument();
  });

  it('renders agent name in brackets', () => {
    render(<ActivityLogItem event={mockEvent} />);
    expect(screen.getByText('[ARCHITECT]')).toBeInTheDocument();
  });

  it('renders message text', () => {
    render(<ActivityLogItem event={mockEvent} />);
    expect(screen.getByText(/Issue #8 parsed/)).toBeInTheDocument();
  });

  it('applies correct agent color class for ARCHITECT', () => {
    render(<ActivityLogItem event={mockEvent} />);
    const agent = screen.getByText('[ARCHITECT]');
    expect(agent).toHaveClass('text-accent');
  });

  it('applies correct agent color class for DEVELOPER', () => {
    const developerEvent = { ...mockEvent, agent: 'DEVELOPER' };
    render(<ActivityLogItem event={developerEvent} />);
    const agent = screen.getByText('[DEVELOPER]');
    expect(agent).toHaveClass('text-primary');
  });

  it('has data-slot attribute', () => {
    const { container } = render(<ActivityLogItem event={mockEvent} />);
    expect(container.querySelector('[data-slot="activity-log-item"]')).toBeInTheDocument();
  });
});
