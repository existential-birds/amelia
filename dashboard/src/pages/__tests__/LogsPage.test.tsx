import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import LogsPage from '../LogsPage';
import { useWorkflowStore } from '../../store/workflowStore';
import type { WorkflowEvent, EventType } from '../../types';

// Mock useVirtualizer to render all items (JSDOM doesn't support scroll dimensions)
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({
    count,
    estimateSize,
  }: {
    count: number;
    estimateSize: () => number;
  }) => {
    const size = estimateSize();
    const items = Array.from({ length: count }, (_, index) => ({
      index,
      key: index,
      size,
      start: index * size,
    }));
    return {
      getVirtualItems: () => items,
      getTotalSize: () => count * size,
      scrollToIndex: vi.fn(),
      measureElement: () => undefined,
    };
  },
}));

// Helper to wrap component with Router
const renderWithRouter = (ui: React.ReactElement) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

// Helper to create mock trace events (WorkflowEvent with level: 'trace')
const createTraceEvent = (
  eventType: EventType,
  overrides?: Partial<WorkflowEvent>
): WorkflowEvent => ({
  id: `evt-${crypto.randomUUID()}`,
  workflow_id: 'wf-123',
  sequence: 1,
  timestamp: new Date().toISOString(),
  agent: 'developer',
  event_type: eventType,
  level: 'trace',
  message: eventType === 'claude_thinking' ? 'Test thinking content' : 'Test message',
  tool_name: eventType === 'claude_tool_call' ? 'test_tool' : undefined,
  tool_input: eventType === 'claude_tool_call' ? { arg: 'value' } : undefined,
  ...overrides,
});

