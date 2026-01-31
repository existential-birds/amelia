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

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/active',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
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

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/wf-1',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
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
      {
        method: 'resumeWorkflow' as const,
        id: 'wf-1',
        expectedUrl: '/api/workflows/wf-1/resume',
      },
    ])(
      '$method should POST to correct endpoint without body',
      async ({ method, id, expectedUrl }) => {
        mockFetchSuccess({ status: 'ok' });

        await api[method](id);

        expect(global.fetch).toHaveBeenCalledWith(
          expectedUrl,
          expect.objectContaining({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: expect.any(AbortSignal),
          })
        );
      }
    );

    it('should POST rejectWorkflow with feedback in body', async () => {
      const id = 'wf-1';
      const feedback = 'Plan needs revision';

      mockFetchSuccess({ status: 'failed' });

      await api.rejectWorkflow(id, feedback);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/wf-1/reject',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feedback }),
          signal: expect.any(AbortSignal),
        })
      );
    });

    it('should handle HTTP errors on mutations', async () => {
      mockFetchError(403, 'Forbidden', 'FORBIDDEN');

      await expect(api.approveWorkflow('wf-1')).rejects.toThrow('Forbidden');
    });
  });

  describe('request timeout', () => {
    it('should convert AbortError to ApiError with timeout code', async () => {
      // Mock fetch that immediately throws AbortError (simulating timeout)
      const abortError = new Error('The operation was aborted');
      abortError.name = 'AbortError';

      (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(abortError);

      // The ApiError should be thrown with timeout details
      await expect(api.getWorkflows()).rejects.toMatchObject({
        message: 'Request timeout',
        code: 'TIMEOUT',
        status: 408,
      });
    });

    it('should pass AbortSignal to fetch', async () => {
      mockFetchSuccess({ workflows: [], total: 0, has_more: false });

      await api.getWorkflows();

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/active',
        expect.objectContaining({
          signal: expect.any(AbortSignal),
        })
      );
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
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows?status=completed',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows?status=failed',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows?status=cancelled',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
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

  // ==========================================================================
  // Queue Workflow Methods
  // ==========================================================================

  describe('startWorkflow', () => {
    it('should POST to /api/workflows/{id}/start', async () => {
      mockFetchSuccess({ workflow_id: 'wf-123', status: 'started' });

      const result = await api.startWorkflow('wf-123');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/wf-123/start',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: expect.any(AbortSignal),
        })
      );
      expect(result.workflow_id).toBe('wf-123');
      expect(result.status).toBe('started');
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(404, 'Workflow not found', 'NOT_FOUND');

      await expect(api.startWorkflow('wf-999')).rejects.toThrow('Workflow not found');
    });

    it('should handle conflict when workflow already running', async () => {
      mockFetchError(409, 'Workflow already running', 'CONFLICT');

      await expect(api.startWorkflow('wf-1')).rejects.toThrow('Workflow already running');
    });
  });

  describe('startBatch', () => {
    it('should POST to /api/workflows/start-batch with empty request', async () => {
      mockFetchSuccess({ started: ['wf-1', 'wf-2'], errors: {} });

      const result = await api.startBatch({});

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/start-batch',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
          signal: expect.any(AbortSignal),
        })
      );
      expect(result.started).toEqual(['wf-1', 'wf-2']);
      expect(result.errors).toEqual({});
    });

    it('should pass workflow_ids when provided', async () => {
      mockFetchSuccess({ started: ['wf-1'], errors: {} });

      await api.startBatch({ workflow_ids: ['wf-1'] });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/start-batch',
        expect.objectContaining({
          body: JSON.stringify({ workflow_ids: ['wf-1'] }),
        })
      );
    });

    it('should pass worktree_path when provided', async () => {
      mockFetchSuccess({ started: ['wf-1'], errors: {} });

      await api.startBatch({ worktree_path: '/repo' });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/start-batch',
        expect.objectContaining({
          body: JSON.stringify({ worktree_path: '/repo' }),
        })
      );
    });

    it('should pass both workflow_ids and worktree_path', async () => {
      mockFetchSuccess({ started: ['wf-1'], errors: {} });

      await api.startBatch({
        workflow_ids: ['wf-1', 'wf-2'],
        worktree_path: '/repo',
      });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows/start-batch',
        expect.objectContaining({
          body: JSON.stringify({ workflow_ids: ['wf-1', 'wf-2'], worktree_path: '/repo' }),
        })
      );
    });

    it('should handle partial errors in batch response', async () => {
      mockFetchSuccess({
        started: ['wf-1'],
        errors: { 'wf-2': 'Already running' },
      });

      const result = await api.startBatch({ workflow_ids: ['wf-1', 'wf-2'] });

      expect(result.started).toEqual(['wf-1']);
      expect(result.errors).toEqual({ 'wf-2': 'Already running' });
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(500, 'Internal server error', 'INTERNAL_ERROR');

      await expect(api.startBatch({})).rejects.toThrow('Internal server error');
    });
  });

  describe('getWorkflowDefaults', () => {
    it('should return worktree_path and profile from most recent workflow', async () => {
      mockFetchSuccess({
        workflows: [
          {
            id: 'wf-1',
            issue_id: 'TASK-001',
            worktree_path: '/Users/test/project',
            profile: 'dev-profile',
            status: 'completed',
            created_at: '2025-01-01T09:00:00Z',
            started_at: '2025-01-01T10:00:00Z',

            total_cost_usd: null,
            total_tokens: null,
            total_duration_ms: null,
          },
        ],
        total: 1,
        has_more: false,
      });

      const result = await api.getWorkflowDefaults();

      expect(result).toEqual({
        worktree_path: '/Users/test/project',
        profile: 'dev-profile',
      });
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/workflows?limit=1',
        expect.anything()
      );
    });

    it('should return null values when no workflows exist', async () => {
      mockFetchSuccess({
        workflows: [],
        total: 0,
        has_more: false,
      });

      const result = await api.getWorkflowDefaults();

      expect(result).toEqual({
        worktree_path: null,
        profile: null,
      });
    });

    it('should return null profile when workflow has no profile', async () => {
      mockFetchSuccess({
        workflows: [
          {
            id: 'wf-1',
            issue_id: 'TASK-001',
            worktree_path: '/Users/test/project',
            profile: null,
            status: 'completed',
            created_at: '2025-01-01T09:00:00Z',
            started_at: '2025-01-01T10:00:00Z',

            total_cost_usd: null,
            total_tokens: null,
            total_duration_ms: null,
          },
        ],
        total: 1,
        has_more: false,
      });

      const result = await api.getWorkflowDefaults();

      expect(result).toEqual({
        worktree_path: '/Users/test/project',
        profile: null,
      });
    });
  });

  // ==========================================================================
  // Config and Files API Methods
  // ==========================================================================

  describe('getConfig', () => {
    it('returns config with working_dir', async () => {
      const mockResponse = {
        working_dir: '/tmp/test-repo',
        max_concurrent: 5,
      };

      mockFetchSuccess(mockResponse);

      const result = await api.getConfig();

      expect(result).toEqual(mockResponse);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/config',
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
    });

    it('should handle HTTP errors', async () => {
      mockFetchError(500, 'Internal server error', 'INTERNAL_ERROR');

      await expect(api.getConfig()).rejects.toThrow('Internal server error');
    });
  });

  describe('readFile', () => {
    it('returns file content and filename', async () => {
      const mockResponse = {
        content: '# Test Design\n\nContent here.',
        filename: 'test-design.md',
      };

      mockFetchSuccess(mockResponse);

      const result = await api.readFile('/path/to/test-design.md');

      expect(result).toEqual(mockResponse);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/files/read',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: '/path/to/test-design.md' }),
          signal: expect.any(AbortSignal),
        })
      );
    });

    it('should handle file not found errors', async () => {
      mockFetchError(404, 'File not found', 'NOT_FOUND');

      await expect(api.readFile('/path/to/nonexistent.md')).rejects.toThrow('File not found');
    });

    it('should handle path validation errors', async () => {
      mockFetchError(400, 'Invalid path', 'VALIDATION_ERROR');

      await expect(api.readFile('../relative/path.md')).rejects.toThrow('Invalid path');
    });
  });
});
