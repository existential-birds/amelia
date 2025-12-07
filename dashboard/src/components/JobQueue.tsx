/**
 * @fileoverview Collapsible job queue displaying active workflows.
 */
import { JobQueueItem } from '@/components/JobQueueItem';
import { Badge } from '@/components/ui/badge';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ChevronDown } from 'lucide-react';
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
  workflows?: Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_name' | 'status' | 'current_stage'>[];
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  className?: string;
}

/**
 * Displays a collapsible list of active workflows.
 *
 * Shows workflow count in a badge and renders each workflow as a
 * selectable JobQueueItem. Displays empty state when no workflows exist.
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
      className={cn('flex flex-col', className)}
    >
      <Collapsible defaultOpen>
        <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-left font-medium text-muted-foreground text-sm transition-colors hover:bg-muted group">
          <span className="flex items-center gap-2">
            <ChevronDown className="h-4 w-4 transition-transform group-data-[state=closed]:-rotate-90" />
            <span className="font-heading text-xs font-semibold tracking-widest">
              JOB QUEUE
            </span>
          </span>
          <Badge variant="secondary" className="text-xs">
            {workflows.length}
          </Badge>
        </CollapsibleTrigger>

        <CollapsibleContent className="mt-2">
          {workflows.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No active workflows
            </p>
          ) : (
            <div className="flex flex-col gap-2">
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
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
