/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { api } from '@/api/client';
import { getActiveWorkflow } from '@/utils/workflow';
import type { LoaderFunctionArgs } from 'react-router-dom';
import type { WorkflowsLoaderData } from '@/types/api';
import { getDemoMode } from '@/hooks/useDemoMode';
import { getMockActiveWorkflows, getMockHistoryWorkflows, getMockWorkflowDetail } from '@/mocks/infinite-mode';
import { logger } from '@/lib/logger';

/**
 * Loader for the active workflows page.
 * Fetches all in_progress and blocked workflows from the API,
 * plus pre-loads the active workflow detail for instant display.
 *
 * @param args - React Router loader arguments containing request URL.
 * @returns Object containing the list of active workflows and optional active detail.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { workflows, activeDetail } = await workflowsLoader({ request });
 * ```
 */
export async function workflowsLoader({ request }: LoaderFunctionArgs): Promise<WorkflowsLoaderData> {
  const url = new URL(request.url);
  const { isDemo, demoType } = getDemoMode(url.searchParams);

  if (isDemo && demoType === 'infinite') {
    const workflows = getMockActiveWorkflows();
    const active = getActiveWorkflow(workflows);
    const activeDetail = active ? getMockWorkflowDetail(active.id) : null;
    return { workflows, activeDetail };
  }

  const workflows = await api.getWorkflows();
  const active = getActiveWorkflow(workflows);

  // Fetch active detail with error handling - don't fail the whole page if detail fails
  let activeDetail = null;
  if (active) {
    try {
      activeDetail = await api.getWorkflow(active.id);
    } catch (error) {
      logger.warn('Failed to fetch active workflow detail', { workflowId: active.id, error });
      // Continue with null - page will show list without canvas
    }
  }

  return { workflows, activeDetail };
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
