import { cn } from '@/lib/utils';
import type { WorkflowEvent } from '@/types';

interface ActivityLogItemProps {
  event: WorkflowEvent;
}

function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toISOString().slice(11, 19);
}

const agentColors: Record<string, string> = {
  ARCHITECT: 'text-accent',
  DEVELOPER: 'text-primary',
  REVIEWER: 'text-status-completed',
  SYSTEM: 'text-muted-foreground',
};

export function ActivityLogItem({ event }: ActivityLogItemProps) {
  const agentColor = agentColors[event.agent.toUpperCase()] || 'text-muted-foreground';

  return (
    <div
      data-slot="activity-log-item"
      className="flex items-start gap-3 py-1.5 border-b border-border/30 font-mono text-sm"
    >
      <span className="text-muted-foreground tabular-nums shrink-0">
        {formatTime(event.timestamp)}
      </span>
      <span className={cn('font-semibold shrink-0', agentColor)}>
        [{event.agent.toUpperCase()}]
      </span>
      <span className="text-foreground/80 break-words">
        {event.message}
      </span>
    </div>
  );
}
