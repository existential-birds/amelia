/**
 * @fileoverview Logs monitoring page - real-time trace event viewer.
 *
 * Displays trace-level events (thinking, tool calls, tool results, agent output)
 * across all workflows with filtering and auto-scroll.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  ArrowDown,
  Trash2,
  Brain,
  Wrench,
  CheckCircle,
  MessageSquare,
  Filter,
} from 'lucide-react';
import Markdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/button';
import { useWorkflowStore } from '@/store/workflowStore';
import { cn, formatTime } from '@/lib/utils';
import type { WorkflowEvent, EventType } from '@/types';

/**
 * Trace event types that are displayed in the logs page.
 */
const TRACE_EVENT_TYPES: EventType[] = [
  'claude_thinking',
  'claude_tool_call',
  'claude_tool_result',
  'agent_output',
];

/**
 * Type for trace event filter values.
 */
type TraceEventType = 'claude_thinking' | 'claude_tool_call' | 'claude_tool_result' | 'agent_output';

/**
 * Icon mapping for different trace event types.
 */
const eventTypeIcons: Record<TraceEventType, React.ReactNode> = {
  claude_thinking: <Brain className="w-4 h-4 text-yellow-500" />,
  claude_tool_call: <Wrench className="w-4 h-4 text-blue-500" />,
  claude_tool_result: <CheckCircle className="w-4 h-4 text-green-500" />,
  agent_output: <MessageSquare className="w-4 h-4 text-purple-500" />,
};

/**
 * Background color classes for different trace event types.
 * Using 20% opacity for backgrounds to ensure visibility against dark themes.
 */
const eventTypeColors: Record<TraceEventType, string> = {
  claude_thinking: 'bg-yellow-500/20 border-yellow-500/30',
  claude_tool_call: 'bg-blue-500/20 border-blue-500/30',
  claude_tool_result: 'bg-green-500/20 border-green-500/30',
  agent_output: 'bg-purple-500/20 border-purple-500/30',
};

/**
 * Type guard to check if an event type is a trace event type.
 */
function isTraceEventType(eventType: EventType): eventType is TraceEventType {
  return TRACE_EVENT_TYPES.includes(eventType);
}

/**
 * Formats tool input for display, showing key parameters concisely.
 * Truncates long values to 100 characters for readability.
 *
 * @param toolInput - The tool input object containing key-value pairs
 * @returns Formatted string of key-value pairs separated by commas
 */
function formatToolInput(toolInput: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(toolInput)) {
    if (value === null || value === undefined) continue;
    const strValue = typeof value === 'string' ? value : JSON.stringify(value);
    // Truncate long values
    const displayValue = strValue.length > 100 ? strValue.slice(0, 100) + '...' : strValue;
    parts.push(`${key}: ${displayValue}`);
  }
  return parts.join(', ');
}

/**
 * Individual trace log event item component.
 * Displays a trace event with icon, timestamp, agent name, and content.
 * Uses color-coded backgrounds based on event type.
 *
 * @param props - Component props
 * @param props.event - The workflow event to display
 * @returns React element for the trace log item
 */
