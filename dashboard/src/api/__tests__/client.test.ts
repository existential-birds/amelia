import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '../client';
import type { WorkflowSummary } from '../../types';

// Mock fetch globally
global.fetch = vi.fn();

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getWorkflows', () => {
    it('should fetch active workflows', async () => {
      const mockWorkflows: WorkflowSummary[] = [
        {
          id: 'wf-1',
          issue_id: 'ISSUE-1',
          worktree_name: 'main',
          status: 'in_progress',
          started_at: '2025-12-01T10:00:00Z',
          current_stage: 'architect',
        },
      ];

      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ workflows: mockWorkflows, total: 1, has_more: false }),
      });

      const result = await api.getWorkflows();

      expect(global.fetch).toHaveBeenCalledWith('/api/workflows/active');
      expect(result).toEqual(mockWorkflows);
    });

    it('should handle fetch errors', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('Network error'));

      await expect(api.getWorkflows()).rejects.toThrow('Network error');
    });

    it('should handle HTTP errors', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ error: 'Internal server error', code: 'INTERNAL_ERROR' }),
      });

      await expect(api.getWorkflows()).rejects.toThrow('Internal server error');
    });
  });

  describe('getWorkflow', () => {
    it('should fetch single workflow by ID', async () => {
      const mockWorkflow = {
        id: 'wf-1',
        issue_id: 'ISSUE-1',
        worktree_path: '/path/to/worktree',
        worktree_name: 'main',
        status: 'in_progress',
        started_at: '2025-12-01T10:00:00Z',
        completed_at: null,
        failure_reason: null,
        current_stage: 'architect',
        plan: null,
        token_usage: {},
        recent_events: [],
      };

      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        json: async () => mockWorkflow,
      });

      const result = await api.getWorkflow('wf-1');

      expect(global.fetch).toHaveBeenCalledWith('/api/workflows/wf-1');
      expect(result.id).toBe('wf-1');
    });
  });

  describe('approveWorkflow', () => {
    it('should POST to approve endpoint', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'in_progress' }),
      });

      await api.approveWorkflow('wf-1');

      expect(global.fetch).toHaveBeenCalledWith('/api/workflows/wf-1/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
    });
  });

  describe('rejectWorkflow', () => {
    it('should POST to reject endpoint with feedback', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'failed' }),
      });

      await api.rejectWorkflow('wf-1', 'Plan needs revision');

      expect(global.fetch).toHaveBeenCalledWith('/api/workflows/wf-1/reject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback: 'Plan needs revision' }),
      });
    });
  });

  describe('cancelWorkflow', () => {
    it('should POST to cancel endpoint', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'cancelled' }),
      });

      await api.cancelWorkflow('wf-1');

      expect(global.fetch).toHaveBeenCalledWith('/api/workflows/wf-1/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
    });
  });

  describe('getWorkflowHistory', () => {
    it('should fetch workflows with completed, failed, and cancelled statuses in parallel', async () => {
      const completedWorkflows = [
        { id: 'wf-1', status: 'completed', started_at: '2025-12-01T10:00:00Z' },
      ];
      const failedWorkflows = [
        { id: 'wf-2', status: 'failed', started_at: '2025-12-01T11:00:00Z' },
      ];
      const cancelledWorkflows = [
        { id: 'wf-3', status: 'cancelled', started_at: '2025-12-01T09:00:00Z' },
      ];

      (global.fetch as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ workflows: completedWorkflows, total: 1, has_more: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ workflows: failedWorkflows, total: 1, has_more: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ workflows: cancelledWorkflows, total: 1, has_more: false }),
        });

      const result = await api.getWorkflowHistory();

      expect(global.fetch).toHaveBeenCalledTimes(3);
      expect(global.fetch).toHaveBeenCalledWith('/api/workflows?status=completed');
      expect(global.fetch).toHaveBeenCalledWith('/api/workflows?status=failed');
      expect(global.fetch).toHaveBeenCalledWith('/api/workflows?status=cancelled');
      // Should be sorted by started_at descending
      expect(result).toHaveLength(3);
      expect(result[0]!.id).toBe('wf-2'); // Most recent (11:00)
      expect(result[1]!.id).toBe('wf-1'); // 10:00
      expect(result[2]!.id).toBe('wf-3'); // Oldest (09:00)
    });
  });
});
