/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { workflowsLoader, workflowDetailLoader, historyLoader } from '../workflows';
import { api } from '../../api/client';
import { getActiveWorkflow } from '../../utils/workflow';
import { createMockWorkflowSummary, createMockWorkflowDetail } from '@/__tests__/fixtures';
import type { LoaderFunctionArgs } from 'react-router-dom';

vi.mock('../../utils/workflow');

vi.mock('../../api/client');

/**
 * Helper to create LoaderFunctionArgs for testing
 */
function createLoaderArgs(params: Record<string, string>): LoaderFunctionArgs {
  return {
    params,
    request: new Request('http://localhost'),
  } as unknown as LoaderFunctionArgs;
}


describe('Workflow Loaders', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('workflowsLoader', () => {
    it('should return workflows list and detail in response', async () => {
      const mockWorkflowSummary = createMockWorkflowSummary({
        id: 'wf-1',
        issue_id: 'ISSUE-1',
        worktree_name: 'main',
        status: 'in_progress',
        started_at: '2025-12-01T10:00:00Z',
        current_stage: 'architect',
      });
      const mockWorkflowDetail = createMockWorkflowDetail({
        id: 'wf-1',
        issue_id: 'ISSUE-1',
        worktree_name: 'main',
        status: 'in_progress',
        started_at: '2025-12-01T10:00:00Z',
        current_stage: 'architect',
        worktree_path: '/path',
      });

      vi.mocked(api.getWorkflows).mockResolvedValueOnce([mockWorkflowSummary]);
      vi.mocked(getActiveWorkflow).mockReturnValueOnce(mockWorkflowSummary);
      vi.mocked(api.getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);

      const result = await workflowsLoader(createLoaderArgs({}));

      expect(api.getWorkflows).toHaveBeenCalledTimes(1);
      expect(result).toHaveProperty('workflows');
      expect(result).toHaveProperty('detail');
      expect(result.workflows).toEqual([mockWorkflowSummary]);
      expect(result.detail).toEqual(mockWorkflowDetail);
    });

    it('should return null detail when no workflows exist', async () => {
      vi.mocked(api.getWorkflows).mockResolvedValueOnce([]);
      vi.mocked(getActiveWorkflow).mockReturnValueOnce(null);

      const result = await workflowsLoader(createLoaderArgs({}));

      expect(result.workflows).toEqual([]);
      expect(result.detail).toBeNull();
      expect(api.getWorkflow).not.toHaveBeenCalled();
    });

    it('should return null detail when detail API call fails', async () => {
      const mockWorkflowSummary = createMockWorkflowSummary({
        id: 'wf-1',
        issue_id: 'ISSUE-1',
        worktree_name: 'main',
        status: 'in_progress',
        started_at: '2025-12-01T10:00:00Z',
        current_stage: 'architect',
      });

      vi.mocked(api.getWorkflows).mockResolvedValueOnce([mockWorkflowSummary]);
      vi.mocked(getActiveWorkflow).mockReturnValueOnce(mockWorkflowSummary);
      vi.mocked(api.getWorkflow).mockRejectedValueOnce(new Error('Detail fetch failed'));

      const result = await workflowsLoader(createLoaderArgs({}));

      expect(result.workflows).toEqual([mockWorkflowSummary]);
      expect(result.detail).toBeNull();
    });

    it('should include active workflow detail when running workflow exists', async () => {
      const runningWorkflow = createMockWorkflowSummary({
        id: 'wf-1',
        status: 'in_progress',
      });
      const runningDetail = createMockWorkflowDetail({
        id: 'wf-1',
        status: 'in_progress',
      });

      vi.mocked(api.getWorkflows).mockResolvedValueOnce([runningWorkflow]);
      vi.mocked(getActiveWorkflow).mockReturnValueOnce(runningWorkflow);
      vi.mocked(api.getWorkflow).mockResolvedValueOnce(runningDetail);

      const result = await workflowsLoader(createLoaderArgs({}));

      expect(getActiveWorkflow).toHaveBeenCalledWith([runningWorkflow]);
      expect(api.getWorkflow).toHaveBeenCalledWith(runningWorkflow.id);
      expect(result.detail).toEqual(runningDetail);
    });

    it('should propagate API errors from getWorkflows', async () => {
      vi.mocked(api.getWorkflows).mockRejectedValueOnce(new Error('Network error'));

      await expect(workflowsLoader(createLoaderArgs({}))).rejects.toThrow('Network error');
    });
  });

  describe('workflowDetailLoader', () => {
    it('should fetch workflow by ID from params', async () => {
      const mockWorkflowDetail = createMockWorkflowDetail({ id: 'wf-1' });

      vi.mocked(api.getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);

      const result = await workflowDetailLoader(createLoaderArgs({ id: 'wf-1' }));

      expect(api.getWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ workflow: mockWorkflowDetail });
    });

    it('should throw 400 if ID is missing', async () => {
      await expect(
        workflowDetailLoader(createLoaderArgs({}))
      ).rejects.toThrowError(
        expect.objectContaining({ status: 400 })
      );
    });
  });

  describe('historyLoader', () => {
    it('should fetch workflow history', async () => {
      const mockWorkflowHistory = createMockWorkflowSummary({
        id: 'wf-old',
        issue_id: 'ISSUE-OLD',
        worktree_name: 'old-branch',
        status: 'completed',
        started_at: '2025-11-01T10:00:00Z',
        current_stage: null,
      });

      vi.mocked(api.getWorkflowHistory).mockResolvedValueOnce([mockWorkflowHistory]);

      const result = await historyLoader(createLoaderArgs({}));

      expect(api.getWorkflowHistory).toHaveBeenCalledTimes(1);
      expect(result).toEqual({ workflows: [mockWorkflowHistory] });
    });
  });
});
