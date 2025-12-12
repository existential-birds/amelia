/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { api } from '@/api/client';
import type { ActionFunctionArgs } from 'react-router-dom';
import type { ActionResult } from '@/types/api';

/**
 * Approves a workflow execution.
 *
 * Handles the approve action for a workflow route, sending approval to the API.
 *
 * @param args - React Router action function arguments containing route params.
 * @returns Action result indicating successful approval or error details.
 * @example
 * ```typescript
 * const result = await approveAction({ params: { id: 'workflow-123' } });
 * // Success: { success: true, action: 'approved' }
 * // Error: { success: false, action: 'approved', error: 'Workflow ID required' }
 * ```
 */
export async function approveAction({ params }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    return { success: false, action: 'approved', error: 'Workflow ID required' };
  }

  try {
    await api.approveWorkflow(params.id);
    return { success: true, action: 'approved' };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to approve workflow';
    return { success: false, action: 'approved', error: message };
  }
}

/**
 * Rejects a workflow execution with feedback.
 *
 * Handles the reject action for a workflow route, extracting feedback from form data
 * and sending it to the API along with the rejection.
 *
 * @param args - React Router action function arguments containing route params and request.
 * @returns Action result indicating successful rejection or error details.
 * @example
 * ```typescript
 * const formData = new FormData();
 * formData.set('feedback', 'Needs more tests');
 * const result = await rejectAction({
 *   params: { id: 'workflow-123' },
 *   request: new Request('/', { method: 'POST', body: formData })
 * });
 * // Success: { success: true, action: 'rejected' }
 * // Error: { success: false, action: 'rejected', error: 'Feedback required' }
 * ```
 */
export async function rejectAction({ params, request }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    return { success: false, action: 'rejected', error: 'Workflow ID required' };
  }

  try {
    const formData = await request.formData();
    const feedback = formData.get('feedback');

    if (!feedback || typeof feedback !== 'string') {
      return { success: false, action: 'rejected', error: 'Feedback required' };
    }

    await api.rejectWorkflow(params.id, feedback);
    return { success: true, action: 'rejected' };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to reject workflow';
    return { success: false, action: 'rejected', error: message };
  }
}

/**
 * Cancels a workflow execution.
 *
 * Handles the cancel action for a workflow route, sending cancellation request to the API.
 *
 * @param args - React Router action function arguments containing route params.
 * @returns Action result indicating successful cancellation or error details.
 * @example
 * ```typescript
 * const result = await cancelAction({ params: { id: 'workflow-123' } });
 * // Success: { success: true, action: 'cancelled' }
 * // Error: { success: false, action: 'cancelled', error: 'Workflow ID required' }
 * ```
 */
export async function cancelAction({ params }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    return { success: false, action: 'cancelled', error: 'Workflow ID required' };
  }

  try {
    await api.cancelWorkflow(params.id);
    return { success: true, action: 'cancelled' };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to cancel workflow';
    return { success: false, action: 'cancelled', error: message };
  }
}
