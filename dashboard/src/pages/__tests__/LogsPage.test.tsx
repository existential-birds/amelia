/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

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
});
