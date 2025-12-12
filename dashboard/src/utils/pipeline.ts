/**
 * @fileoverview Pipeline conversion utilities for workflow visualization.
 */
import type { WorkflowDetail, TaskNode } from '@/types';

/** Node in the pipeline visualization. */
export interface PipelineNode {
  id: string;
  label: string;
  subtitle?: string;
  status: 'completed' | 'active' | 'blocked' | 'pending';
  tokens?: string;
}

/** Edge connecting pipeline nodes. */
export interface PipelineEdge {
  from: string;
  to: string;
  label: string;
  status: 'completed' | 'active' | 'pending';
}

/** Pipeline data structure for WorkflowCanvas. */
export interface Pipeline {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

/**
 * Formats a duration in milliseconds to a human-readable string.
 * @param ms - Duration in milliseconds
 * @returns Formatted string (e.g., "1m 23s", "45s", "2h 5m")
 */
function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    const remainingMinutes = minutes % 60;
    return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
  }
  if (minutes > 0) {
    const remainingSeconds = seconds % 60;
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  }
  return `${seconds}s`;
}

/**
 * Formats a token count to a human-readable string.
 * @param tokens - Number of tokens
 * @returns Formatted string (e.g., "1.2k", "45.3k", "1.2M")
 */
function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    return `${(tokens / 1_000).toFixed(1)}k`;
  }
  return `${tokens}`;
}

/**
 * Truncates text to a maximum length, adding ellipsis if needed.
 * @param text - Text to truncate
 * @param maxLength - Maximum length (default 20)
 * @returns Truncated text
 */
function truncateText(text: string, maxLength = 20): string {
  if (text.length <= maxLength) {
    return text;
  }
  return text.slice(0, maxLength - 1) + '…';
}

/**
 * Generates a label for a task node from the task description.
 * Uses a truncated version of the description as the primary label.
 * @param task - The task node
 * @returns Short label for the task (e.g., "Setup test infra…")
 */
function getTaskLabel(task: TaskNode): string {
  return truncateText(task.description);
}

/**
 * Calculates the subtitle for a task node based on execution time.
 * TODO(#73): Wire up started_at/completed_at from backend
 * @param task - The task node
 * @returns Duration string, status indicator, or undefined
 */
function getTaskSubtitle(task: TaskNode): string | undefined {
  // Show duration for completed tasks with timing data
  if (task.started_at && task.completed_at) {
    const startTime = new Date(task.started_at).getTime();
    const endTime = new Date(task.completed_at).getTime();
    const duration = endTime - startTime;
    if (duration > 0) {
      return formatDuration(duration);
    }
  }

  // Show "Running..." for active tasks (could show elapsed time with started_at)
  if (task.status === 'in_progress') {
    return 'Running...';
  }

  return undefined;
}

/**
 * Converts a workflow detail into a pipeline visualization format.
 *
 * Maps task statuses to node statuses:
 * - completed -> completed
 * - in_progress -> active
 * - failed -> blocked
 * - other -> pending
 *
 * @param workflow - The workflow detail containing the plan
 * @returns Pipeline data or null if no plan exists
 */
export function buildPipeline(workflow: WorkflowDetail): Pipeline | null {
  if (!workflow.plan) {
    return null;
  }

  const taskIds = new Set(workflow.plan.tasks.map((t) => t.id));

  const nodes: PipelineNode[] = workflow.plan.tasks.map((task) => ({
    id: task.id,
    label: getTaskLabel(task),
    subtitle: getTaskSubtitle(task),
    status: task.status === 'completed'
      ? 'completed'
      : task.status === 'in_progress'
      ? 'active'
      : task.status === 'failed'
      ? 'blocked'
      : 'pending',
    // TODO(#73): Wire up tokens from backend
    tokens: task.tokens ? formatTokens(task.tokens) : undefined,
  }));

  // Filter edges to only include those where both source and target exist
  // Compute edge status based on target task state:
  // - If target is completed → edge is completed
  // - If target is in_progress → edge is active
  // - Otherwise → edge is pending
  const edges: PipelineEdge[] = workflow.plan.tasks.flatMap((task) =>
    task.dependencies
      .filter((depId) => taskIds.has(depId))
      .map((depId) => ({
        from: depId,
        to: task.id,
        label: '',
        status: task.status === 'completed'
          ? 'completed'
          : task.status === 'in_progress'
          ? 'active'
          : 'pending',
      }))
  );

  return { nodes, edges };
}
