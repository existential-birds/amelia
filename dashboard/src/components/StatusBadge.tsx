/**
 * @fileoverview Status badge component for workflow states.
 */
import { cva } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import type { WorkflowStatus } from '@/types';

/** CVA variants for status badge styling based on workflow state. */
const statusBadgeVariants = cva(
  'inline-flex items-center justify-center gap-1.5 min-w-[6.5rem] rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-wider transition-colors',
  {
    variants: {
      status: {
        pending: 'bg-status-pending/20 text-status-pending border border-status-pending/30',
        running: 'bg-status-running/20 text-status-running border border-status-running/30',
        completed: 'bg-status-completed/20 text-status-completed border border-status-completed/30',
        failed: 'bg-status-failed/20 text-status-failed border border-status-failed/30',
        blocked: 'bg-status-blocked/20 text-status-blocked border border-status-blocked/30',
        cancelled: 'bg-status-cancelled/20 text-status-cancelled border border-status-cancelled/30',
      },
    },
    defaultVariants: {
      status: 'pending',
    },
  }
);

/**
 * Props for the StatusBadge component.
 * @property status - Current workflow status
 * @property className - Optional additional CSS classes
 */
interface StatusBadgeProps {
  status: WorkflowStatus;
  className?: string;
}

/** Human-readable labels for each workflow status. */
const statusLabels: Record<WorkflowStatus, string> = {
  pending: 'QUEUED',
  in_progress: 'RUNNING',
  blocked: 'BLOCKED',
  completed: 'DONE',
  failed: 'FAILED',
  cancelled: 'CANCELLED',
};

/** Internal status type for styling variants. */
type IndicatorStatus = 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'cancelled';

/** Maps workflow status to indicator status for styling. */
const statusMapping: Record<WorkflowStatus, IndicatorStatus> = {
  pending: 'pending',
  in_progress: 'running',
  blocked: 'blocked',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'cancelled',
};

/**
 * Displays a color-coded badge indicating workflow status.
 *
 * Shows a pulsing indicator for running status. Includes proper
 * ARIA attributes for accessibility.
 *
 * @param props - Component props
 * @returns The status badge UI
 *
 * @example
 * ```tsx
 * <StatusBadge status="in_progress" />
 * ```
 */
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