describe('LogsPage', () => {
  beforeEach(() => {
    // Reset store before each test
    useWorkflowStore.setState({
      eventsByWorkflow: {},
      eventIdsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: [],
    });
  });

  it('renders empty state when no events', () => {
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/no trace events yet/i)).toBeInTheDocument();
    expect(screen.getByText(/events will appear here as workflows run/i)).toBeInTheDocument();
  });

  it('renders trace events from store', () => {
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_thinking', {
        message: 'Analyzing requirements...',
      }),
      createTraceEvent('claude_tool_call', {
        tool_name: 'read_file',
      }),
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/analyzing requirements/i)).toBeInTheDocument();
    expect(screen.getByText(/read_file/i)).toBeInTheDocument();
  });

  it('displays event count indicator', () => {
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_thinking'),
      createTraceEvent('agent_output'),
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/2 events/i)).toBeInTheDocument();
  });

  it('filters events by type', () => {
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_thinking', {
        message: 'Thinking event content',
      }),
      createTraceEvent('agent_output', {
        message: 'Agent output content',
      }),
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    renderWithRouter(<LogsPage />);

    // Find and click filter dropdown
    const filterSelect = screen.getByDisplayValue(/all events/i);
    fireEvent.change(filterSelect, { target: { value: 'claude_thinking' } });

    // Should only show thinking event content (not the dropdown option)
    expect(screen.getByText(/thinking event content/i)).toBeInTheDocument();
    expect(screen.queryByText(/agent output content/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 event/i)).toBeInTheDocument();
  });

  it('clears events when clear button is clicked', () => {
    const events: WorkflowEvent[] = [createTraceEvent('claude_thinking')];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/1 event/i)).toBeInTheDocument();

    // Click clear button
    const clearButton = screen.getByRole('button', { name: /clear/i });
    fireEvent.click(clearButton);

    // Should now show empty state
    expect(screen.getByText(/no trace events yet/i)).toBeInTheDocument();
  });

  it('displays correct icon for each event type', () => {
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_thinking'),
      createTraceEvent('claude_tool_call'),
      createTraceEvent('claude_tool_result'),
      createTraceEvent('agent_output'),
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    const { container } = renderWithRouter(<LogsPage />);

    // Lucide icons render with predictable class names (lucide-{icon-name})
    expect(container.querySelector('.lucide-brain')).toBeInTheDocument();
    expect(container.querySelector('.lucide-wrench')).toBeInTheDocument();
    expect(container.querySelector('.lucide-circle-check-big')).toBeInTheDocument();
    expect(container.querySelector('.lucide-message-square')).toBeInTheDocument();
  });

  it('shows agent name in event item', () => {
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_thinking', {
        agent: 'architect',
        message: 'Planning the implementation',
      }),
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/architect/i)).toBeInTheDocument();
  });

  it('formats timestamp correctly', () => {
    const timestamp = '2025-12-13T10:30:45.123Z';
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_thinking', {
        timestamp,
        message: 'Test content',
      }),
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    renderWithRouter(<LogsPage />);

    // Formatted time should be HH:MM:SS (8 chars from the ISO string)
    expect(screen.getByText(/10:30:45/)).toBeInTheDocument();
  });

  it('displays tool name for tool call events', () => {
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_tool_call', {
        tool_name: 'execute_command',
      }),
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/execute_command/i)).toBeInTheDocument();
  });

  it('renders all event types with correct data attributes', () => {
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_thinking', {
        message: 'Thinking',
      }),
      createTraceEvent('claude_tool_call'),
      createTraceEvent('claude_tool_result'),
      createTraceEvent('agent_output', {
        message: 'Output',
      }),
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    const { container } = renderWithRouter(<LogsPage />);

    // Verify each event type is rendered with stable data-event-type attribute
    expect(container.querySelector('[data-event-type="claude_thinking"]')).toBeInTheDocument();
    expect(container.querySelector('[data-event-type="claude_tool_call"]')).toBeInTheDocument();
    expect(container.querySelector('[data-event-type="claude_tool_result"]')).toBeInTheDocument();
    expect(container.querySelector('[data-event-type="agent_output"]')).toBeInTheDocument();
  });

  it('only displays trace-level events', () => {
    const events: WorkflowEvent[] = [
      createTraceEvent('claude_thinking', { message: 'Trace event' }),
      {
        id: 'evt-info-1',
        workflow_id: 'wf-123',
        sequence: 2,
        timestamp: new Date().toISOString(),
        agent: 'developer',
        event_type: 'stage_started',
        level: 'info',
        message: 'Info level event',
      },
      {
        id: 'evt-debug-1',
        workflow_id: 'wf-123',
        sequence: 3,
        timestamp: new Date().toISOString(),
        agent: 'developer',
        event_type: 'file_modified',
        level: 'debug',
        message: 'Debug level event',
      },
    ];

    useWorkflowStore.setState({
      eventsByWorkflow: { 'wf-123': events },
      eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
    });
    renderWithRouter(<LogsPage />);

    // Should only show trace event, not info or debug
    expect(screen.getByText(/trace event/i)).toBeInTheDocument();
    expect(screen.queryByText(/info level event/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/debug level event/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 event/i)).toBeInTheDocument();
  });

  describe('markdown rendering', () => {
    it('renders markdown headers as HTML heading elements', () => {
      const events: WorkflowEvent[] = [
        createTraceEvent('claude_thinking', {
          message: '## Header Level 2\n\nSome paragraph text',
        }),
      ];

      useWorkflowStore.setState({
        eventsByWorkflow: { 'wf-123': events },
        eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
      });
      const { container } = renderWithRouter(<LogsPage />);

      // Verify h2 element is rendered within the prose container (markdown content)
      // The page also has an h2 for "Logs" in the header, so we need to be specific
      const proseContainer = container.querySelector('.prose');
      expect(proseContainer).toBeInTheDocument();
      const heading = proseContainer?.querySelector('h2');
      expect(heading).toBeInTheDocument();
      expect(heading).toHaveTextContent('Header Level 2');
      // Ensure the raw markdown syntax is not visible
      expect(screen.queryByText(/^## Header/)).not.toBeInTheDocument();
    });

    it('renders bold and inline code markdown syntax as HTML', () => {
      const events: WorkflowEvent[] = [
        createTraceEvent('agent_output', {
          message: '**bold text** and `inline code`',
        }),
      ];

      useWorkflowStore.setState({
        eventsByWorkflow: { 'wf-123': events },
        eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
      });
      const { container } = renderWithRouter(<LogsPage />);

      // Verify strong element for bold
      const strongElement = container.querySelector('strong');
      expect(strongElement).toBeInTheDocument();
      expect(strongElement).toHaveTextContent('bold text');

      // Verify code element for inline code
      const codeElement = container.querySelector('code');
      expect(codeElement).toBeInTheDocument();
      expect(codeElement).toHaveTextContent('inline code');

      // Ensure raw markdown syntax is not visible
      expect(screen.queryByText(/\*\*bold text\*\*/)).not.toBeInTheDocument();
      expect(screen.queryByText(/`inline code`/)).not.toBeInTheDocument();
    });

    it('renders code blocks with pre and code elements', () => {
      const events: WorkflowEvent[] = [
        createTraceEvent('claude_thinking', {
          message: '```javascript\nconst x = 1;\nconsole.log(x);\n```',
        }),
      ];

      useWorkflowStore.setState({
        eventsByWorkflow: { 'wf-123': events },
        eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
      });
      const { container } = renderWithRouter(<LogsPage />);

      // Verify pre element exists for code block
      const preElement = container.querySelector('pre');
      expect(preElement).toBeInTheDocument();

      // Verify code element inside pre
      const codeElement = preElement?.querySelector('code');
      expect(codeElement).toBeInTheDocument();
      expect(codeElement).toHaveTextContent('const x = 1;');

      // Ensure raw backticks are not visible
      expect(screen.queryByText(/```/)).not.toBeInTheDocument();
    });

    it('renders unordered lists as ul/li elements', () => {
      const events: WorkflowEvent[] = [
        createTraceEvent('agent_output', {
          message: '- item 1\n- item 2\n- item 3',
        }),
      ];

      useWorkflowStore.setState({
        eventsByWorkflow: { 'wf-123': events },
        eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
      });
      const { container } = renderWithRouter(<LogsPage />);

      // Verify ul element exists
      const ulElement = container.querySelector('ul');
      expect(ulElement).toBeInTheDocument();

      // Verify list items
      const listItems = container.querySelectorAll('li');
      expect(listItems).toHaveLength(3);
      expect(listItems[0]).toHaveTextContent('item 1');
      expect(listItems[1]).toHaveTextContent('item 2');
      expect(listItems[2]).toHaveTextContent('item 3');

      // Ensure raw markdown list syntax is not visible
      expect(screen.queryByText(/^- item/)).not.toBeInTheDocument();
    });

    it('renders ordered lists as ol/li elements', () => {
      const events: WorkflowEvent[] = [
        createTraceEvent('claude_thinking', {
          message: '1. First step\n2. Second step\n3. Third step',
        }),
      ];

      useWorkflowStore.setState({
        eventsByWorkflow: { 'wf-123': events },
        eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
      });
      const { container } = renderWithRouter(<LogsPage />);

      // Verify ol element exists
      const olElement = container.querySelector('ol');
      expect(olElement).toBeInTheDocument();

      // Verify list items
      const listItems = container.querySelectorAll('li');
      expect(listItems).toHaveLength(3);
      expect(listItems[0]).toHaveTextContent('First step');
    });

    it('renders links as anchor elements', () => {
      const events: WorkflowEvent[] = [
        createTraceEvent('agent_output', {
          message: 'Check out [this link](https://example.com) for more info',
        }),
      ];

      useWorkflowStore.setState({
        eventsByWorkflow: { 'wf-123': events },
        eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
      });
      const { container } = renderWithRouter(<LogsPage />);

      // Verify anchor element exists with correct href
      const anchor = container.querySelector('a');
      expect(anchor).toBeInTheDocument();
      expect(anchor).toHaveTextContent('this link');
      expect(anchor).toHaveAttribute('href', 'https://example.com');

      // Ensure raw markdown link syntax is not visible
      expect(screen.queryByText(/\[this link\]/)).not.toBeInTheDocument();
    });

    it('preserves single line breaks in plain text content', () => {
      const events: WorkflowEvent[] = [
        createTraceEvent('claude_thinking', {
          message: 'First line\nSecond line\nThird line',
        }),
      ];

      useWorkflowStore.setState({
        eventsByWorkflow: { 'wf-123': events },
        eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
      });
      const { container } = renderWithRouter(<LogsPage />);

      // With remark-breaks, single newlines become <br> elements
      const brElements = container.querySelectorAll('br');
      expect(brElements.length).toBeGreaterThanOrEqual(2);
    });

    it('renders complex markdown with multiple elements', () => {
      const events: WorkflowEvent[] = [
        createTraceEvent('claude_thinking', {
          message: `## Analysis Complete

Here are the findings:

- **Issue 1**: Found a bug in \`utils.ts\`
- **Issue 2**: Missing error handling

\`\`\`typescript
function fix() {
  return true;
}
\`\`\``,
        }),
      ];

      useWorkflowStore.setState({
        eventsByWorkflow: { 'wf-123': events },
        eventIdsByWorkflow: { 'wf-123': new Set(events.map((e) => e.id)) },
      });
      const { container } = renderWithRouter(<LogsPage />);

      // Verify heading within prose container (page has "Logs" h2 in header)
      const proseContainer = container.querySelector('.prose');
      expect(proseContainer).toBeInTheDocument();
      expect(proseContainer?.querySelector('h2')).toHaveTextContent('Analysis Complete');

      // Verify list with bold and inline code
      expect(proseContainer?.querySelector('ul')).toBeInTheDocument();
      expect(proseContainer?.querySelectorAll('strong')).toHaveLength(2);
      expect(proseContainer?.querySelector('code:not(pre code)')).toHaveTextContent('utils.ts');

      // Verify code block
      expect(proseContainer?.querySelector('pre code')).toHaveTextContent('function fix()');
    });
  });
});
