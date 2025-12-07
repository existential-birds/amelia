/**
 * @fileoverview Real-time activity log for workflow events.
 */
import { useEffect, useRef, useMemo } from 'react';
import { ActivityLogItem } from '@/components/ActivityLogItem';
import { useWorkflowStore } from '@/store/workflowStore';
import { cn } from '@/lib/utils';
import type { WorkflowEvent } from '@/types';

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
 * Displays a scrollable log of workflow events with real-time updates.
 *
 * Merges initial server-loaded events with real-time WebSocket events,
 * deduplicating by event ID. Auto-scrolls to bottom when new events arrive.
 * Includes terminal-style scanlines overlay for visual effect.
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

  // Merge: loader events + any new real-time events (deduplicated by id)
  const events = useMemo(() => {
    const realtimeEvents = eventsByWorkflow[workflowId] || [];
    const loaderEventIds = new Set(initialEvents.map(e => e.id));
    const newEvents = realtimeEvents.filter(e => !loaderEventIds.has(e.id));
    return [...initialEvents, ...newEvents];
  }, [initialEvents, eventsByWorkflow, workflowId]);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (scrollRef.current && scrollRef.current.scrollIntoView) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [events.length]);

  return (
    <div
      data-slot="activity-log"
      className={cn('flex flex-col h-full', className)}
    >
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
        <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground">
          ACTIVITY LOG
        </h3>
        <span className="font-mono text-xs text-muted-foreground">
          {events.length} events
        </span>
      </div>

      <div
        role="log"
        aria-live="polite"
        aria-label="Workflow activity log"
        className="flex-1 overflow-y-auto p-4 relative"
      >
        {/* Scanlines overlay for terminal aesthetic */}
        <div
          className="absolute inset-0 pointer-events-none opacity-30 z-10"
          style={{
            background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.015) 2px, rgba(255,255,255,0.015) 4px)',
          }}
          aria-hidden="true"
        />

        {events.length === 0 ? (
          <p className="text-center text-muted-foreground py-8">
            No activity yet
          </p>
        ) : (
          <div className="relative z-0 space-y-0">
            {events.map((event) => (
              <ActivityLogItem key={event.id} event={event} />
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
