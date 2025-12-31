/**
 * @fileoverview Logs monitoring page - real-time stream event viewer.
 *
 * Displays all stream events across workflows with filtering and auto-scroll.
 */

import { useState, useEffect, useRef } from 'react';
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
import { useStreamStore } from '@/store/stream-store';
import { StreamEventType, type StreamEvent } from '@/types';
import { cn, formatTime } from '@/lib/utils';

/**
 * Icon mapping for different stream event types.
 */
const eventTypeIcons: Record<StreamEventType, React.ReactNode> = {
  [StreamEventType.CLAUDE_THINKING]: (
    <Brain className="w-4 h-4 text-yellow-500" />
  ),
  [StreamEventType.CLAUDE_TOOL_CALL]: (
    <Wrench className="w-4 h-4 text-blue-500" />
  ),
  [StreamEventType.CLAUDE_TOOL_RESULT]: (
    <CheckCircle className="w-4 h-4 text-green-500" />
  ),
  [StreamEventType.AGENT_OUTPUT]: (
    <MessageSquare className="w-4 h-4 text-purple-500" />
  ),
};

/**
 * Background color classes for different stream event types.
 */
const eventTypeColors: Record<StreamEventType, string> = {
  [StreamEventType.CLAUDE_THINKING]: 'bg-yellow-500/10 border-yellow-500/20',
  [StreamEventType.CLAUDE_TOOL_CALL]: 'bg-blue-500/10 border-blue-500/20',
  [StreamEventType.CLAUDE_TOOL_RESULT]: 'bg-green-500/10 border-green-500/20',
  [StreamEventType.AGENT_OUTPUT]: 'bg-purple-500/10 border-purple-500/20',
};

/**
 * Individual stream log event item component.
 *
 * @param props - Component props
 * @param props.event - The stream event to display
 * @returns The rendered stream log item
 */
/**
 * Formats tool input for display, showing key parameters concisely.
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

function StreamLogItem({ event }: { event: StreamEvent }) {
  return (
    <div
      data-testid={`event-${event.id}`}
      data-event-type={event.subtype}
      className={cn(
        'flex items-start gap-3 px-3 py-2 rounded border',
        eventTypeColors[event.subtype]
      )}
    >
      <div className="mt-0.5">{eventTypeIcons[event.subtype]}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono tabular-nums">
            {formatTime(event.timestamp)}
          </span>
          <span className="font-semibold uppercase">[{event.agent}]</span>
          {event.tool_name && (
            <span className="text-blue-400">→ {event.tool_name}</span>
          )}
        </div>
        {event.tool_input && Object.keys(event.tool_input).length > 0 && (
          <div className="mt-1 text-xs text-muted-foreground/80 font-mono">
            {formatToolInput(event.tool_input)}
          </div>
        )}
        {event.content && (
          <div className="mt-1 prose prose-sm prose-invert max-w-none prose-p:my-1 prose-p:first:mt-0 prose-p:last:mb-0 prose-headings:text-foreground prose-p:text-foreground/80 prose-strong:text-foreground prose-code:text-accent prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-li:text-foreground/80 [&_pre]:whitespace-pre-wrap [&_code]:break-all">
            <Markdown remarkPlugins={[remarkBreaks]}>{event.content}</Markdown>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Logs monitoring page component.
 *
 * Displays real-time stream events from all workflows with filtering,
 * auto-scroll, and event type differentiation. Shows thinking tokens,
 * tool calls, tool results, and agent outputs.
 *
 * @returns The logs page UI with stream event viewer
 */
export default function LogsPage() {
  const events = useStreamStore((state) => state.events);
  const clearEvents = useStreamStore((state) => state.clearEvents);

  const scrollRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [typeFilter, setTypeFilter] = useState<StreamEventType | 'all'>('all');

  // Filter events
  const filteredEvents =
    typeFilter === 'all' ? events : events.filter((e) => e.subtype === typeFilter);

  // Auto-scroll when at bottom
  useEffect(() => {
    if (isAtBottom && scrollRef.current?.scrollIntoView) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [filteredEvents.length, isAtBottom]);

  // Track scroll position
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    setIsAtBottom(scrollHeight - scrollTop - clientHeight < 50);
  };

  const scrollToBottom = () => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
    setIsAtBottom(true);
  };

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
            value={typeFilter}
            onChange={(e) =>
              setTypeFilter(e.target.value as StreamEventType | 'all')
            }
            className="bg-background border rounded px-2 py-1 text-sm outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
          >
            <option value="all">All Events</option>
            <option value={StreamEventType.CLAUDE_THINKING}>Thinking</option>
            <option value={StreamEventType.CLAUDE_TOOL_CALL}>Tool Calls</option>
            <option value={StreamEventType.CLAUDE_TOOL_RESULT}>
              Tool Results
            </option>
            <option value={StreamEventType.AGENT_OUTPUT}>Agent Output</option>
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
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 relative"
      >
        {filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <Filter className="w-12 h-12 mb-4 opacity-50" />
            <p>No stream events yet</p>
            <p className="text-sm">Events will appear here as workflows run</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredEvents.map((event) => (
              <StreamLogItem
                key={event.id}
                event={event}
              />
            ))}
            <div ref={scrollRef} />
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
