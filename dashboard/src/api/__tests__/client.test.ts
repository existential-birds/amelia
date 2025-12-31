import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '../client';
import { createMockWorkflowSummary, createMockWorkflowDetail } from '@/__tests__/fixtures';

// Mock fetch globally
global.fetch = vi.fn();

// ============================================================================
// Test Helpers
// ============================================================================

function mockFetchSuccess<T>(data: T) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: true,
    json: async () => data,
  });
}

function mockFetchError(status: number, error: string, code: string) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: false,
    status,
    json: async () => ({ error, code }),
  });
}

// ============================================================================
// Tests
// ============================================================================

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getWorkflows', () => {
    it('should fetch active workflows', async () => {
      const mockWorkflows = [createMockWorkflowSummary()];

      mockFetchSuccess({ workflows: mockWorkflows, total: 1, has_more: false });

      const result = await api.getWorkflows();

      expect(global.fetch).toHaveBeenCalledWith('/api/workflows/active');
      expect(result).toEqual(mockWorkflows);
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(500, 'Internal server error', 'INTERNAL_ERROR');

      await expect(api.getWorkflows()).rejects.toThrow('Internal server error');
    });
  });

  describe('getWorkflow', () => {
    it('should fetch single workflow by ID', async () => {
      const mockWorkflow = createMockWorkflowDetail({ id: 'wf-1' });

      mockFetchSuccess(mockWorkflow);

      const result = await api.getWorkflow('wf-1');

      expect(global.fetch).toHaveBeenCalledWith('/api/workflows/wf-1');
      expect(result.id).toBe('wf-1');
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(404, 'Workflow not found', 'NOT_FOUND');

      await expect(api.getWorkflow('wf-999')).rejects.toThrow('Workflow not found');
    });
  });

  describe('workflow mutations', () => {
    it.each([
      {
        method: 'approveWorkflow' as const,
        id: 'wf-1',
        expectedUrl: '/api/workflows/wf-1/approve',
      },
      {
        method: 'cancelWorkflow' as const,
        id: 'wf-1',
        expectedUrl: '/api/workflows/wf-1/cancel',
      },
    ])(
      '$method should POST to correct endpoint without body',
      async ({ method, id, expectedUrl }) => {
        mockFetchSuccess({ status: 'ok' });

        await api[method](id);

        expect(global.fetch).toHaveBeenCalledWith(expectedUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
      }
    );

    it('should POST rejectWorkflow with feedback in body', async () => {
      const id = 'wf-1';
      const feedback = 'Plan needs revision';

      mockFetchSuccess({ status: 'failed' });

      await api.rejectWorkflow(id, feedback);

      expect(global.fetch).toHaveBeenCalledWith('/api/workflows/wf-1/reject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback }),
      });
    });

    it('should handle HTTP errors on mutations', async () => {
      mockFetchError(403, 'Forbidden', 'FORBIDDEN');

      await expect(api.approveWorkflow('wf-1')).rejects.toThrow('Forbidden');
    });
  });

  describe('getWorkflowHistory', () => {
    it('should fetch workflows with completed, failed, and cancelled statuses in parallel', async () => {
      const completedWorkflows = [
        createMockWorkflowSummary({
          id: 'wf-1',
          status: 'completed',
          started_at: '2025-12-01T10:00:00Z',
        }),
      ];
      const failedWorkflows = [
        createMockWorkflowSummary({
          id: 'wf-2',
          status: 'failed',
          started_at: '2025-12-01T11:00:00Z',
        }),
      ];
      const cancelledWorkflows = [
        createMockWorkflowSummary({
          id: 'wf-3',
          status: 'cancelled',
          started_at: '2025-12-01T09:00:00Z',
        }),
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

    it('should handle HTTP errors', async () => {
      // getWorkflowHistory makes 3 parallel requests, mock the first to fail
      // (Promise.all will reject on first error)
      (global.fetch as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce({
          ok: false,
          status: 500,
          json: async () => ({ error: 'Internal server error', code: 'INTERNAL_ERROR' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ workflows: [], total: 0, has_more: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ workflows: [], total: 0, has_more: false }),
        });

      await expect(api.getWorkflowHistory()).rejects.toThrow('Internal server error');
    });
  });
});
