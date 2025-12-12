import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityLog } from './ActivityLog';
import * as workflowStore from '@/store/workflowStore';
import { createMockEvent } from '@/__tests__/fixtures';

vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn(() => ({
    eventsByWorkflow: {},
  })),
}));

describe('ActivityLog', () => {
  const mockEvents = [
    createMockEvent({
      id: 'evt-001',
      workflow_id: 'wf-001',
      sequence: 1,
      timestamp: '2025-12-01T14:32:07Z',
      agent: 'ARCHITECT',
      event_type: 'stage_started',
      message: 'Issue #8 parsed.',
    }),
    createMockEvent({
      id: 'evt-002',
      workflow_id: 'wf-001',
      sequence: 2,
      timestamp: '2025-12-01T14:32:45Z',
      agent: 'ARCHITECT',
      event_type: 'stage_completed',
      message: 'Plan approved.',
    }),
  ];

  beforeEach(() => {
    vi.mocked(workflowStore.useWorkflowStore).mockReturnValue({
      eventsByWorkflow: {},
    } as any);
  });

  it('renders section title', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(screen.getByText('ACTIVITY LOG')).toBeInTheDocument();
  });

  it('renders all initial events', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(screen.getByText(/Issue #8 parsed/)).toBeInTheDocument();
    expect(screen.getByText(/Plan approved/)).toBeInTheDocument();
  });

  it('merges loader events with real-time events from Zustand', () => {
    const realtimeEvent = createMockEvent({
      id: 'evt-003',
      workflow_id: 'wf-001',
      sequence: 3,
      timestamp: '2025-12-01T14:33:00Z',
      agent: 'DEVELOPER',
      event_type: 'stage_started',
      message: 'Starting implementation.',
    });

    vi.mocked(workflowStore.useWorkflowStore).mockReturnValue({
      eventsByWorkflow: { 'wf-001': [realtimeEvent] },
    } as any);

    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

    expect(screen.getByText(/Issue #8 parsed/)).toBeInTheDocument();
    expect(screen.getByText(/Starting implementation/)).toBeInTheDocument();
  });

  it('has proper ARIA role for log', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(screen.getByRole('log')).toHaveAttribute('aria-live', 'polite');
  });

  it('shows empty state when no events', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={[]} />);
    expect(screen.getByText(/No activity/)).toBeInTheDocument();
  });

  it('deduplicates events with same ID from initialEvents and real-time store', () => {
    const duplicateEvent = createMockEvent({
      id: 'evt-001',
      workflow_id: 'wf-001',
      sequence: 1,
      timestamp: '2025-12-01T14:32:07Z',
      agent: 'ARCHITECT',
      event_type: 'stage_started',
      message: 'Issue #8 parsed.',
    });

    vi.mocked(workflowStore.useWorkflowStore).mockReturnValue({
      eventsByWorkflow: { 'wf-001': [duplicateEvent] },
    } as any);

    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

    // Verify the event appears only once (not duplicated)
    const issueElements = screen.getAllByText(/Issue #8 parsed/);
    expect(issueElements).toHaveLength(1);

    // Verify event count shows 2 (initial events), not 3
    expect(screen.getByText('2 events')).toBeInTheDocument();
  });
});
