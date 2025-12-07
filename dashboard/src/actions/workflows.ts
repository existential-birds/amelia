import { api } from '@/api/client';
import type { ActionFunctionArgs } from 'react-router-dom';
import type { ActionResult } from '@/types/api';

/**
 * Approves a workflow execution.
 *
 * Handles the approve action for a workflow route, sending approval to the API.
 *
 * @param args - React Router action function arguments containing route params.
 * @returns Action result indicating successful approval.
 * @throws {Response} 400 error if workflow ID is missing from route params.
 * @example
 * ```typescript
 * const result = await approveAction({ params: { id: 'workflow-123' } });
 * // Returns: { success: true, action: 'approved' }
 * ```
 */
export async function approveAction({ params }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  await api.approveWorkflow(params.id);
  return { success: true, action: 'approved' };
}

/**
 * Rejects a workflow execution with feedback.
 *
 * Handles the reject action for a workflow route, extracting feedback from form data
 * and sending it to the API along with the rejection.
 *
 * @param args - React Router action function arguments containing route params and request.
 * @returns Action result indicating successful rejection.
 * @throws {Response} 400 error if workflow ID is missing or feedback is not provided.
 * @example
 * ```typescript
 * const formData = new FormData();
 * formData.set('feedback', 'Needs more tests');
 * const result = await rejectAction({
 *   params: { id: 'workflow-123' },
 *   request: new Request('/', { method: 'POST', body: formData })
 * });
 * // Returns: { success: true, action: 'rejected' }
 * ```
 */
export async function rejectAction({ params, request }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  const formData = await request.formData();
  const feedback = formData.get('feedback');

  if (!feedback || typeof feedback !== 'string') {
    throw new Response('Feedback required', { status: 400 });
  }

  await api.rejectWorkflow(params.id, feedback);
  return { success: true, action: 'rejected' };
}

/**
 * Cancels a workflow execution.
 *
 * Handles the cancel action for a workflow route, sending cancellation request to the API.
 *
 * @param args - React Router action function arguments containing route params.
 * @returns Action result indicating successful cancellation.
 * @throws {Response} 400 error if workflow ID is missing from route params.
 * @example
 * ```typescript
 * const result = await cancelAction({ params: { id: 'workflow-123' } });
 * // Returns: { success: true, action: 'cancelled' }
 * ```
 */
export async function cancelAction({ params }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  await api.cancelWorkflow(params.id);
  return { success: true, action: 'cancelled' };
}
