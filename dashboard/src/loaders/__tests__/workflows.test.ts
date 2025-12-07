import { describe, it, expect, vi, beforeEach } from 'vitest';
import { workflowsLoader, workflowDetailLoader, historyLoader } from '../workflows';
import { api } from '../../api/client';

vi.mock('../../api/client');

describe('Workflow Loaders', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('workflowsLoader', () => {
    it('should fetch active workflows', async () => {
      const mockWorkflows = [
        {
          id: 'wf-1',
          issue_id: 'ISSUE-1',
          worktree_name: 'main',
          status: 'in_progress' as const,
          started_at: '2025-12-01T10:00:00Z',
          current_stage: 'architect',
        },
      ];

      vi.mocked(api.getWorkflows).mockResolvedValueOnce(mockWorkflows);

      const result = await workflowsLoader();

      expect(api.getWorkflows).toHaveBeenCalledTimes(1);
      expect(result).toEqual({ workflows: mockWorkflows });
    });

    it('should propagate API errors', async () => {
      vi.mocked(api.getWorkflows).mockRejectedValueOnce(new Error('Network error'));

      await expect(workflowsLoader()).rejects.toThrow('Network error');
    });
  });

  describe('workflowDetailLoader', () => {
    it('should fetch workflow by ID from params', async () => {
      const mockWorkflow = {
        id: 'wf-1',
        issue_id: 'ISSUE-1',
        worktree_path: '/path',
        worktree_name: 'main',
        status: 'in_progress' as const,
        started_at: '2025-12-01T10:00:00Z',
        completed_at: null,
        failure_reason: null,
        current_stage: 'architect',
        plan: null,
        token_usage: {},
        recent_events: [],
      };

      vi.mocked(api.getWorkflow).mockResolvedValueOnce(mockWorkflow);

      const result = await workflowDetailLoader({
        params: { id: 'wf-1' },
        request: new Request('http://localhost/workflows/wf-1'),
      } as unknown as Parameters<typeof workflowDetailLoader>[0]);

      expect(api.getWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ workflow: mockWorkflow });
    });

    it('should throw 400 if ID is missing', async () => {
      try {
        await workflowDetailLoader({
          params: {},
          request: new Request('http://localhost/workflows'),
        } as unknown as Parameters<typeof workflowDetailLoader>[0]);
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(Response);
        expect((error as Response).status).toBe(400);
      }
    });
  });

  describe('historyLoader', () => {
    it('should fetch workflow history', async () => {
      const mockHistory = [
        {
          id: 'wf-old',
          issue_id: 'ISSUE-OLD',
          worktree_name: 'old-branch',
          status: 'completed' as const,
          started_at: '2025-11-01T10:00:00Z',
          current_stage: null,
        },
      ];

      vi.mocked(api.getWorkflowHistory).mockResolvedValueOnce(mockHistory);

      const result = await historyLoader();

      expect(api.getWorkflowHistory).toHaveBeenCalledTimes(1);
      expect(result).toEqual({ workflows: mockHistory });
    });
  });
});
