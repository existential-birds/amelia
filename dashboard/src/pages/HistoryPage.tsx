/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { useLoaderData, useNavigate } from 'react-router-dom';
import { StatusBadge } from '@/components/StatusBadge';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { cn } from '@/lib/utils';
import type { WorkflowSummary } from '@/types';

interface HistoryLoaderData {
  workflows: WorkflowSummary[];
}

export default function HistoryPage() {
  const { workflows } = useLoaderData() as HistoryLoaderData;
  const navigate = useNavigate();

  if (workflows.length === 0) {
    return <WorkflowEmptyState variant="no-activity" />;
  }

  const handleWorkflowClick = (workflowId: string) => {
    navigate(`/workflows/${workflowId}`);
  };

  const handleKeyDown = (e: React.KeyboardEvent, workflowId: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      navigate(`/workflows/${workflowId}`);
    }
  };

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
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-display text-primary">Workflow History</h2>
        <span className="text-sm text-muted-foreground">
          {workflows.length} {workflows.length === 1 ? 'workflow' : 'workflows'}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {workflows.map((workflow) => (
          <div
            key={workflow.id}
            role="button"
            tabIndex={0}
            onClick={() => handleWorkflowClick(workflow.id)}
            onKeyDown={(e) => handleKeyDown(e, workflow.id)}
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
          </div>
        ))}
      </div>
    </div>
  );
}

// Loader function will be added in Plan 09
// export async function loader() { ... }
