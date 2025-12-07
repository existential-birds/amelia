import { describe, it, expect, vi, beforeEach } from 'vitest';
import { approveAction, rejectAction, cancelAction } from '../workflows';
import { api } from '../../api/client';
import type { ActionFunctionArgs } from 'react-router-dom';

vi.mock('../../api/client');

/**
 * Helper to create ActionFunctionArgs for testing
 */
function createActionArgs(params: Record<string, string>, requestInit?: RequestInit): ActionFunctionArgs {
  return {
    params,
    request: new Request('http://localhost', { method: 'POST', ...requestInit }),
  } as unknown as ActionFunctionArgs;
}

describe('Workflow Actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('validation', () => {
    it.each([
      ['approveAction', approveAction],
      ['rejectAction', rejectAction],
      ['cancelAction', cancelAction],
    ])('%s should throw 400 if ID is missing', async (_name, action) => {
      const args = createActionArgs({});
      await expect(action(args)).rejects.toThrowError(
        expect.objectContaining({ status: 400 })
      );
    });
  });

  describe('approveAction', () => {
    it('should approve workflow by ID from params', async () => {
      vi.mocked(api.approveWorkflow).mockResolvedValueOnce(undefined);

      const result = await approveAction(createActionArgs({ id: 'wf-1' }));

      expect(api.approveWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ success: true, action: 'approved' });
    });

    it('should propagate API errors', async () => {
      vi.mocked(api.approveWorkflow).mockRejectedValueOnce(new Error('Server error'));

      await expect(
        approveAction(createActionArgs({ id: 'wf-1' }))
      ).rejects.toThrow('Server error');
    });
  });

  describe('rejectAction', () => {
    it('should reject workflow with feedback from form data', async () => {
      vi.mocked(api.rejectWorkflow).mockResolvedValueOnce(undefined);

      const formData = new FormData();
      formData.append('feedback', 'Plan needs revision');

      const result = await rejectAction(createActionArgs({ id: 'wf-1' }, { body: formData }));

      expect(api.rejectWorkflow).toHaveBeenCalledWith('wf-1', 'Plan needs revision');
      expect(result).toEqual({ success: true, action: 'rejected' });
    });

    it('should throw 400 if feedback is missing', async () => {
      const formData = new FormData();
      // No feedback field

      await expect(
        rejectAction(createActionArgs({ id: 'wf-1' }, { body: formData }))
      ).rejects.toThrowError(
        expect.objectContaining({ status: 400 })
      );
    });
  });

  describe('cancelAction', () => {
    it('should cancel workflow by ID from params', async () => {
      vi.mocked(api.cancelWorkflow).mockResolvedValueOnce(undefined);

      const result = await cancelAction(createActionArgs({ id: 'wf-1' }));

      expect(api.cancelWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ success: true, action: 'cancelled' });
    });
  });
});
