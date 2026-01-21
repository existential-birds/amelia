/**
 * @fileoverview Static job queue displaying active workflows.
 */
import { useState } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { JobQueueItem } from '@/components/JobQueueItem';
import { cn } from '@/lib/utils';
import type { WorkflowSummary } from '@/types';

/**
 * Props for the JobQueue component.
 * @property workflows - Array of workflow summaries to display
 * @property selectedId - ID of the currently selected workflow
 * @property onSelect - Callback when a workflow is selected
 * @property className - Optional additional CSS classes
 * @property collapsible - Whether the queue can be collapsed (default: false)
 * @property defaultCollapsed - Initial collapsed state when collapsible is true (default: false)
 */
interface JobQueueProps {
  workflows?: Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_path' | 'status' | 'current_stage'>[];
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  className?: string;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
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
  className,
  collapsible = false,
  defaultCollapsed = false
}: JobQueueProps) {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);

  const handleHeaderClick = () => {
    if (collapsible) {
      setIsCollapsed(!isCollapsed);
    }
  };

  const ChevronIcon = isCollapsed ? ChevronUp : ChevronDown;

  return (
    <div
      data-slot="job-queue"
      className={cn('bg-card/60 border border-border/50 flex flex-col', className)}
    >
      <div
        className={cn(
          'sticky top-0 z-20 bg-card/60 backdrop-blur-sm px-5 pt-5 pb-3 border-b border-border/50',
          collapsible && 'cursor-pointer hover:bg-card/80 transition-colors'
        )}
        onClick={handleHeaderClick}
        role={collapsible ? 'button' : undefined}
        aria-expanded={collapsible ? !isCollapsed : undefined}
        tabIndex={collapsible ? 0 : undefined}
        onKeyDown={collapsible ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleHeaderClick();
          }
        } : undefined}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground">
            JOB QUEUE{collapsible && ` (${workflows.length})`}
          </h3>
          {collapsible && (
            <ChevronIcon className="size-4 text-muted-foreground" />
          )}
        </div>
      </div>

      <div
        aria-hidden={collapsible && isCollapsed}
        className={cn(
          'transition-all duration-200 overflow-hidden',
          collapsible && isCollapsed
            ? 'max-h-0 opacity-0 invisible pointer-events-none'
            : 'max-h-[2000px] opacity-100 visible'
        )}
      >
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
    </div>
  );
}
