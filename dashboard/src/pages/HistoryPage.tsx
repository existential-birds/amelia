/**
 * @fileoverview Workflow history page showing past workflows.
 */
import { Link, useLoaderData } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { cn } from '@/lib/utils';
import { historyLoader } from '@/loaders/workflows';

/**
 * Displays a list of past workflows with status and timestamps.
 *
 * Shows workflow history in a scrollable list with status badges,
 * issue IDs, and start times. Supports keyboard navigation.
 *
 * @returns The history page UI
 */
export default function HistoryPage() {
  const { workflows } = useLoaderData<typeof historyLoader>();

  if (workflows.length === 0) {
    return <WorkflowEmptyState variant="no-activity" />;
  }

  /**
   * Formats an ISO date string for display.
   * @param dateString - ISO date string or null
   * @returns Formatted date string (e.g., "Dec 7, 10:30 AM")
   */
  const formatDate = (dateString: string | null): string => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  };

  return (
    <div className="flex flex-col w-full">
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>HISTORY</PageHeader.Label>
          <PageHeader.Title>Past Runs</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Center>
          <PageHeader.Label>TOTAL</PageHeader.Label>
          <PageHeader.Value>{workflows.length}</PageHeader.Value>
        </PageHeader.Center>
      </PageHeader>

      <div className="flex flex-col gap-2 p-6">
        {workflows.map((workflow) => (
          <Link
            key={workflow.id}
            to={`/workflows/${workflow.id}`}
            className={cn(
              'flex items-center gap-4 p-4 rounded-lg border transition-all duration-200 cursor-pointer',
              'hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              'border-border/50 bg-card/50'
            )}
          >
            <StatusBadge status={workflow.status} />

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-semibold text-accent">
                  {workflow.issue_id}
                </span>
                <span className="font-body text-sm text-foreground truncate">
                  {workflow.worktree_name}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Started: {formatDate(workflow.started_at)}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
