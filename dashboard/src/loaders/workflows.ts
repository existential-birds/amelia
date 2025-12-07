import { api } from '@/api/client';
import type { LoaderFunctionArgs } from 'react-router-dom';

/**
 * Loader for active workflows page.
 * Fetches in_progress and blocked workflows.
 */
export async function workflowsLoader() {
  const workflows = await api.getWorkflows();
  return { workflows };
}

/**
 * Loader for workflow detail page.
 * Fetches full workflow details including events and token usage.
 */
export async function workflowDetailLoader({ params }: LoaderFunctionArgs) {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  const workflow = await api.getWorkflow(params.id);
  return { workflow };
}

/**
 * Loader for workflow history page.
 * Fetches completed, failed, and cancelled workflows.
 */
export async function historyLoader() {
  const workflows = await api.getWorkflowHistory();
  return { workflows };
}
