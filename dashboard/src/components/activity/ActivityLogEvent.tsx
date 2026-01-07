import { cn } from '@/lib/utils';
import type { WorkflowEvent } from '@/types';

const AGENT_STYLES: Record<string, { text: string; bg: string }> = {
  ARCHITECT: { text: 'text-blue-400', bg: '' },
  DEVELOPER: { text: 'text-green-400', bg: '' },
  REVIEWER: { text: 'text-yellow-400', bg: '' },
  SYSTEM: { text: 'text-muted-foreground', bg: '' },
};

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  // Use toISOString for consistent UTC output (avoids timezone issues in tests)
  return date.toISOString().slice(11, 19);
}

interface ActivityLogEventProps {
  event: WorkflowEvent;
}

export function ActivityLogEvent({ event }: ActivityLogEventProps) {
  const agentKey = event.agent.toUpperCase();
  const style = AGENT_STYLES[agentKey] ?? AGENT_STYLES.SYSTEM;

  return (
    <div
      data-slot="activity-log-event"
      className={cn(
        'grid grid-cols-[100px_120px_1fr] gap-3 py-1.5 px-3',
        'border-b border-border/30 font-mono text-sm',
        style.bg
      )}
    >
      <span className="text-muted-foreground tabular-nums">
        {formatTime(event.timestamp)}
      </span>
      <span className={cn('font-semibold', style.text)}>
        [{agentKey}]
      </span>
      <span className="text-foreground/80 break-words">{event.message}</span>
    </div>
  );
}
