/**
 * @fileoverview Individual item in the job queue list.
 *
 * Industrial card design with status indicator rail on left edge.
 * Optimized for information density without truncation.
 */
import { cn } from '@/lib/utils';
import type { WorkflowSummary, WorkflowStatus } from '@/types';

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

/** Maps workflow status to indicator styling. */
const statusStyles: Record<WorkflowStatus, { rail: string; dot: string; text: string }> = {
  pending: {
    rail: 'bg-status-pending/60',
    dot: 'bg-status-pending',
    text: 'text-status-pending',
  },
  in_progress: {
    rail: 'bg-status-running/80',
    dot: 'bg-status-running animate-pulse',
    text: 'text-status-running',
  },
  blocked: {
    rail: 'bg-status-blocked/60',
    dot: 'bg-status-blocked',
    text: 'text-status-blocked',
  },
  completed: {
    rail: 'bg-status-completed/60',
    dot: 'bg-status-completed',
    text: 'text-status-completed',
  },
  failed: {
    rail: 'bg-status-failed/60',
    dot: 'bg-status-failed',
    text: 'text-status-failed',
  },
  cancelled: {
    rail: 'bg-status-cancelled/60',
    dot: 'bg-status-cancelled',
    text: 'text-status-cancelled',
  },
};

/** Human-readable status labels. */
const statusLabels: Record<WorkflowStatus, string> = {
  pending: 'QUEUED',
  in_progress: 'RUNNING',
  blocked: 'BLOCKED',
  completed: 'DONE',
  failed: 'FAILED',
  cancelled: 'CANCELLED',
};

/**
 * Extracts the repository name from a worktree path.
 * @param path - Full filesystem path like /Users/ka/github/existential-birds/amelia
 * @returns Repository name like "amelia"
 */
function getRepoName(path: string): string {
  if (!path || path === '/') return 'unknown';
  const segments = path.split(/[\\/]+/).filter(Boolean);
  return segments[segments.length - 1] || 'unknown';
}

/**
 * Renders a single workflow item in the job queue.
 *
 * Industrial card design with:
 * - Colored status rail on left edge
 * - Issue ID as primary identifier
 * - Repository name (extracted from worktree path)
 * - Current stage indicator
 * - Compact status dot with label
 *
 * Supports keyboard navigation and visual selection state.
 *
 * @param props - Component props
 * @returns The job queue item UI
 */
export function JobQueueItem({ workflow, selected, onSelect, className }: JobQueueItemProps) {
  const handleClick = () => onSelect(workflow.id);
  const style = statusStyles[workflow.status];
  const repoName = getRepoName(workflow.worktree_path);

  return (
    <button
      type="button"
      onClick={handleClick}
      data-slot="job-queue-item"
      data-selected={selected}
      className={cn(
        'group w-full text-left relative',
        'flex items-stretch rounded-md border transition-all duration-200 cursor-pointer overflow-hidden',
        'hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        selected
          ? 'border-primary bg-primary/5 shadow-[0_0_20px_rgba(255,200,87,0.15)]'
          : 'border-border/40 bg-card/40',
        className
      )}
    >
      {/* Status Rail - colored left edge */}
      <div className={cn('w-1 shrink-0 transition-all', style.rail)} />

      {/* Content */}
      <div className="flex-1 min-w-0 px-3 py-2.5 flex flex-col gap-1">
        {/* Row 1: Issue ID and Status */}
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-sm font-semibold text-accent truncate">
            {workflow.issue_id}
          </span>
          <div className={cn('flex items-center gap-1.5 shrink-0', style.text)}>
            <span className={cn('size-1.5 rounded-full', style.dot)} />
            <span className="font-heading text-[10px] font-semibold tracking-wider">
              {statusLabels[workflow.status]}
            </span>
          </div>
        </div>

        {/* Row 2: Repo name and current stage */}
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="font-body text-foreground/80 truncate">
            {repoName}
          </span>
          {workflow.current_stage && (
            <span className="font-mono text-muted-foreground uppercase tracking-wide shrink-0">
              {workflow.current_stage}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
