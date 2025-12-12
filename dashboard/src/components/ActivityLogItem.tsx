/**
 * @fileoverview Individual log entry in the activity log.
 */
import { cn } from '@/lib/utils';
import type { WorkflowEvent } from '@/types';

/**
 * Props for the ActivityLogItem component.
 * @property event - The workflow event to display
 */
interface ActivityLogItemProps {
  event: WorkflowEvent;
}

/**
 * Formats an ISO timestamp to HH:MM:SS format.
 * @param isoString - ISO 8601 timestamp string
 * @returns Time string in HH:MM:SS format
 */
function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toISOString().slice(11, 19);
}

/** Color mapping for different agent types in the log. */
const agentColors: Record<string, string> = {
  ORCHESTRATOR: 'text-muted-foreground',
  ARCHITECT: 'text-accent',
  DEVELOPER: 'text-primary',
  REVIEWER: 'text-status-completed',
  SYSTEM: 'text-muted-foreground',
};

/**
 * Renders a single event entry in the activity log.
 *
 * Displays timestamp, agent name (color-coded), and event message
 * in a terminal-style format.
 *
 * @param props - Component props
 * @returns The log item UI
 */
export function ActivityLogItem({ event }: ActivityLogItemProps) {
  const agentColor = agentColors[event.agent.toUpperCase()] || 'text-muted-foreground';

  return (
    <div
      data-slot="activity-log-item"
      className="grid grid-cols-[70px_120px_1fr] gap-3 py-1.5 border-b border-border/30 font-mono text-sm"
    >
      <span className="text-muted-foreground tabular-nums">
        {formatTime(event.timestamp)}
      </span>
      <span className={cn('font-semibold', agentColor)}>
        [{event.agent.toUpperCase()}]
      </span>
      <span className="text-foreground/80 break-words">
        {event.message}
      </span>
    </div>
  );
}
