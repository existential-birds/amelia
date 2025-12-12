/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

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
      ['approveAction', approveAction, 'approved'],
      ['rejectAction', rejectAction, 'rejected'],
      ['cancelAction', cancelAction, 'cancelled'],
    ])('%s should return error if ID is missing', async (_name, action, actionType) => {
      const args = createActionArgs({});
      const result = await action(args);

      expect(result).toEqual({
        success: false,
        action: actionType,
        error: 'Workflow ID required',
      });
    });
  });

  describe('approveAction', () => {
    it('should approve workflow by ID from params', async () => {
      vi.mocked(api.approveWorkflow).mockResolvedValueOnce(undefined);

      const result = await approveAction(createActionArgs({ id: 'wf-1' }));

      expect(api.approveWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ success: true, action: 'approved' });
    });

    it('should return error on API failure', async () => {
      vi.mocked(api.approveWorkflow).mockRejectedValueOnce(new Error('Server error'));

      const result = await approveAction(createActionArgs({ id: 'wf-1' }));

      expect(result).toEqual({
        success: false,
        action: 'approved',
        error: 'Server error',
      });
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

    it('should return error if feedback is missing', async () => {
      const formData = new FormData();
      // No feedback field

      const result = await rejectAction(createActionArgs({ id: 'wf-1' }, { body: formData }));

      expect(result).toEqual({
        success: false,
        action: 'rejected',
        error: 'Feedback required',
      });
    });

    it('should return error on API failure', async () => {
      vi.mocked(api.rejectWorkflow).mockRejectedValueOnce(new Error('Network error'));

      const formData = new FormData();
      formData.append('feedback', 'Fix this');

      const result = await rejectAction(createActionArgs({ id: 'wf-1' }, { body: formData }));

      expect(result).toEqual({
        success: false,
        action: 'rejected',
        error: 'Network error',
      });
    });
  });

  describe('cancelAction', () => {
    it('should cancel workflow by ID from params', async () => {
      vi.mocked(api.cancelWorkflow).mockResolvedValueOnce(undefined);

      const result = await cancelAction(createActionArgs({ id: 'wf-1' }));

      expect(api.cancelWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ success: true, action: 'cancelled' });
    });

    it('should return error on API failure', async () => {
      vi.mocked(api.cancelWorkflow).mockRejectedValueOnce(new Error('Cannot cancel'));

      const result = await cancelAction(createActionArgs({ id: 'wf-1' }));

      expect(result).toEqual({
        success: false,
        action: 'cancelled',
        error: 'Cannot cancel',
      });
    });
  });
});
