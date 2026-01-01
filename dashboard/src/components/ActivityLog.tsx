/**
 * @fileoverview Real-time activity log for workflow events.
 */
import { useEffect, useRef, useMemo } from 'react';
import { Radio, RadioTower, Zap } from 'lucide-react';
import { ActivityLogItem } from '@/components/ActivityLogItem';
import { useWorkflowStore } from '@/store/workflowStore';
import { useStreamStore } from '@/store/stream-store';
import { cn, formatTime } from '@/lib/utils';
import { AGENT_STYLES } from '@/lib/constants';
import type { WorkflowEvent, StreamEvent } from '@/types';

/**
 * Props for the ActivityLog component.
 * @property workflowId - ID of the workflow to display events for
 * @property initialEvents - Events loaded from server (SSR/loader)
 * @property className - Optional additional CSS classes
 */
interface ActivityLogProps {
  workflowId: string;
  initialEvents?: WorkflowEvent[];
  className?: string;
}

/**
 * Unified log entry type that can represent either a workflow event or a stream event.
 *
 * Used internally by ActivityLog to merge and sort events from different sources
 * (loader data vs WebSocket streams) into a single chronological timeline.
 */
type LogEntry =
  | { kind: 'workflow'; event: WorkflowEvent }
  | { kind: 'stream'; event: StreamEvent };

/**
 * Component to render stream events in the activity log.
 * Displays stream events with a distinctive visual style to differentiate from workflow events.
 *
 * @param props - Component props.
 * @param props.event - The stream event to display.
 * @returns A div element containing the formatted stream log entry with timestamp, agent badge, and content.
 */
function StreamLogEntry({ event }: { event: StreamEvent }) {
  const agentKey = event.agent.toUpperCase();
  const style = AGENT_STYLES[agentKey] ?? { text: 'text-muted-foreground', bg: '' };

  return (
    <div
      data-slot="stream-log-item"
      className={cn(
        'relative grid grid-cols-[100px_120px_1fr] gap-3 py-1.5 border-b border-border/30 font-mono text-sm bg-primary/5',
        style.bg
      )}
    >
      <Zap className="absolute -left-4 top-1/2 -translate-y-1/2 w-3 h-3 text-primary" aria-hidden="true" />
      <span className="text-muted-foreground tabular-nums">
        {formatTime(event.timestamp)}
      </span>
      <span className={cn('font-semibold', style.text)}>
        [{agentKey}]
      </span>
      <span className="text-foreground/80 break-words">
        {event.tool_name ? `→ ${event.tool_name}` : event.content || event.subtype}
      </span>
    </div>
  );
}

/**
 * Displays a scrollable log of workflow events with real-time updates.
 *
 * Merges initial server-loaded events with real-time WebSocket events,
 * deduplicating by event ID. Auto-scrolls to bottom when new events arrive.
 * Includes terminal-style scanlines overlay for visual effect.
 *
 * When live mode is enabled, also shows stream events (thinking, tool calls, etc.)
 * interleaved with workflow events in chronological order.
 *
 * @param props - Component props
 * @returns The activity log UI
 *
 * @example
 * ```tsx
 * <ActivityLog
 *   workflowId="wf-123"
 *   initialEvents={loaderData.events}
 * />
 * ```
 */
export function ActivityLog({ workflowId, initialEvents = [], className }: ActivityLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Real-time events from WebSocket (via Zustand store)
  const { eventsByWorkflow } = useWorkflowStore();

  // Stream store for live mode and stream events
  const streamEvents = useStreamStore((state) => state.events);
  const liveMode = useStreamStore((state) => state.liveMode);
  const setLiveMode = useStreamStore((state) => state.setLiveMode);

  // Merge: loader events + any new real-time events (deduplicated by id)
  const workflowEvents = useMemo(() => {
    const realtimeEvents = eventsByWorkflow[workflowId] || [];
    const loaderEventIds = new Set(initialEvents.map(e => e.id));
    const newEvents = realtimeEvents.filter(e => !loaderEventIds.has(e.id));
    return [...initialEvents, ...newEvents];
  }, [initialEvents, eventsByWorkflow, workflowId]);

  // Build unified log entries by merging workflow and stream events
  const logEntries: LogEntry[] = useMemo(() => {
    // Start with workflow events
    const entries: LogEntry[] = workflowEvents.map(event => ({ kind: 'workflow' as const, event }));

    // If live mode is enabled, add stream events for this workflow
    if (liveMode) {
      const workflowStreamEvents = streamEvents.filter(e => e.workflow_id === workflowId);
      entries.push(...workflowStreamEvents.map(event => ({ kind: 'stream' as const, event })));
    }

    // Sort all entries by timestamp, with id as secondary sort for stability
    return entries.sort((a, b) => {
      const timeA = new Date(a.event.timestamp).getTime();
      const timeB = new Date(b.event.timestamp).getTime();
      const timeDiff = timeA - timeB;
      if (timeDiff !== 0) return timeDiff;
      return a.event.id.localeCompare(b.event.id);
    });
  }, [workflowEvents, streamEvents, liveMode, workflowId]);

  // Auto-scroll to bottom when new events arrive
  // Note: scrollIntoView check needed because jsdom doesn't implement it
  useEffect(() => {
    if (scrollRef.current?.scrollIntoView) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logEntries.length]);

  return (
    <div
      data-slot="activity-log"
      className={cn('flex flex-col', className)}
    >
      <div className="sticky top-0 z-20 flex items-center justify-between px-4 py-2 border-b border-border bg-background">
        <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground">
          ACTIVITY LOG
        </h3>
        <div className="flex items-center gap-3">
          {/* Live mode toggle - uses different icons for a11y (color-blind users) */}
          <button
            type="button"
            onClick={() => setLiveMode(!liveMode)}
            className={cn(
              'flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-colors',
              liveMode
                ? 'bg-primary/20 text-primary'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            )}
            aria-pressed={liveMode}
            title={liveMode ? 'Hide live stream events' : 'Show live stream events'}
          >
            {liveMode ? (
              <RadioTower className="w-3 h-3 animate-pulse" aria-hidden="true" />
            ) : (
              <Radio className="w-3 h-3" aria-hidden="true" />
            )}
            {liveMode ? 'Live' : 'Paused'}
          </button>

          <span className="font-mono text-xs text-muted-foreground">
            {logEntries.length} events
          </span>
        </div>
      </div>

      <div
        role="log"
        aria-live="polite"
        aria-label="Workflow activity log"
        className="p-4 relative"
      >
        {/* Scanlines overlay for terminal aesthetic */}
        <div
          className="absolute inset-0 pointer-events-none opacity-30 z-10"
          style={{
            background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.015) 2px, rgba(255,255,255,0.015) 4px)',
          }}
          aria-hidden="true"
        />

        {logEntries.length === 0 ? (
          <p className="text-center text-muted-foreground py-8">
            No activity yet
          </p>
        ) : (
          <div className="relative z-0 space-y-0">
            {logEntries.map((entry) => (
              entry.kind === 'workflow' ? (
                <ActivityLogItem key={`workflow-${entry.event.id}`} event={entry.event} />
              ) : (
                <StreamLogEntry key={`stream-${entry.event.id}`} event={entry.event} />
              )
            ))}

            {/* Blinking cursor */}
            <div className="mt-2 font-mono text-primary animate-blink" aria-hidden="true">
              _
            </div>

            {/* Scroll anchor */}
            <div ref={scrollRef} />
          </div>
        )}
      </div>
    </div>
  );
}
