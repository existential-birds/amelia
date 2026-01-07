import { api } from '@/api/client';
import { getActiveWorkflow, getMostRecentCompleted } from '@/utils/workflow';
import type { LoaderFunctionArgs } from 'react-router-dom';
import type { WorkflowsLoaderData } from '@/types/api';
import { getDemoMode } from '@/hooks/useDemoMode';
import { getMockActiveWorkflows, getMockHistoryWorkflows, getMockWorkflowDetail } from '@/mocks/infinite-mode';
import { logger } from '@/lib/logger';

/**
 * Loader for the active workflows page.
 * Fetches all in_progress and blocked workflows from the API,
 * plus pre-loads the workflow detail based on URL parameter or active workflow.
 *
 * @param args - React Router loader arguments containing request URL and optional route params.
 * @returns Object containing the list of active workflows and optional detail.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * // For /workflows - loads active workflow detail
 * const { workflows, detail } = await workflowsLoader({ request });
 *
 * // For /workflows/:id - loads specific workflow detail
 * const { workflows, detail } = await workflowsLoader({ request, params: { id: 'wf-123' } });
 * ```
 */
export async function workflowsLoader({ request, params }: LoaderFunctionArgs): Promise<WorkflowsLoaderData> {
  const url = new URL(request.url);
  const { isDemo, demoType } = getDemoMode(url.searchParams);

  if (isDemo && demoType === 'infinite') {
    const workflows = getMockActiveWorkflows();
    const active = getActiveWorkflow(workflows);
    // Use id param if provided, otherwise use active workflow
    const targetId = params?.id ?? active?.id;
    const detail = targetId ? getMockWorkflowDetail(targetId) : null;
    return { workflows, detail };
  }

  // Fetch active workflows and history in parallel
  const [activeWorkflows, historyWorkflows] = await Promise.all([
    api.getWorkflows(),
    api.getWorkflowHistory(),
  ]);

  // Include the most recently completed workflow in the list so the canvas
  // doesn't immediately clear when a workflow completes
  const recentCompleted = getMostRecentCompleted(historyWorkflows);
  const workflows = recentCompleted
    ? [...activeWorkflows, recentCompleted]
    : activeWorkflows;

  const active = getActiveWorkflow(workflows);

  // Determine which workflow detail to fetch:
  // 1. If id param exists, fetch that specific workflow
  // 2. Otherwise, fetch the active workflow detail
  const targetId = params?.id ?? active?.id;
  let detail = null;
  let detailError: string | null = null;
  if (targetId) {
    try {
      detail = await api.getWorkflow(targetId);
    } catch (error) {
      logger.warn('Failed to fetch workflow detail', { workflowId: targetId, error });
      detailError = error instanceof Error ? error.message : 'Failed to load workflow details';
    }
  }

  return { workflows, detail, detailError };
}

/**
 * Loader for the workflow detail page.
 * Fetches full workflow details including events and token usage for a specific workflow.
 *
 * @param args - React Router loader arguments containing route parameters and request.
 * @returns Object containing the detailed workflow data.
 * @throws {Response} 400 error when workflow ID is missing from route parameters.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { workflow } = await workflowDetailLoader({ params: { id: 'workflow-123' }, request });
 * ```
 */
export async function workflowDetailLoader({ params, request }: LoaderFunctionArgs) {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  const url = new URL(request.url);
  const { isDemo, demoType } = getDemoMode(url.searchParams);

  if (isDemo && demoType === 'infinite') {
    const workflow = getMockWorkflowDetail(params.id);
    return { workflow };
  }

  const workflow = await api.getWorkflow(params.id);
  return { workflow };
}

/**
 * Loader for the workflow history page.
 * Fetches all completed, failed, and cancelled workflows from the API.
 *
 * @param args - React Router loader arguments containing request URL.
 * @returns Object containing the list of historical workflows.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { workflows } = await historyLoader({ request });
 * ```
 */
export async function historyLoader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const { isDemo, demoType } = getDemoMode(url.searchParams);

  if (isDemo && demoType === 'infinite') {
    const workflows = getMockHistoryWorkflows();
    return { workflows };
  }

  const workflows = await api.getWorkflowHistory();
  return { workflows };
}
