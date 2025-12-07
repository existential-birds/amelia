/**
 * @fileoverview Workflow utility functions.
 */
import type { WorkflowSummary } from '@/types';

/**
 * Determines which workflow to display as the "active" workflow.
 *
 * Priority:
 * 1. Running workflow (status === 'in_progress')
 * 2. Blocked workflow awaiting approval (status === 'blocked')
 * 3. Most recently started completed workflow
 *
 * @param workflows - List of workflow summaries
 * @returns The active workflow or null if none exist
 */
export function getActiveWorkflow(workflows: WorkflowSummary[]): WorkflowSummary | null {
  // Priority 1: Running workflow
  const running = workflows.find(w => w.status === 'in_progress');
  if (running) return running;

  // Priority 2: Blocked workflow (awaiting approval)
  const blocked = workflows.find(w => w.status === 'blocked');
  if (blocked) return blocked;

  // Priority 3: Last completed (most recent by started_at)
  const completed = workflows
    .filter(w => w.status === 'completed')
    .sort((a, b) => {
      if (!a.started_at || !b.started_at) return 0;
      return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
    });

  return completed[0] ?? null;
}
