import { describe, it, expect, vi, beforeEach } from 'vitest';
import { workflowsLoader, workflowDetailLoader, historyLoader } from '../workflows';
import { api } from '../../api/client';
import type { LoaderFunctionArgs } from 'react-router-dom';

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

/**
 * Mock workflow data fixtures
 */
const mockWorkflowSummary = {
  id: 'wf-1',
  issue_id: 'ISSUE-1',
  worktree_name: 'main',
  status: 'in_progress' as const,
  started_at: '2025-12-01T10:00:00Z',
  current_stage: 'architect',
};

const mockWorkflowDetail = {
  ...mockWorkflowSummary,
  worktree_path: '/path',
  completed_at: null,
  failure_reason: null,
  plan: null,
  token_usage: {},
  recent_events: [],
};

const mockWorkflowHistory = {
  id: 'wf-old',
  issue_id: 'ISSUE-OLD',
  worktree_name: 'old-branch',
  status: 'completed' as const,
  started_at: '2025-11-01T10:00:00Z',
  current_stage: null,
};

describe('Workflow Loaders', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('workflowsLoader', () => {
    it('should fetch active workflows', async () => {
      vi.mocked(api.getWorkflows).mockResolvedValueOnce([mockWorkflowSummary]);

      const result = await workflowsLoader();

      expect(api.getWorkflows).toHaveBeenCalledTimes(1);
      expect(result).toEqual({ workflows: [mockWorkflowSummary] });
    });

    it('should propagate API errors', async () => {
      vi.mocked(api.getWorkflows).mockRejectedValueOnce(new Error('Network error'));

      await expect(workflowsLoader()).rejects.toThrow('Network error');
    });
  });

  describe('workflowDetailLoader', () => {
    it('should fetch workflow by ID from params', async () => {
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
      vi.mocked(api.getWorkflowHistory).mockResolvedValueOnce([mockWorkflowHistory]);

      const result = await historyLoader();

      expect(api.getWorkflowHistory).toHaveBeenCalledTimes(1);
      expect(result).toEqual({ workflows: [mockWorkflowHistory] });
    });
  });
});
