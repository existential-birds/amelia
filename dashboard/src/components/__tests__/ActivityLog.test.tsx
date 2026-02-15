import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActivityLog } from '../ActivityLog';
import type { WorkflowEvent } from '@/types';

// Mock the stores - return a function that applies selectors to mock state
const mockStoreState = { eventsByWorkflow: {} as Record<string, unknown[]> };
vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: <T,>(selector?: (state: typeof mockStoreState) => T): T =>
    selector ? selector(mockStoreState) : (mockStoreState as unknown as T),
}));

// Mock useVirtualizer to render all items (JSDOM doesn't support scroll dimensions)
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count, estimateSize }: { count: number; estimateSize: (index: number) => number }) => {
    const items = Array.from({ length: count }, (_, index) => ({
      index,
      key: index,
      size: estimateSize(index),
      start: Array.from({ length: index }, (_, i) => estimateSize(i)).reduce((a, b) => a + b, 0),
    }));
    return {
      getVirtualItems: () => items,
      getTotalSize: () => items.reduce((acc, item) => acc + item.size, 0),
      scrollToIndex: vi.fn(),
      measureElement: () => undefined,
    };
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

const makeEvent = (overrides: Partial<WorkflowEvent>): WorkflowEvent => ({
  id: 'evt-1',
  workflow_id: 'wf-test',
  sequence: 1,
  timestamp: '2025-01-01T00:00:00Z',
  agent: 'developer',
  event_type: 'task_started',
  level: 'debug',
  message: 'Test event',
  ...overrides,
});

describe('ActivityLog', () => {
  it('renders stage headers', () => {
    const events = [
      makeEvent({ id: '1', agent: 'architect', event_type: 'stage_started', level: 'info' }),
    ];

    render(<ActivityLog workflowId="wf-test" initialEvents={events} />);

    expect(screen.getByText('Planning (Architect)')).toBeInTheDocument();
  });

  it('renders debug events alongside info events', () => {
    const events = [
      makeEvent({ id: '1', level: 'info', message: 'Info event' }),
      makeEvent({ id: '2', level: 'debug', message: 'Debug event', event_type: 'task_started' }),
    ];

    render(<ActivityLog workflowId="wf-test" initialEvents={events} />);

    expect(screen.getByText('Info event')).toBeInTheDocument();
    expect(screen.getByText('Debug event')).toBeInTheDocument();
  });

  it('collapses stage when header clicked', () => {
    const events = [
      makeEvent({ id: '1', agent: 'architect', event_type: 'stage_started', level: 'info' }),
      makeEvent({ id: '2', agent: 'architect', message: 'Detail event', level: 'debug' }),
    ];

    render(<ActivityLog workflowId="wf-test" initialEvents={events} />);

    // Event should be visible initially
    expect(screen.getByText('Detail event')).toBeInTheDocument();

    // Click to collapse
    fireEvent.click(screen.getByText('Planning (Architect)'));

    // Event should be hidden
    expect(screen.queryByText('Detail event')).not.toBeInTheDocument();
  });

  it('does not have Live toggle', () => {
    render(<ActivityLog workflowId="wf-test" initialEvents={[]} />);

    expect(screen.queryByText(/live/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });
});
