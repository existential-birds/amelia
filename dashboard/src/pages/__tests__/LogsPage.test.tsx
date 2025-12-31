import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import LogsPage from '../LogsPage';
import { useStreamStore } from '../../store/stream-store';
import { StreamEventType, type StreamEvent } from '../../types';

// Helper to wrap component with Router
const renderWithRouter = (ui: React.ReactElement) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

// Helper to create mock stream events
const createStreamEvent = (
  subtype: StreamEventType,
  overrides?: Partial<StreamEvent>
): StreamEvent => ({
  id: `stream-${crypto.randomUUID()}`,
  subtype,
  content: subtype === StreamEventType.CLAUDE_THINKING ? 'Test thinking content' : null,
  timestamp: new Date().toISOString(),
  agent: 'developer',
  workflow_id: 'wf-123',
  tool_name: subtype === StreamEventType.CLAUDE_TOOL_CALL ? 'test_tool' : null,
  tool_input: subtype === StreamEventType.CLAUDE_TOOL_CALL ? { arg: 'value' } : null,
  ...overrides,
});

describe('LogsPage', () => {
  beforeEach(() => {
    // Reset store before each test
    useStreamStore.setState({
      events: [],
      liveMode: false,
      maxEvents: 1000,
    });
  });

  it('renders empty state when no events', () => {
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/no stream events yet/i)).toBeInTheDocument();
    expect(screen.getByText(/events will appear here as workflows run/i)).toBeInTheDocument();
  });

  it('renders stream events from store', () => {
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_THINKING, {
        content: 'Analyzing requirements...',
      }),
      createStreamEvent(StreamEventType.CLAUDE_TOOL_CALL, {
        tool_name: 'read_file',
      }),
    ];

    useStreamStore.setState({ events });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/analyzing requirements/i)).toBeInTheDocument();
    expect(screen.getByText(/read_file/i)).toBeInTheDocument();
  });

  it('displays event count indicator', () => {
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_THINKING),
      createStreamEvent(StreamEventType.AGENT_OUTPUT),
    ];

    useStreamStore.setState({ events });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/2 events/i)).toBeInTheDocument();
  });

  it('filters events by type', () => {
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_THINKING, {
        content: 'Thinking event content',
      }),
      createStreamEvent(StreamEventType.AGENT_OUTPUT, {
        content: 'Agent output content',
      }),
    ];

    useStreamStore.setState({ events });
    renderWithRouter(<LogsPage />);

    // Find and click filter dropdown
    const filterSelect = screen.getByDisplayValue(/all events/i);
    fireEvent.change(filterSelect, { target: { value: StreamEventType.CLAUDE_THINKING } });

    // Should only show thinking event content (not the dropdown option)
    expect(screen.getByText(/thinking event content/i)).toBeInTheDocument();
    expect(screen.queryByText(/agent output content/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 event/i)).toBeInTheDocument();
  });

  it('clears events when clear button is clicked', () => {
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_THINKING),
    ];

    useStreamStore.setState({ events });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/1 event/i)).toBeInTheDocument();

    // Click clear button
    const clearButton = screen.getByRole('button', { name: /clear/i });
    fireEvent.click(clearButton);

    // Should now show empty state
    expect(screen.getByText(/no stream events yet/i)).toBeInTheDocument();
  });

  it('displays correct icon for each event type', () => {
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_THINKING),
      createStreamEvent(StreamEventType.CLAUDE_TOOL_CALL),
      createStreamEvent(StreamEventType.CLAUDE_TOOL_RESULT),
      createStreamEvent(StreamEventType.AGENT_OUTPUT),
    ];

    useStreamStore.setState({ events });
    const { container } = renderWithRouter(<LogsPage />);

    // Lucide icons render with predictable class names (lucide-{icon-name})
    expect(container.querySelector('.lucide-brain')).toBeInTheDocument();
    expect(container.querySelector('.lucide-wrench')).toBeInTheDocument();
    expect(container.querySelector('.lucide-circle-check-big')).toBeInTheDocument();
    expect(container.querySelector('.lucide-message-square')).toBeInTheDocument();
  });

  it('shows agent name in event item', () => {
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_THINKING, {
        agent: 'architect',
        content: 'Planning the implementation',
      }),
    ];

    useStreamStore.setState({ events });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/\[architect\]/i)).toBeInTheDocument();
  });

  it('formats timestamp correctly', () => {
    const timestamp = '2025-12-13T10:30:45.123Z';
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_THINKING, {
        timestamp,
        content: 'Test content',
      }),
    ];

    useStreamStore.setState({ events });
    renderWithRouter(<LogsPage />);

    // Formatted time should be HH:MM:SS.mmm (11 chars from the ISO string)
    expect(screen.getByText(/10:30:45.123/)).toBeInTheDocument();
  });

  it('displays tool name for tool call events', () => {
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_TOOL_CALL, {
        tool_name: 'execute_command',
      }),
    ];

    useStreamStore.setState({ events });
    renderWithRouter(<LogsPage />);

    expect(screen.getByText(/execute_command/i)).toBeInTheDocument();
  });

  it('renders all event types with correct data attributes', () => {
    const events: StreamEvent[] = [
      createStreamEvent(StreamEventType.CLAUDE_THINKING, {
        content: 'Thinking',
      }),
      createStreamEvent(StreamEventType.CLAUDE_TOOL_CALL),
      createStreamEvent(StreamEventType.CLAUDE_TOOL_RESULT),
      createStreamEvent(StreamEventType.AGENT_OUTPUT, {
        content: 'Output',
      }),
    ];

    useStreamStore.setState({ events });
    const { container } = renderWithRouter(<LogsPage />);

    // Verify each event type is rendered with stable data-event-type attribute
    expect(container.querySelector('[data-event-type="claude_thinking"]')).toBeInTheDocument();
    expect(container.querySelector('[data-event-type="claude_tool_call"]')).toBeInTheDocument();
    expect(container.querySelector('[data-event-type="claude_tool_result"]')).toBeInTheDocument();
    expect(container.querySelector('[data-event-type="agent_output"]')).toBeInTheDocument();
  });

  describe('markdown rendering', () => {
    it('renders markdown headers as HTML heading elements', () => {
      const events: StreamEvent[] = [
        createStreamEvent(StreamEventType.CLAUDE_THINKING, {
          content: '## Header Level 2\n\nSome paragraph text',
        }),
      ];

      useStreamStore.setState({ events });
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
      const events: StreamEvent[] = [
        createStreamEvent(StreamEventType.AGENT_OUTPUT, {
          content: '**bold text** and `inline code`',
        }),
      ];

      useStreamStore.setState({ events });
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
      const events: StreamEvent[] = [
        createStreamEvent(StreamEventType.CLAUDE_THINKING, {
          content: '```javascript\nconst x = 1;\nconsole.log(x);\n```',
        }),
      ];

      useStreamStore.setState({ events });
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
      const events: StreamEvent[] = [
        createStreamEvent(StreamEventType.AGENT_OUTPUT, {
          content: '- item 1\n- item 2\n- item 3',
        }),
      ];

      useStreamStore.setState({ events });
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
      const events: StreamEvent[] = [
        createStreamEvent(StreamEventType.CLAUDE_THINKING, {
          content: '1. First step\n2. Second step\n3. Third step',
        }),
      ];

      useStreamStore.setState({ events });
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
      const events: StreamEvent[] = [
        createStreamEvent(StreamEventType.AGENT_OUTPUT, {
          content: 'Check out [this link](https://example.com) for more info',
        }),
      ];

      useStreamStore.setState({ events });
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
      const events: StreamEvent[] = [
        createStreamEvent(StreamEventType.CLAUDE_THINKING, {
          content: 'First line\nSecond line\nThird line',
        }),
      ];

      useStreamStore.setState({ events });
      const { container } = renderWithRouter(<LogsPage />);

      // With remark-breaks, single newlines become <br> elements
      const brElements = container.querySelectorAll('br');
      expect(brElements.length).toBeGreaterThanOrEqual(2);
    });

    it('renders complex markdown with multiple elements', () => {
      const events: StreamEvent[] = [
        createStreamEvent(StreamEventType.CLAUDE_THINKING, {
          content: `## Analysis Complete

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

      useStreamStore.setState({ events });
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
