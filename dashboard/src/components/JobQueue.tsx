/**
 * @fileoverview Static job queue displaying active workflows.
 */
import { JobQueueItem } from '@/components/JobQueueItem';
import { cn } from '@/lib/utils';
import type { WorkflowSummary } from '@/types';

/**
 * Props for the JobQueue component.
 * @property workflows - Array of workflow summaries to display
 * @property selectedId - ID of the currently selected workflow
 * @property onSelect - Callback when a workflow is selected
 * @property className - Optional additional CSS classes
 */
interface JobQueueProps {
  workflows?: Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_path' | 'status' | 'current_stage'>[];
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  className?: string;
}

/**
 * Displays a static list of active workflows.
 *
 * Renders each workflow as a selectable JobQueueItem.
 * Displays empty state when no workflows exist.
 *
 * @param props - Component props
 * @returns The job queue UI
 *
 * @example
 * ```tsx
 * <JobQueue
 *   workflows={workflows}
 *   selectedId={currentId}
 *   onSelect={(id) => navigate(`/workflows/${id}`)}
 * />
 * ```
 */
export function JobQueue({
  workflows = [],
  selectedId = null,
  onSelect = () => {},
  className
}: JobQueueProps) {
  return (
    <div
      data-slot="job-queue"
      className={cn('bg-card/60 border border-border/50 flex flex-col', className)}
    >
      <div className="sticky top-0 z-20 bg-card/60 backdrop-blur-sm px-5 pt-5 pb-3 border-b border-border/50">
        <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground">
          JOB QUEUE
        </h3>
      </div>

      {workflows.length === 0 ? (
        <p className="text-center text-muted-foreground py-8">
          No active workflows
        </p>
      ) : (
        <div className="flex flex-col gap-2 p-5">
          {workflows.map((workflow) => (
            <JobQueueItem
              key={workflow.id}
              workflow={workflow}
              selected={workflow.id === selectedId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
