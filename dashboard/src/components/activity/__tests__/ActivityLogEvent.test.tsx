import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityLogEvent } from '../ActivityLogEvent';
import type { WorkflowEvent } from '@/types';

const makeEvent = (overrides: Partial<WorkflowEvent> = {}): WorkflowEvent => ({
  id: 'evt-1',
  workflow_id: 'wf-1',
  sequence: 1,
  timestamp: '2025-01-01T12:30:45Z',
  agent: 'developer',
  event_type: 'task_started',
  level: 'debug',
  message: 'Started implementation task',
  ...overrides,
});

describe('ActivityLogEvent', () => {
  it('renders event message', () => {
    render(<ActivityLogEvent event={makeEvent()} />);
    expect(screen.getByText('Started implementation task')).toBeInTheDocument();
  });

  it('renders formatted timestamp', () => {
    render(<ActivityLogEvent event={makeEvent()} />);
    // Should show time portion
    expect(screen.getByText(/12:30:45/)).toBeInTheDocument();
  });

  it('renders agent name', () => {
    render(<ActivityLogEvent event={makeEvent({ agent: 'architect' })} />);
    expect(screen.getByText('ARCHITECT')).toBeInTheDocument();
  });
});
