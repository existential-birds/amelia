import { api } from '@/api/client';
import type { LoaderFunctionArgs } from 'react-router-dom';

/**
 * Loader for the active workflows page.
 * Fetches all in_progress and blocked workflows from the API.
 *
 * @returns Object containing the list of active workflows.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { workflows } = await workflowsLoader();
 * ```
 */
export async function workflowsLoader() {
  const workflows = await api.getWorkflows();
  return { workflows };
}

/**
 * Loader for the workflow detail page.
 * Fetches full workflow details including events and token usage for a specific workflow.
 *
 * @param args - React Router loader arguments containing route parameters.
 * @returns Object containing the detailed workflow data.
 * @throws {Response} 400 error when workflow ID is missing from route parameters.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { workflow } = await workflowDetailLoader({ params: { id: 'workflow-123' } });
 * ```
 */
export async function workflowDetailLoader({ params }: LoaderFunctionArgs) {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  const workflow = await api.getWorkflow(params.id);
  return { workflow };
}

/**
 * Loader for the workflow history page.
 * Fetches all completed, failed, and cancelled workflows from the API.
 *
 * @returns Object containing the list of historical workflows.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { workflows } = await historyLoader();
 * ```
 */
export async function historyLoader() {
  const workflows = await api.getWorkflowHistory();
  return { workflows };
}