function TraceLogItem({ event }: { event: WorkflowEvent }) {
  if (!isTraceEventType(event.event_type)) return null;

  return (
    <div
      data-testid={`event-${event.id}`}
      data-event-type={event.event_type}
      className={cn(
        'flex items-start gap-3 px-3 py-2 rounded border',
        eventTypeColors[event.event_type]
      )}
    >
      <div className="mt-0.5">{eventTypeIcons[event.event_type]}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono tabular-nums">
            {formatTime(event.timestamp)}
          </span>
          <span className="font-semibold uppercase">{event.agent}</span>
          {event.model && (
            <span className="text-muted-foreground/70 font-mono text-[10px]">
              {event.model}
            </span>
          )}
          {event.tool_name && (
            <span className="text-blue-400">→ {event.tool_name}</span>
          )}
        </div>
        {event.tool_input && Object.keys(event.tool_input).length > 0 && (
          <div className="mt-1 text-xs text-muted-foreground/80 font-mono">
            {formatToolInput(event.tool_input)}
          </div>
        )}
        {event.message && (
          <div className="mt-1 prose prose-sm prose-invert max-w-none prose-p:my-1 prose-p:first:mt-0 prose-p:last:mb-0 prose-headings:text-foreground prose-p:text-foreground/80 prose-strong:text-foreground prose-code:text-accent prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-li:text-foreground/80 [&_pre]:whitespace-pre-wrap [&_code]:break-all">
            <Markdown remarkPlugins={[remarkBreaks]}>{event.message}</Markdown>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Logs monitoring page component.
 *
 * Displays real-time trace events from all workflows with filtering,
 * auto-scroll, and event type differentiation. Shows thinking tokens,
 * tool calls, tool results, and agent outputs.
 *
 * @returns The logs page UI with trace event viewer
 */
/** Estimated row height for virtualization */
const ESTIMATED_ROW_HEIGHT = 60;

export default function LogsPage() {
  const eventsByWorkflow = useWorkflowStore((state) => state.eventsByWorkflow);

  const parentRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [typeFilter, setTypeFilter] = useState<TraceEventType | 'all'>('all');

  // Collect and filter trace events from all workflows
  const traceEvents = useMemo(() => {
    const allEvents: WorkflowEvent[] = [];
    for (const events of Object.values(eventsByWorkflow)) {
      for (const event of events) {
        if (event.level === 'trace' && isTraceEventType(event.event_type)) {
          allEvents.push(event);
        }
      }
    }
    // Sort by timestamp, most recent last
    return allEvents.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }, [eventsByWorkflow]);

  // Filter events by type if filter is active
  const filteredEvents =
    typeFilter === 'all'
      ? traceEvents
      : traceEvents.filter((e) => e.event_type === typeFilter);

  // Clear events function (resets store for all workflows)
  const clearEvents = useCallback(() => {
    useWorkflowStore.setState({
      eventsByWorkflow: {},
      eventIdsByWorkflow: {},
    });
  }, []);

  // Virtualizer for efficient rendering of large event lists
  // Uses dynamic measurement for accurate row heights (content varies with markdown)
  const rowVirtualizer = useVirtualizer({
    count: filteredEvents.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 5,
  });

  // Get measureElement ref for dynamic row height measurement
  const measureElement = rowVirtualizer.measureElement;

  // Auto-scroll to bottom when new events arrive (if already at bottom)
  useEffect(() => {
    if (isAtBottom && filteredEvents.length > 0) {
      rowVirtualizer.scrollToIndex(filteredEvents.length - 1, {
        behavior: 'smooth',
      });
    }
  }, [filteredEvents.length, isAtBottom, rowVirtualizer]);

  // Track scroll position to determine if user is at bottom
  const handleScroll = useCallback(() => {
    if (!parentRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = parentRef.current;
    setIsAtBottom(scrollHeight - scrollTop - clientHeight < 50);
  }, []);

  const scrollToBottom = useCallback(() => {
    if (filteredEvents.length > 0) {
      rowVirtualizer.scrollToIndex(filteredEvents.length - 1, {
        behavior: 'smooth',
      });
    }
    setIsAtBottom(true);
  }, [filteredEvents.length, rowVirtualizer]);

  return (
    <div className="flex flex-col h-full w-full">
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>MONITORING</PageHeader.Label>
          <PageHeader.Title>Logs</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Right>
          {/* Filter dropdown */}
          <select
            aria-label="Filter by event type"
            value={typeFilter}
            onChange={(e) =>
              setTypeFilter(e.target.value as TraceEventType | 'all')
            }
            className="bg-background border rounded px-2 py-1 text-sm outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
          >
            <option value="all">All Events</option>
            <option value="claude_thinking">Thinking</option>
            <option value="claude_tool_call">Tool Calls</option>
            <option value="claude_tool_result">Tool Results</option>
            <option value="agent_output">Agent Output</option>
          </select>

          <span className="text-sm text-muted-foreground">
            {filteredEvents.length} {filteredEvents.length === 1 ? 'event' : 'events'}
          </span>

          <Button variant="outline" size="sm" onClick={clearEvents}>
            <Trash2 className="w-4 h-4 mr-1" />
            Clear
          </Button>
        </PageHeader.Right>
      </PageHeader>

      <div
        ref={parentRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 relative"
      >
        {filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <Filter className="w-12 h-12 mb-4 opacity-50" />
            <p>No trace events yet</p>
            <p className="text-sm">Events will appear here as workflows run</p>
          </div>
        ) : (
          <div
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const event = filteredEvents[virtualRow.index];
              if (!event) return null;

              return (
                <div
                  key={event.id}
                  ref={measureElement}
                  data-index={virtualRow.index}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <div className="pb-2">
                    <TraceLogItem event={event} />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Scroll to bottom button */}
        {!isAtBottom && filteredEvents.length > 0 && (
          <Button
            variant="secondary"
            size="sm"
            className="absolute bottom-4 right-4 shadow-lg"
            onClick={scrollToBottom}
          >
            <ArrowDown className="w-4 h-4 mr-1" />
            Scroll to bottom
          </Button>
        )}
      </div>
    </div>
  );
}

// No loader needed for logs page
