/**
 * Additional TypeScript types for React Router loaders and actions.
 * Re-exports base types from Plan 08.
 * Keep in sync with amelia/server/models/*.py
 */

// Re-export all types from Plan 08 Task 8
export * from './index';

import type { WorkflowSummary, WorkflowDetail } from './index';

// ============================================================================
// React Router Loader Data Types
// ============================================================================

/**
 * Data returned by the workflows list route loader.
 * Used by the workflows index page to display all workflows.
 *
 * @example
 * ```typescript
 * export const loader = async (): Promise<WorkflowsLoaderData> => {
 *   const workflows = await fetchWorkflows();
 *   return { workflows };
 * };
 * ```
 */
export interface WorkflowsLoaderData {
  /** Array of workflow summaries to display in the list. */
  workflows: WorkflowSummary[];
}

/**
 * Data returned by the workflow detail route loader.
 * Used by the workflow detail page to display a single workflow's information.
 *
 * @example
 * ```typescript
 * export const loader = async ({ params }): Promise<WorkflowDetailLoaderData> => {
 *   const workflow = await fetchWorkflow(params.id);
 *   return { workflow };
 * };
 * ```
 */
export interface WorkflowDetailLoaderData {
  /** Complete workflow details including events, plan, and token usage. */
  workflow: WorkflowDetail;
}

// ============================================================================
// React Router Action Result Types
// ============================================================================

/**
 * Result object returned by React Router actions (approve, reject, cancel).
 * Indicates whether the action succeeded and which action was performed.
 *
 * @example
 * ```typescript
 * // Success case
 * const result: ActionResult = {
 *   success: true,
 *   action: 'approved'
 * };
 *
 * // Error case
 * const errorResult: ActionResult = {
 *   success: false,
 *   action: 'rejected',
 *   error: 'Server error: 500'
 * };
 * ```
 */
export interface ActionResult {
  /** Whether the action was successfully executed. */
  success: boolean;

  /** Which action was performed. */
  action: 'approved' | 'rejected' | 'cancelled';

  /** Error message if the action failed, otherwise undefined. */
  error?: string;
}
