/**
 * @fileoverview Workflow progress indicator component.
 */
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

/**
 * Props for the WorkflowProgress component.
 * @property completed - Number of completed workflow stages
 * @property total - Total number of workflow stages
 * @property className - Optional additional CSS classes
 */
interface WorkflowProgressProps {
  completed: number;
  total: number;
  className?: string;
}

/**
 * WorkflowProgress shows overall workflow completion using shadcn/ui Progress.
 * Includes percentage label and stage count.
 *
 * Uses OKLCH status colors:
 * - In progress: --status-running (amber)
 * - Complete: --status-completed (teal/green)
 *
 * @param props - Component props
 * @param props.completed - Number of completed workflow stages
 * @param props.total - Total number of workflow stages
 * @param props.className - Optional additional CSS classes
 * @returns React element displaying the workflow progress bar with stage count
 */
export function WorkflowProgress({ completed, total, className }: WorkflowProgressProps) {
  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
  const isComplete = completed === total && total > 0;

  return (
    <div
      data-slot="workflow-progress"
      data-complete={isComplete}
      className={cn('flex flex-col gap-2', className)}
    >
      <div className="flex items-center justify-between text-sm">
        <span className="font-mono text-muted-foreground">
          {completed} of {total} stages
        </span>
        <span className="font-mono font-semibold text-foreground">
          {percentage}%
        </span>
      </div>

      <Progress
        value={percentage}
        className={cn(
          'h-2',
          isComplete && '[&>[data-slot=progress-indicator]]:bg-status-completed'
        )}
        aria-label={`Workflow progress: ${percentage}% complete`}
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
      />
    </div>
  );
}
