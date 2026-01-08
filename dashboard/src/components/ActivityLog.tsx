import { useRef, useState, useMemo, useEffect } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useWorkflowStore } from '@/store/workflowStore';
import {
  ActivityLogHeader,
  ActivityLogEvent,
  useActivityLogGroups,
} from './activity';
import type { WorkflowEvent } from '@/types';

interface ActivityLogProps {
  workflowId: string;
  initialEvents?: WorkflowEvent[];
}

export function ActivityLog({
  workflowId,
  initialEvents = [],
}: ActivityLogProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const [collapsedStages, setCollapsedStages] = useState<Set<string>>(
    new Set()
  );

  // Get realtime events from store
  const { eventsByWorkflow } = useWorkflowStore();

  // Merge initial events with realtime events
  const allEvents = useMemo(() => {
    const realtimeEvents = eventsByWorkflow[workflowId] || [];
    const initialIds = new Set(initialEvents.map((e) => e.id));
    const newEvents = realtimeEvents.filter((e) => !initialIds.has(e.id));
    return [...initialEvents, ...newEvents];
  }, [initialEvents, eventsByWorkflow, workflowId]);

  // Group events by stage and flatten for virtualization
  const { rows } = useActivityLogGroups(allEvents, collapsedStages);

  // Virtualizer with dynamic height measurement
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (index) => {
      const row = rows[index];
      return row?.type === 'header' ? 44 : 36;
    },
    overscan: 10,
    measureElement: (element) => element.getBoundingClientRect().height,
  });

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (rows.length > 0 && parentRef.current) {
      rowVirtualizer.scrollToIndex(rows.length - 1, { behavior: 'smooth' });
    }
  }, [rows.length, rowVirtualizer]);

  const toggleStage = (stage: string) => {
    setCollapsedStages((prev) => {
      const next = new Set(prev);
      if (next.has(stage)) {
        next.delete(stage);
      } else {
        next.add(stage);
      }
      return next;
    });
  };

  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground font-mono text-sm">
        No events yet
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      className="h-full overflow-auto"
      role="log"
      aria-live="polite"
    >
      <div
        style={{
          height: `${rowVirtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {rowVirtualizer.getVirtualItems().map((virtualRow) => {
          const row = rows[virtualRow.index];
          if (!row) return null;

          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={rowVirtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                minHeight: `${virtualRow.size}px`,
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              {row.type === 'header' ? (
                <ActivityLogHeader
                  group={row.group}
                  isCollapsed={collapsedStages.has(row.group.stage)}
                  onToggle={() => toggleStage(row.group.stage)}
                />
              ) : (
                <ActivityLogEvent event={row.event} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
