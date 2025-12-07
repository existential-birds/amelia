import { StatusBadge } from '@/components/StatusBadge';
import { Loader } from '@/components/ai-elements/loader';
import { cn } from '@/lib/utils';
import type { WorkflowSummary } from '@/types';

interface WorkflowHeaderProps {
  workflow: Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_name' | 'status'>;
  elapsedTime?: string;
  className?: string;
}

export function WorkflowHeader({ workflow, elapsedTime, className }: WorkflowHeaderProps) {
  const isRunning = workflow.status === 'in_progress';

  return (
    <header
      role="banner"
      data-slot="workflow-header"
      className={cn(
        'flex items-center justify-between px-6 py-4 border-b border-border bg-card/50',
        className
      )}
    >
      {/* Left: Workflow info */}
      <div>
        <span className="block font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-1">
          WORKFLOW
        </span>
        <div className="flex items-center gap-3">
          <h2 className="font-display text-3xl font-bold tracking-wider text-foreground">
            {workflow.issue_id}
          </h2>
          <span className="font-mono text-sm text-muted-foreground">
            {workflow.worktree_name}
          </span>
        </div>
      </div>

      {/* Right: Status */}
      <div className="flex items-center gap-3 px-4 py-2 bg-primary/10 border border-primary/30 rounded">
        {isRunning && (
          <Loader className="w-4 h-4 text-primary" />
        )}
        <StatusBadge status={workflow.status} />
        {elapsedTime && (
          <span className="font-mono text-sm text-muted-foreground">
            {elapsedTime}
          </span>
        )}
      </div>
    </header>
  );
}
