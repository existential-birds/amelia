import { cn } from '@/lib/utils';
import type { WorkflowEvent } from '@/types';

const DEFAULT_STYLE = { text: 'text-muted-foreground', bg: '' } as const;

const AGENT_STYLES: Record<string, { text: string; bg: string }> = {
  ARCHITECT: { text: 'text-agent-architect', bg: 'bg-agent-architect-bg' },
  DEVELOPER: { text: 'text-agent-developer', bg: 'bg-agent-developer-bg' },
  REVIEWER: { text: 'text-agent-reviewer', bg: 'bg-agent-reviewer-bg' },
  VALIDATOR: { text: 'text-agent-pm', bg: 'bg-agent-pm-bg' },
  PLAN_VALIDATOR: { text: 'text-agent-pm', bg: 'bg-agent-pm-bg' },
  HUMAN_APPROVAL: { text: 'text-destructive', bg: 'bg-destructive/5' },
  SYSTEM: DEFAULT_STYLE,
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
  const style = AGENT_STYLES[agentKey] ?? DEFAULT_STYLE;

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
        {agentKey}
      </span>
      <span className="text-foreground/80 break-words">{event.message}</span>
    </div>
  );
}
