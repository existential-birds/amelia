import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import type { WorkflowStatus } from '@/types';

const statusBadgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-wider transition-colors',
  {
    variants: {
      status: {
        pending: 'bg-status-pending/20 text-status-pending border border-status-pending/30',
        running: 'bg-status-running/20 text-status-running border border-status-running/30',
        completed: 'bg-status-completed/20 text-status-completed border border-status-completed/30',
        failed: 'bg-status-failed/20 text-status-failed border border-status-failed/30',
        blocked: 'bg-status-blocked/20 text-status-blocked border border-status-blocked/30',
      },
    },
    defaultVariants: {
      status: 'pending',
    },
  }
);

interface StatusBadgeProps extends VariantProps<typeof statusBadgeVariants> {
  status: WorkflowStatus;
  className?: string;
}

const statusLabels: Record<WorkflowStatus, string> = {
  pending: 'QUEUED',
  in_progress: 'RUNNING',
  blocked: 'BLOCKED',
  completed: 'DONE',
  failed: 'FAILED',
  cancelled: 'CANCELLED',
};

type IndicatorStatus = 'pending' | 'running' | 'completed' | 'failed' | 'blocked';

const statusMapping: Record<WorkflowStatus, IndicatorStatus> = {
  pending: 'pending',
  in_progress: 'running',
  blocked: 'blocked',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'failed',
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const indicatorStatus = statusMapping[status];
  const displayStatus = status === 'in_progress' ? 'running' : status;

  return (
    <div
      data-slot="status-badge"
      data-status={indicatorStatus}
      role="status"
      aria-label={`Workflow status: ${displayStatus}`}
      className={cn(statusBadgeVariants({ status: indicatorStatus }), className)}
    >
      <span
        className={cn(
          'size-2 rounded-full',
          indicatorStatus === 'running' && 'animate-pulse bg-current',
          indicatorStatus !== 'running' && 'bg-current'
        )}
      />
      {statusLabels[status]}
    </div>
  );
}
