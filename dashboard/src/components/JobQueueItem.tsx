/**
 * @fileoverview Individual item in the job queue list.
 */
import { StatusBadge } from '@/components/StatusBadge';
import { cn } from '@/lib/utils';
import { truncateWorkflowId } from '@/utils';
import type { WorkflowSummary } from '@/types';

/**
 * Props for the JobQueueItem component.
 * @property workflow - Workflow data to display
 * @property selected - Whether this item is currently selected
 * @property onSelect - Callback when item is clicked/activated
 * @property className - Optional additional CSS classes
 */
interface JobQueueItemProps {
  workflow: Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_path' | 'status' | 'current_stage'>;
  selected: boolean;
  onSelect: (id: string) => void;
  className?: string;
}

/**
 * Renders a single workflow item in the job queue.
 *
 * Displays issue ID, worktree name, and status badge.
 * Supports keyboard navigation (Enter/Space) and visual selection state with gold glow.
 *
 * @param props - Component props
 * @returns The job queue item UI
 */
export function JobQueueItem({ workflow, selected, onSelect, className }: JobQueueItemProps) {
  const handleClick = () => onSelect(workflow.id);

  return (
    <button
      type="button"
      onClick={handleClick}
      data-slot="job-queue-item"
      data-selected={selected}
      className={cn(
        'w-full text-left',
        'flex flex-col gap-1.5 p-3 rounded-lg border transition-all duration-200 cursor-pointer',
        'hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        selected
          ? 'border-primary border-2 bg-primary/5 shadow-[0_0_15px_rgba(255,200,87,0.1)]'
          : 'border-border/30 bg-card/60',
        className
      )}
    >
      {/* Row 1: Issue ID and Status Badge */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <span
          title={workflow.issue_id}
          className="font-mono text-sm font-semibold text-accent truncate"
        >
          {truncateWorkflowId(workflow.issue_id)}
        </span>
        <StatusBadge status={workflow.status} className="flex-shrink-0" />
      </div>

      {/* Row 2: Worktree Path */}
      <div className="font-body text-sm text-foreground truncate">
        {workflow.worktree_path}
      </div>
    </button>
  );
}
