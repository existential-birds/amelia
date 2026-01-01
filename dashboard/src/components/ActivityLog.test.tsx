import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ActivityLog } from './ActivityLog';
import * as workflowStore from '@/store/workflowStore';
import * as streamStore from '@/store/stream-store';
import { createMockEvent, createMockStreamEvent } from '@/__tests__/fixtures';
import { StreamEventType } from '@/types';

vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn(() => ({
    eventsByWorkflow: {},
  })),
}));

vi.mock('@/store/stream-store', () => ({
  useStreamStore: vi.fn((selector) => {
    const state = {
      events: [],
      liveMode: false,
      setLiveMode: vi.fn(),
    };
    return selector ? selector(state) : state;
  }),
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

    vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
      const state = {
        events: [],
        liveMode: false,
        setLiveMode: vi.fn(),
      };
      return selector ? selector(state) : state;
    });
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

  describe('Live Mode Toggle', () => {
    it('renders live mode toggle button', () => {
      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
      // When live mode is off, button shows "Paused"
      const toggle = screen.getByRole('button', { name: /paused/i });
      expect(toggle).toBeInTheDocument();
      expect(toggle).toHaveAttribute('aria-pressed', 'false');
    });

    it('calls setLiveMode when toggle is clicked', async () => {
      const user = userEvent.setup();
      const mockSetLiveMode = vi.fn();

      vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
        const state = {
          events: [],
          liveMode: false,
          setLiveMode: mockSetLiveMode,
        };
        return selector ? selector(state) : state;
      });

      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
      // When live mode is off, button shows "Paused"
      const toggle = screen.getByRole('button', { name: /paused/i });

      await user.click(toggle);

      expect(mockSetLiveMode).toHaveBeenCalledWith(true);
    });

    it('shows stream events when live mode is enabled', () => {
      const streamEvent = createMockStreamEvent({
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:32:20Z',
        subtype: StreamEventType.CLAUDE_THINKING,
        content: 'Analyzing requirements...',
        agent: 'architect',
      });

      vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
        const state = {
          events: [streamEvent],
          liveMode: true,
          setLiveMode: vi.fn(),
        };
        return selector ? selector(state) : state;
      });

      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

      expect(screen.getByText(/Analyzing requirements/)).toBeInTheDocument();
      expect(screen.getByText('3 events')).toBeInTheDocument(); // 2 workflow + 1 stream
    });

    it('does not show stream events when live mode is disabled', () => {
      const streamEvent = createMockStreamEvent({
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:32:20Z',
        subtype: StreamEventType.CLAUDE_THINKING,
        content: 'Analyzing requirements...',
        agent: 'architect',
      });

      vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
        const state = {
          events: [streamEvent],
          liveMode: false,
          setLiveMode: vi.fn(),
        };
        return selector ? selector(state) : state;
      });

      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

      expect(screen.queryByText(/Analyzing requirements/)).not.toBeInTheDocument();
      expect(screen.getByText('2 events')).toBeInTheDocument(); // Only workflow events
    });

    it('filters stream events by workflow_id', () => {
      const streamEvent1 = createMockStreamEvent({
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:32:20Z',
        content: 'Event for wf-001',
      });

      const streamEvent2 = createMockStreamEvent({
        workflow_id: 'wf-002',
        timestamp: '2025-12-01T14:32:25Z',
        content: 'Event for wf-002',
      });

      vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
        const state = {
          events: [streamEvent1, streamEvent2],
          liveMode: true,
          setLiveMode: vi.fn(),
        };
        return selector ? selector(state) : state;
      });

      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

      expect(screen.getByText(/Event for wf-001/)).toBeInTheDocument();
      expect(screen.queryByText(/Event for wf-002/)).not.toBeInTheDocument();
      expect(screen.getByText('3 events')).toBeInTheDocument(); // 2 workflow + 1 stream
    });

    it('sorts stream and workflow events by timestamp', () => {
      const streamEvent1 = createMockStreamEvent({
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:32:15Z', // Between the two workflow events
        content: 'Stream event in the middle',
        subtype: StreamEventType.CLAUDE_THINKING,
      });

      vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
        const state = {
          events: [streamEvent1],
          liveMode: true,
          setLiveMode: vi.fn(),
        };
        return selector ? selector(state) : state;
      });

      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

      // Get all log items
      const logContainer = screen.getByRole('log');
      const logItems = logContainer.querySelectorAll('[data-slot="activity-log-item"], [data-slot="stream-log-item"]');

      // Verify order: evt-001 (14:32:07), stream (14:32:15), evt-002 (14:32:45)
      expect(logItems).toHaveLength(3);
      expect(logItems[0]).toHaveTextContent(/Issue #8 parsed/);
      expect(logItems[1]).toHaveTextContent(/Stream event in the middle/);
      expect(logItems[2]).toHaveTextContent(/Plan approved/);
    });

    it('shows tool calls in stream events', () => {
      const toolCallEvent = createMockStreamEvent({
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:32:20Z',
        subtype: StreamEventType.CLAUDE_TOOL_CALL,
        content: null,
        tool_name: 'read_file',
        tool_input: { path: '/src/main.py' },
      });

      vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
        const state = {
          events: [toolCallEvent],
          liveMode: true,
          setLiveMode: vi.fn(),
        };
        return selector ? selector(state) : state;
      });

      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

      expect(screen.getByText(/→ read_file/)).toBeInTheDocument();
    });

    it('visually distinguishes stream events from workflow events', () => {
      const streamEvent = createMockStreamEvent({
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:32:20Z',
        content: 'Stream event',
      });

      vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
        const state = {
          events: [streamEvent],
          liveMode: true,
          setLiveMode: vi.fn(),
        };
        return selector ? selector(state) : state;
      });

      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

      // Stream events should have the stream-log-item data slot
      const streamLogItem = screen.getByText(/Stream event/).closest('[data-slot="stream-log-item"]');
      expect(streamLogItem).toBeInTheDocument();
    });

    it('toggle button shows pressed state when live mode is enabled', () => {
      vi.mocked(streamStore.useStreamStore).mockImplementation((selector: any) => {
        const state = {
          events: [],
          liveMode: true,
          setLiveMode: vi.fn(),
        };
        return selector ? selector(state) : state;
      });

      render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

      const toggle = screen.getByRole('button', { name: /live/i });
      expect(toggle).toHaveAttribute('aria-pressed', 'true');
    });
  });
});
