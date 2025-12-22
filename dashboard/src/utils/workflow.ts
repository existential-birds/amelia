/**
 * @fileoverview Workflow utility functions.
 */
import type { WorkflowSummary, WorkflowDetail } from '@/types';

/**
 * Sorts workflows by start time in descending order (most recent first).
 * @param a - First workflow to compare
 * @param b - Second workflow to compare
 * @returns Negative if b is newer, positive if a is newer, 0 if equal or missing timestamps
 */
function sortByStartTimeDesc(a: WorkflowSummary, b: WorkflowSummary): number {
  if (!a.started_at || !b.started_at) return 0;
  return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
}

/**
 * Determines which workflow to display as the "active" workflow.
 *
 * Priority:
 * 1. Most recently started running workflow (status === 'in_progress')
 * 2. Most recently started blocked workflow (status === 'blocked')
 * 3. Most recently started completed workflow
 *
 * @param workflows - List of workflow summaries
 * @returns The active workflow or null if none exist
 */
export function getActiveWorkflow(workflows: WorkflowSummary[]): WorkflowSummary | null {
  // Priority 1: Most recently started running workflow
  const running = workflows
    .filter(w => w.status === 'in_progress')
    .sort(sortByStartTimeDesc);
  if (running[0]) return running[0];

  // Priority 2: Most recently started blocked workflow
  const blocked = workflows
    .filter(w => w.status === 'blocked')
    .sort(sortByStartTimeDesc);
  if (blocked[0]) return blocked[0];

  // Priority 3: Most recently started completed workflow
  const completed = workflows
    .filter(w => w.status === 'completed')
    .sort(sortByStartTimeDesc);

  return completed[0] ?? null;
}

/**
 * Determines the end time for elapsed time calculation.
 * Uses completed_at if available, otherwise uses current time for in-progress workflows,
 * or the last event timestamp for blocked/failed/canceled workflows.
 * @param workflow - The workflow detail
 * @returns End time in milliseconds since epoch
 */
function getEndTime(workflow: WorkflowDetail): number {
  if (workflow.completed_at) {
    return new Date(workflow.completed_at).getTime();
  }

  if (workflow.status === 'in_progress') {
    return Date.now();  // Still running, show live elapsed time
  }

  // Blocked, failed, canceled - use last event time
  return workflow.recent_events?.at(-1)?.timestamp
    ? new Date(workflow.recent_events.at(-1)!.timestamp).getTime()
    : Date.now();
}

/**
 * Formats the elapsed time for a workflow in HH:MM format.
 *
 * For running workflows: calculates time from started_at to now
 * For completed workflows: calculates time from started_at to completed_at
 *
 * @param workflow - The workflow detail to calculate elapsed time for
 * @returns Formatted time string (e.g., "2h 34m") or "--:--" if no start time
 */
export function formatElapsedTime(workflow: WorkflowDetail | null): string {
  if (!workflow?.started_at) {
    return '--:--';
  }

  const startTime = new Date(workflow.started_at).getTime();
  const endTime = getEndTime(workflow);

  const elapsedMs = endTime - startTime;
  const elapsedMinutes = Math.floor(elapsedMs / (1000 * 60));
  const hours = Math.floor(elapsedMinutes / 60);
  const minutes = elapsedMinutes % 60;

  return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
}
