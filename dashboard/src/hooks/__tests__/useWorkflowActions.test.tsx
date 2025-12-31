import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useWorkflowActions } from '../useWorkflowActions';
import { useWorkflowStore } from '../../store/workflowStore';
import { api } from '../../api/client';
import * as toast from '../../components/Toast';

vi.mock('../../api/client');
vi.mock('../../components/Toast', () => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));

describe('useWorkflowActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkflowStore.setState({
      eventsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: [],
    });
  });

  describe.each([
    {
      action: 'approveWorkflow' as const,
      actionId: 'approve',
      apiMethod: 'approveWorkflow' as const,
      args: ['wf-1', 'blocked' as const] as const,
      successMessage: 'Plan approved',
      errorPrefix: 'Approval failed',
    },
    {
      action: 'rejectWorkflow' as const,
      actionId: 'reject',
      apiMethod: 'rejectWorkflow' as const,
      args: ['wf-1', 'Needs revision', 'blocked' as const] as const,
      successMessage: 'Plan rejected',
      errorPrefix: 'Rejection failed',
    },
    {
      action: 'cancelWorkflow' as const,
      actionId: 'cancel',
      apiMethod: 'cancelWorkflow' as const,
      args: ['wf-1', 'in_progress' as const] as const,
      successMessage: 'Workflow cancelled',
      errorPrefix: 'Cancellation failed',
    },
  ])('$action', ({ action, actionId, apiMethod, args, successMessage, errorPrefix }) => {
    it('should add pending action during request', async () => {
      vi.mocked(api[apiMethod]).mockImplementationOnce(
        () => new Promise((resolve) => { setTimeout(resolve, 100); })
      );

      const { result } = renderHook(() => useWorkflowActions());

      act(() => {
        (result.current[action] as any)(...args);
      });

      await waitFor(() => {
        expect(useWorkflowStore.getState().pendingActions.includes(`${actionId}-wf-1`)).toBe(true);
      });

      await waitFor(() => {
        expect(useWorkflowStore.getState().pendingActions.includes(`${actionId}-wf-1`)).toBe(false);
      });
    });

    it('should show success toast on success', async () => {
      vi.mocked(api[apiMethod]).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useWorkflowActions());

      await act(async () => {
        await (result.current[action] as any)(...args);
      });

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(successMessage);
      });
    });

    it('should show error toast on failure', async () => {
      vi.mocked(api[apiMethod]).mockRejectedValueOnce(new Error('Server error'));

      const { result } = renderHook(() => useWorkflowActions());

      await act(async () => {
        await (result.current[action] as any)(...args);
      });

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(`${errorPrefix}: Server error`);
      });
    });
  });

  describe('isActionPending', () => {
    it('should return true if action is pending', () => {
      useWorkflowStore.setState({ pendingActions: ['approve-wf-1'] });

      const { result } = renderHook(() => useWorkflowActions());

      expect(result.current.isActionPending('wf-1')).toBe(true);
    });

    it('should return false if no action is pending', () => {
      useWorkflowStore.setState({ pendingActions: [] });

      const { result } = renderHook(() => useWorkflowActions());

      expect(result.current.isActionPending('wf-1')).toBe(false);
    });

    it('should check for any action type for the workflow', () => {
      useWorkflowStore.setState({ pendingActions: ['reject-wf-1'] });

      const { result } = renderHook(() => useWorkflowActions());

      expect(result.current.isActionPending('wf-1')).toBe(true);
    });

    it('should not match workflow IDs that share a suffix', () => {
      useWorkflowStore.setState({ pendingActions: ['approve-wf-11'] });

      const { result } = renderHook(() => useWorkflowActions());

      // wf-1 should NOT match approve-wf-11 even though "wf-11" ends with "1"
      expect(result.current.isActionPending('wf-1')).toBe(false);
      expect(result.current.isActionPending('wf-11')).toBe(true);
    });
  });
});
