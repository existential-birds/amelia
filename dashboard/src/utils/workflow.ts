/**
 * @fileoverview Workflow utility functions.
 */
import type { WorkflowSummary, WorkflowDetail } from '@/types';

// ============================================================================
// Token & Cost Formatting
// ============================================================================

/**
 * Formats a token count in a compact format with K suffix for thousands.
 * Examples: 500 -> "500", 1500 -> "1.5K", 15200 -> "15.2K"
 *
 * @param tokens - The number of tokens to format
 * @returns Formatted string with K suffix for values >= 1000
 */
export function formatTokens(tokens: number): string {
  if (tokens < 1000) {
    return tokens.toString();
  }
  const value = tokens / 1000;
  // Use at most 1 decimal place, remove trailing zeros
  return `${parseFloat(value.toFixed(1))}K`;
}

/**
 * Formats a USD cost value with dollar sign and 2 decimal places.
 * Example: 0.42 -> "$0.42"
 *
 * @param cost - The cost in USD
 * @returns Formatted string with dollar sign
 */
export function formatCost(cost: number): string {
  return `$${cost.toFixed(2)}`;
}

/**
 * Formats a duration in milliseconds to a human-readable format.
 * Examples: 15000 -> "15s", 97000 -> "1m 37s", 154000 -> "2m 34s"
 *
 * @param durationMs - Duration in milliseconds
 * @returns Formatted string in "Xm Ys" or "Xs" format
 */
export function formatDuration(durationMs: number): string {
  const totalSeconds = Math.floor(durationMs / 1000);

  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (seconds === 0) {
    return `${minutes}m`;
  }

  return `${minutes}m ${seconds}s`;
}

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
 * 3. Most recently created pending workflow
 * 4. Most recently started completed workflow
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

  // Priority 3: Most recently created pending workflow (uses created_at since started_at is null)
  const pending = workflows
    .filter(w => w.status === 'pending')
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  if (pending[0]) return pending[0];

  // Priority 4: Most recently started completed workflow
  const completed = workflows
    .filter(w => w.status === 'completed')
    .sort(sortByStartTimeDesc);

  return completed[0] ?? null;
}

/**
 * Gets the most recently completed workflow from a list.
 *
 * Used to keep a completed workflow visible in the active workflows view
 * so the canvas doesn't immediately clear when a workflow finishes.
 *
 * @param workflows - List of workflow summaries (typically from history)
 * @returns The most recently completed workflow or null if none exist
 */
export function getMostRecentCompleted(workflows: WorkflowSummary[]): WorkflowSummary | null {
  const completed = workflows
    .filter(w => w.status === 'completed')
    .sort(sortByStartTimeDesc);

  return completed[0] ?? null;
}

/**
 * Determines the end time for elapsed time calculation.
 * Uses completed_at if available, otherwise uses current time for in-progress workflows,
 * or the last event timestamp for blocked/failed/canceled workflows.
 * @param workflow - The workflow detail object containing timing and event information
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

/**
 * Formats a relative time string for display (e.g., "5m ago", "2h ago").
 *
 * @param timestamp - ISO 8601 timestamp to format relative to now
 * @returns Relative time string (e.g., "5m ago", "2h ago", "3d ago")
 */
export function formatRelativeTime(timestamp: string): string {
  const now = Date.now();
  const time = new Date(timestamp).getTime();
  const diffMs = now - time;

  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMinutes < 1) {
    return 'just now';
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  return `${diffDays}d ago`;
}
