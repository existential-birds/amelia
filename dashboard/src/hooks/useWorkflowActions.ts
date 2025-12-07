import { useCallback } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import { api } from '../api/client';
import * as toast from '../components/Toast';
import type { WorkflowStatus } from '../types';

/**
 * Return type for the useWorkflowActions hook.
 */
interface UseWorkflowActionsResult {
  /**
   * Approves a workflow plan, allowing it to proceed to execution.
   *
   * @param workflowId - The unique identifier of the workflow to approve.
   * @param previousStatus - The previous status of the workflow (for optimistic updates).
   * @returns A promise that resolves when the approval is complete.
   */
  approveWorkflow: (workflowId: string, previousStatus: WorkflowStatus) => Promise<void>;

  /**
   * Rejects a workflow plan with feedback, preventing execution.
   *
   * @param workflowId - The unique identifier of the workflow to reject.
   * @param feedback - Feedback message explaining why the plan was rejected.
   * @param previousStatus - The previous status of the workflow (for optimistic updates).
   * @returns A promise that resolves when the rejection is complete.
   */
  rejectWorkflow: (workflowId: string, feedback: string, previousStatus: WorkflowStatus) => Promise<void>;

  /**
   * Cancels a running or pending workflow.
   *
   * @param workflowId - The unique identifier of the workflow to cancel.
   * @param previousStatus - The previous status of the workflow (for optimistic updates).
   * @returns A promise that resolves when the cancellation is complete.
   */
  cancelWorkflow: (workflowId: string, previousStatus: WorkflowStatus) => Promise<void>;

  /**
   * Checks if any action is currently pending for the specified workflow.
   *
   * @param workflowId - The unique identifier of the workflow to check.
   * @returns True if an action (approve, reject, or cancel) is pending for this workflow.
   */
  isActionPending: (workflowId: string) => boolean;
}

/**
 * Hook that provides workflow action handlers with optimistic updates and error handling.
 *
 * Manages all workflow state transitions including approval, rejection, and cancellation:
 * - Tracks pending actions in Zustand store to prevent duplicate requests
 * - Shows toast notifications for success and error states
 * - Handles API communication with automatic error recovery
 * - Provides action status checking for UI state management
 *
 * Each action follows this pattern:
 * 1. Add action to pending state (disables UI controls)
 * 2. Make API call
 * 3. Show success/error toast
 * 4. Remove action from pending state (re-enables UI controls)
 *
 * @returns An object containing action handlers and status checker.
 *
 * @example
 * ```tsx
 * function WorkflowCard({ workflow }) {
 *   const { approveWorkflow, rejectWorkflow, isActionPending } = useWorkflowActions();
 *   const isPending = isActionPending(workflow.id);
 *
 *   return (
 *     <div>
 *       <button
 *         onClick={() => approveWorkflow(workflow.id, workflow.status)}
 *         disabled={isPending}
 *       >
 *         Approve
 *       </button>
 *       <button
 *         onClick={() => rejectWorkflow(workflow.id, 'Needs revision', workflow.status)}
 *         disabled={isPending}
 *       >
 *         Reject
 *       </button>
 *     </div>
 *   );
 * }
 * ```
 */
export function useWorkflowActions(): UseWorkflowActionsResult {
  const { addPendingAction, removePendingAction, pendingActions } = useWorkflowStore();

  const approveWorkflow = useCallback(
    async (workflowId: string, _previousStatus: WorkflowStatus) => {
      const actionId = `approve-${workflowId}`;
      addPendingAction(actionId);

      try {
        await api.approveWorkflow(workflowId);
        toast.success('Plan approved');
      } catch (error) {
        toast.error(`Approval failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      } finally {
        removePendingAction(actionId);
      }
    },
    [addPendingAction, removePendingAction]
  );

  const rejectWorkflow = useCallback(
    async (workflowId: string, feedback: string, _previousStatus: WorkflowStatus) => {
      const actionId = `reject-${workflowId}`;
      addPendingAction(actionId);

      try {
        await api.rejectWorkflow(workflowId, feedback);
        toast.success('Plan rejected');
      } catch (error) {
        toast.error(`Rejection failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      } finally {
        removePendingAction(actionId);
      }
    },
    [addPendingAction, removePendingAction]
  );

  const cancelWorkflow = useCallback(
    async (workflowId: string, _previousStatus: WorkflowStatus) => {
      const actionId = `cancel-${workflowId}`;
      addPendingAction(actionId);

      try {
        await api.cancelWorkflow(workflowId);
        toast.success('Workflow cancelled');
      } catch (error) {
        toast.error(`Cancellation failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      } finally {
        removePendingAction(actionId);
      }
    },
    [addPendingAction, removePendingAction]
  );

  const isActionPending = useCallback(
    (workflowId: string) => {
      return pendingActions.some(
        (id) =>
          id === `approve-${workflowId}` ||
          id === `reject-${workflowId}` ||
          id === `cancel-${workflowId}`
      );
    },
    [pendingActions]
  );

  return {
    approveWorkflow,
    rejectWorkflow,
    cancelWorkflow,
    isActionPending,
  };
}
