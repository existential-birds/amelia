# Zustand Store & WebSocket Hook Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** ⏳ Not Started

**Goal:** Implement a hybrid data architecture using React Router v7 loaders for initial data, Zustand for real-time state, WebSocket connection hook with reconnection logic, and React Router actions for mutations.

**Architecture:** React Router v7 loaders for initial data fetching and revalidation, Zustand store for real-time WebSocket events and UI state (with sessionStorage persistence), WebSocket hook with exponential backoff reconnection and sequence gap detection, REST API client using fetch, React Router actions with useFetcher for mutations.

**Tech Stack:** Zustand, TypeScript, Vitest, React Testing Library, native fetch API

**Depends on:** Plan 8 (React Dashboard Setup)

---

## Task 1: Extend TypeScript Types for React Router

> **Depends on:** This task extends types created in Plan 08 Task 8. Those types must exist first.

**Files:**
- Create: `dashboard/src/types/api.ts` (additional React Router specific types)

**Step 1: Write the failing test**

```typescript
// dashboard/src/types/__tests__/api.test.ts
import { describe, it, expect } from 'vitest';
import type {
  WorkflowsLoaderData,
  WorkflowDetailLoaderData,
  ActionResult,
} from '../api';

describe('React Router Type Definitions', () => {
  it('should create valid WorkflowsLoaderData object', () => {
    const loaderData: WorkflowsLoaderData = {
      workflows: [
        {
          id: 'wf-123',
          issue_id: 'ISSUE-456',
          worktree_path: '/path',
          worktree_name: 'feature-branch',
          status: 'in_progress',
          started_at: '2025-12-01T10:00:00Z',
          completed_at: null,
          current_stage: 'architect',
        },
      ],
    };

    expect(loaderData.workflows).toHaveLength(1);
    expect(loaderData.workflows[0].id).toBe('wf-123');
  });

  it('should create valid WorkflowDetailLoaderData object', () => {
    const loaderData: WorkflowDetailLoaderData = {
      workflow: {
        id: 'wf-123',
        issue_id: 'ISSUE-456',
        worktree_path: '/path',
        worktree_name: 'feature-branch',
        status: 'in_progress',
        started_at: '2025-12-01T10:00:00Z',
        completed_at: null,
        failure_reason: null,
        current_stage: 'architect',
        plan: null,
        token_usage: {},
        recent_events: [],
      },
    };

    expect(loaderData.workflow.id).toBe('wf-123');
  });

  it('should create valid ActionResult object', () => {
    const result: ActionResult = {
      success: true,
      action: 'approved',
    };

    expect(result.success).toBe(true);
    expect(result.action).toBe('approved');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- src/types/__tests__/api.test.ts`
Expected: FAIL with module not found or type errors

**Step 3: Implement additional TypeScript types**

```typescript
// dashboard/src/types/api.ts
/**
 * Additional TypeScript types for React Router loaders and actions.
 * Re-exports base types from Plan 08.
 * Keep in sync with amelia/server/models/*.py
 */

// Re-export all types from Plan 08 Task 8
export * from './index';

// React Router loader/action types (NEW in this plan)
export interface WorkflowsLoaderData {
  workflows: WorkflowSummary[];
}

export interface WorkflowDetailLoaderData {
  workflow: WorkflowDetail;
}

export interface ActionResult {
  success: boolean;
  action: 'approved' | 'rejected' | 'cancelled';
  error?: string;
}

// WebSocket message types (updated to use 'data' instead of 'payload')
export type WebSocketMessage =
  | { type: 'event'; data: WorkflowEvent }  // Changed from 'payload' to 'data'
  | { type: 'ping' }
  | { type: 'backfill_complete'; count: number }
  | { type: 'backfill_expired'; message: string };

export type WebSocketClientMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' };
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- src/types/__tests__/api.test.ts`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/types/api.ts && git commit -m "feat(dashboard): extend TypeScript types for React Router loaders and actions

- WorkflowsLoaderData, WorkflowDetailLoaderData, ActionResult
- Re-exports base types from Plan 08
- WebSocket message types with 'data' field (not 'payload')"`

---

## Task 2: Implement API Client Module

**Files:**
- Create: `dashboard/src/api/client.ts`
- Create: `dashboard/src/api/__tests__/client.test.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/api/__tests__/client.test.ts
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

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ workflows: mockWorkflows, total: 1, has_more: false }),
      });

      const result = await api.getWorkflows();

      expect(global.fetch).toHaveBeenCalledWith('http://localhost:8420/api/workflows?status=in_progress,blocked');
      expect(result).toEqual(mockWorkflows);
    });

    it('should handle fetch errors', async () => {
      (global.fetch as any).mockRejectedValueOnce(new Error('Network error'));

      await expect(api.getWorkflows()).rejects.toThrow('Network error');
    });

    it('should handle HTTP errors', async () => {
      (global.fetch as any).mockResolvedValueOnce({
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

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockWorkflow,
      });

      const result = await api.getWorkflow('wf-1');

      expect(global.fetch).toHaveBeenCalledWith('http://localhost:8420/api/workflows/wf-1');
      expect(result.id).toBe('wf-1');
    });
  });

  describe('approveWorkflow', () => {
    it('should POST to approve endpoint', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'in_progress' }),
      });

      await api.approveWorkflow('wf-1');

      expect(global.fetch).toHaveBeenCalledWith('http://localhost:8420/api/workflows/wf-1/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
    });
  });

  describe('rejectWorkflow', () => {
    it('should POST to reject endpoint with feedback', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'failed' }),
      });

      await api.rejectWorkflow('wf-1', 'Plan needs revision');

      expect(global.fetch).toHaveBeenCalledWith('http://localhost:8420/api/workflows/wf-1/reject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback: 'Plan needs revision' }),
      });
    });
  });

  describe('cancelWorkflow', () => {
    it('should POST to cancel endpoint', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'cancelled' }),
      });

      await api.cancelWorkflow('wf-1');

      expect(global.fetch).toHaveBeenCalledWith('http://localhost:8420/api/workflows/wf-1/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- src/api/__tests__/client.test.ts`
Expected: FAIL with module not found

**Step 3: Implement API client**

```typescript
// dashboard/src/api/client.ts
import type {
  WorkflowSummary,
  WorkflowDetailResponse,
  WorkflowListResponse,
  ErrorResponse,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8420/api';

class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: ErrorResponse;
    try {
      errorData = await response.json();
    } catch {
      throw new ApiError(
        `HTTP ${response.status}: ${response.statusText}`,
        'HTTP_ERROR',
        response.status
      );
    }

    throw new ApiError(
      errorData.error,
      errorData.code,
      response.status,
      errorData.details
    );
  }

  return response.json();
}

export const api = {
  /**
   * Get all active workflows (in_progress or blocked).
   */
  async getWorkflows(): Promise<WorkflowSummary[]> {
    const response = await fetch(`${API_BASE_URL}/workflows?status=in_progress,blocked`);
    const data = await handleResponse<WorkflowListResponse>(response);
    return data.workflows;
  },

  /**
   * Get single workflow by ID with full details.
   */
  async getWorkflow(id: string): Promise<WorkflowDetailResponse> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}`);
    return handleResponse<WorkflowDetailResponse>(response);
  },

  /**
   * Approve a blocked workflow's plan.
   */
  async approveWorkflow(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    await handleResponse(response);
  },

  /**
   * Reject a workflow's plan with feedback.
   */
  async rejectWorkflow(id: string, feedback: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback }),
    });
    await handleResponse(response);
  },

  /**
   * Cancel a running workflow.
   */
  async cancelWorkflow(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    await handleResponse(response);
  },
};

export { ApiError };
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- src/api/__tests__/client.test.ts`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/api && git commit -m "feat(dashboard): add REST API client module"`

---

## Task 3: Implement Route Loaders for Data Fetching

**Files:**
- Create: `dashboard/src/loaders/workflows.ts`
- Create: `dashboard/src/loaders/__tests__/workflows.test.ts`
- Create: `dashboard/src/loaders/index.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/loaders/__tests__/workflows.test.ts
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
      } as any);

      expect(api.getWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ workflow: mockWorkflow });
    });

    it('should throw 400 if ID is missing', async () => {
      try {
        await workflowDetailLoader({
          params: {},
          request: new Request('http://localhost/workflows'),
        } as any);
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
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- src/loaders/__tests__/workflows.test.ts`
Expected: FAIL with module not found

**Step 3: Add getWorkflowHistory to API client**

```typescript
// dashboard/src/api/client.ts (add to existing api object)
export const api = {
  // ... existing methods ...

  /**
   * Get workflow history (completed, failed, cancelled).
   */
  async getWorkflowHistory(): Promise<WorkflowSummary[]> {
    const response = await fetch(`${API_BASE_URL}/workflows?status=completed,failed,cancelled`);
    const data = await handleResponse<WorkflowListResponse>(response);
    return data.workflows;
  },
};
```

**Step 4: Implement route loaders**

```typescript
// dashboard/src/loaders/workflows.ts
import { api } from '@/api/client';
import type { LoaderFunctionArgs } from 'react-router-dom';

/**
 * Loader for active workflows page.
 * Fetches in_progress and blocked workflows.
 */
export async function workflowsLoader() {
  const workflows = await api.getWorkflows();
  return { workflows };
}

/**
 * Loader for workflow detail page.
 * Fetches full workflow details including events and token usage.
 */
export async function workflowDetailLoader({ params }: LoaderFunctionArgs) {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  const workflow = await api.getWorkflow(params.id);
  return { workflow };
}

/**
 * Loader for workflow history page.
 * Fetches completed, failed, and cancelled workflows.
 */
export async function historyLoader() {
  const workflows = await api.getWorkflowHistory();
  return { workflows };
}
```

```typescript
// dashboard/src/loaders/index.ts
export { workflowsLoader, workflowDetailLoader, historyLoader } from './workflows';
```

**Step 5: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- src/loaders/__tests__/workflows.test.ts`
Expected: PASS

**Step 6: Commit**

Run: `git add dashboard/src/loaders dashboard/src/api && git commit -m "feat(dashboard): add React Router loaders for workflow data"`

---

## Task 4: Implement Zustand Workflow Store (Real-time & UI State Only)

**Files:**
- Create: `dashboard/src/store/workflowStore.ts`
- Create: `dashboard/src/store/__tests__/workflowStore.test.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/store/__tests__/workflowStore.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkflowStore } from '../workflowStore';
import type { WorkflowSummary, WorkflowEvent } from '../../types';

// Mock sessionStorage
const sessionStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'sessionStorage', { value: sessionStorageMock });

describe('workflowStore', () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: new Set(),
    });
    sessionStorageMock.clear();
  });

  describe('selectWorkflow', () => {
    it('should update selectedWorkflowId', () => {
      useWorkflowStore.getState().selectWorkflow('wf-123');

      expect(useWorkflowStore.getState().selectedWorkflowId).toBe('wf-123');
    });

    it('should allow null selection', () => {
      useWorkflowStore.setState({ selectedWorkflowId: 'wf-1' });
      useWorkflowStore.getState().selectWorkflow(null);

      expect(useWorkflowStore.getState().selectedWorkflowId).toBeNull();
    });
  });

  describe('addEvent', () => {
    it('should add event to workflow event list', () => {
      const event: WorkflowEvent = {
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        timestamp: '2025-12-01T10:00:00Z',
        agent: 'architect',
        event_type: 'workflow_started',
        message: 'Workflow started',
        data: null,
        correlation_id: null,
      };

      useWorkflowStore.getState().addEvent(event);

      const state = useWorkflowStore.getState();
      expect(state.eventsByWorkflow['wf-1']).toHaveLength(1);
      expect(state.eventsByWorkflow['wf-1'][0]).toEqual(event);
      expect(state.lastEventId).toBe('evt-1');
    });

    it('should append to existing events', () => {
      const event1: WorkflowEvent = {
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        timestamp: '2025-12-01T10:00:00Z',
        agent: 'architect',
        event_type: 'workflow_started',
        message: 'Started',
        data: null,
        correlation_id: null,
      };

      const event2: WorkflowEvent = {
        id: 'evt-2',
        workflow_id: 'wf-1',
        sequence: 2,
        timestamp: '2025-12-01T10:01:00Z',
        agent: 'architect',
        event_type: 'stage_started',
        message: 'Planning',
        data: { stage: 'architect' },
        correlation_id: null,
      };

      useWorkflowStore.getState().addEvent(event1);
      useWorkflowStore.getState().addEvent(event2);

      const events = useWorkflowStore.getState().eventsByWorkflow['wf-1'];
      expect(events).toHaveLength(2);
      expect(events[0].id).toBe('evt-1');
      expect(events[1].id).toBe('evt-2');
    });

    it('should trim events when exceeding MAX_EVENTS_PER_WORKFLOW', () => {
      const MAX_EVENTS = 500;

      // Add 501 events
      for (let i = 1; i <= MAX_EVENTS + 1; i++) {
        const event: WorkflowEvent = {
          id: `evt-${i}`,
          workflow_id: 'wf-1',
          sequence: i,
          timestamp: '2025-12-01T10:00:00Z',
          agent: 'architect',
          event_type: 'stage_started',
          message: `Event ${i}`,
          data: null,
          correlation_id: null,
        };
        useWorkflowStore.getState().addEvent(event);
      }

      const events = useWorkflowStore.getState().eventsByWorkflow['wf-1'];
      expect(events).toHaveLength(MAX_EVENTS);
      // Should keep most recent (evt-2 to evt-501, dropping evt-1)
      expect(events[0].id).toBe('evt-2');
      expect(events[MAX_EVENTS - 1].id).toBe(`evt-${MAX_EVENTS + 1}`);
    });
  });

  describe('updateWorkflow', () => {
    it('should update workflow fields', () => {
      useWorkflowStore.setState({
        workflows: {
          'wf-1': {
            id: 'wf-1',
            issue_id: 'ISSUE-1',
            worktree_name: 'main',
            status: 'in_progress',
            started_at: '2025-12-01T10:00:00Z',
            current_stage: 'architect',
          },
        },
      });

      useWorkflowStore.getState().updateWorkflow('wf-1', { status: 'blocked' });

      expect(useWorkflowStore.getState().workflows['wf-1'].status).toBe('blocked');
    });

    it('should preserve other fields when updating', () => {
      useWorkflowStore.setState({
        workflows: {
          'wf-1': {
            id: 'wf-1',
            issue_id: 'ISSUE-1',
            worktree_name: 'main',
            status: 'in_progress',
            started_at: '2025-12-01T10:00:00Z',
            current_stage: 'architect',
          },
        },
      });

      useWorkflowStore.getState().updateWorkflow('wf-1', { current_stage: 'developer' });

      const workflow = useWorkflowStore.getState().workflows['wf-1'];
      expect(workflow.current_stage).toBe('developer');
      expect(workflow.status).toBe('in_progress');
      expect(workflow.issue_id).toBe('ISSUE-1');
    });

    it('should do nothing if workflow not found', () => {
      useWorkflowStore.setState({ workflows: {} });

      useWorkflowStore.getState().updateWorkflow('wf-999', { status: 'blocked' });

      expect(useWorkflowStore.getState().workflows).toEqual({});
    });
  });

  describe('connection state', () => {
    it('should update connection status', () => {
      useWorkflowStore.getState().setConnected(true);

      expect(useWorkflowStore.getState().isConnected).toBe(true);
      expect(useWorkflowStore.getState().error).toBeNull();
    });

    it('should set error when disconnected', () => {
      useWorkflowStore.getState().setConnected(false);

      expect(useWorkflowStore.getState().isConnected).toBe(false);
      expect(useWorkflowStore.getState().error).toBe('Connection lost');
    });
  });

  describe('pending actions', () => {
    it('should add pending action', () => {
      useWorkflowStore.getState().addPendingAction('approve-wf-1');

      expect(useWorkflowStore.getState().pendingActions.has('approve-wf-1')).toBe(true);
    });

    it('should not duplicate pending action', () => {
      useWorkflowStore.getState().addPendingAction('approve-wf-1');
      useWorkflowStore.getState().addPendingAction('approve-wf-1');

      expect(useWorkflowStore.getState().pendingActions.size).toBe(1);
    });

    it('should remove pending action', () => {
      useWorkflowStore.getState().addPendingAction('approve-wf-1');
      useWorkflowStore.getState().removePendingAction('approve-wf-1');

      expect(useWorkflowStore.getState().pendingActions.size).toBe(0);
    });
  });

  describe('persistence', () => {
    it('should persist selectedWorkflowId to sessionStorage', () => {
      useWorkflowStore.getState().selectWorkflow('wf-123');

      const stored = sessionStorageMock.getItem('amelia-workflow-state');
      expect(stored).not.toBeNull();
      const parsed = JSON.parse(stored!);
      expect(parsed.state.selectedWorkflowId).toBe('wf-123');
    });

    it('should persist lastEventId to sessionStorage', () => {
      useWorkflowStore.getState().addEvent({
        id: 'evt-999',
        workflow_id: 'wf-1',
        sequence: 1,
        timestamp: '2025-12-01T10:00:00Z',
        agent: 'architect',
        event_type: 'workflow_started',
        message: 'Started',
        data: null,
        correlation_id: null,
      });

      const stored = sessionStorageMock.getItem('amelia-workflow-state');
      const parsed = JSON.parse(stored!);
      expect(parsed.state.lastEventId).toBe('evt-999');
    });

    it('should NOT persist events to sessionStorage', () => {
      useWorkflowStore.getState().addEvent({
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        timestamp: '2025-12-01T10:00:00Z',
        agent: 'architect',
        event_type: 'workflow_started',
        message: 'Started',
        data: null,
        correlation_id: null,
      });

      const stored = sessionStorageMock.getItem('amelia-workflow-state');
      const parsed = JSON.parse(stored!);
      expect(parsed.state.eventsByWorkflow).toBeUndefined();
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- src/store/__tests__/workflowStore.test.ts`
Expected: FAIL with module not found

**Step 3: Install Zustand**

Run: `cd dashboard && pnpm add zustand`

**Step 4: Implement Zustand store**

```typescript
// dashboard/src/store/workflowStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { WorkflowEvent } from '../types';

const MAX_EVENTS_PER_WORKFLOW = 500;

/**
 * Zustand store for real-time WebSocket events and UI state.
 *
 * Note: Workflow data comes from React Router loaders, not this store.
 * This store only manages:
 * - Real-time events from WebSocket
 * - UI state (selected workflow)
 * - Connection state
 * - Pending actions for optimistic UI
 */
interface WorkflowState {
  // UI State
  selectedWorkflowId: string | null;

  // Real-time events from WebSocket (grouped by workflow)
  eventsByWorkflow: Record<string, WorkflowEvent[]>;

  // Last seen event ID for reconnection backfill
  lastEventId: string | null;

  // Connection state
  isConnected: boolean;
  connectionError: string | null;

  // Pending actions for optimistic UI tracking
  pendingActions: Set<string>; // Action IDs currently in flight

  // Actions
  selectWorkflow: (id: string | null) => void;
  addEvent: (event: WorkflowEvent) => void;
  setConnected: (connected: boolean, error?: string) => void;
  addPendingAction: (actionId: string) => void;
  removePendingAction: (actionId: string) => void;
}

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set) => ({
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: new Set(),

      selectWorkflow: (id) => set({ selectedWorkflowId: id }),

      addEvent: (event) =>
        set((state) => {
          const existing = state.eventsByWorkflow[event.workflow_id] ?? [];
          const updated = [...existing, event];

          // Trim oldest events if exceeding limit (keep most recent)
          const trimmed =
            updated.length > MAX_EVENTS_PER_WORKFLOW
              ? updated.slice(-MAX_EVENTS_PER_WORKFLOW)
              : updated;

          return {
            eventsByWorkflow: {
              ...state.eventsByWorkflow,
              [event.workflow_id]: trimmed,
            },
            lastEventId: event.id,
          };
        }),

      setConnected: (connected, error) =>
        set({
          isConnected: connected,
          connectionError: error ?? null,
        }),

      addPendingAction: (actionId) =>
        set((state) => {
          const newSet = new Set(state.pendingActions);
          newSet.add(actionId);
          return { pendingActions: newSet };
        }),

      removePendingAction: (actionId) =>
        set((state) => {
          const newSet = new Set(state.pendingActions);
          newSet.delete(actionId);
          return { pendingActions: newSet };
        }),
    }),
    {
      name: 'amelia-workflow-state',
      storage: {
        getItem: (name) => {
          const value = sessionStorage.getItem(name);
          return value ? JSON.parse(value) : null;
        },
        setItem: (name, value) => {
          sessionStorage.setItem(name, JSON.stringify(value));
        },
        removeItem: (name) => {
          sessionStorage.removeItem(name);
        },
      },
      // Only persist UI state - events are ephemeral
      partialize: (state) => ({
        selectedWorkflowId: state.selectedWorkflowId,
        lastEventId: state.lastEventId,
      }),
    }
  )
);
```

**Step 5: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- src/store/__tests__/workflowStore.test.ts`
Expected: PASS

**Step 6: Commit**

Run: `git add dashboard/src/store dashboard/package.json dashboard/package-lock.json && git commit -m "feat(dashboard): add Zustand store for real-time events and UI state"`

---

## Task 5: Implement WebSocket Connection Hook

**Files:**
- Create: `dashboard/src/hooks/useWebSocket.ts`
- Create: `dashboard/src/hooks/__tests__/useWebSocket.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/hooks/__tests__/useWebSocket.test.tsx
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useWebSocket } from '../useWebSocket';
import { useWorkflowStore } from '../../store/workflowStore';

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  readyState: number = 0; // CONNECTING

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    // Simulate connection after a tick
    setTimeout(() => {
      this.readyState = 1; // OPEN
      this.onopen?.(new Event('open'));
    }, 0);
  }

  send(data: string) {
    // Mock send
  }

  close() {
    this.readyState = 3; // CLOSED
    this.onclose?.(new CloseEvent('close'));
  }

  static reset() {
    MockWebSocket.instances = [];
  }
}

global.WebSocket = MockWebSocket as any;

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.reset();
    useWorkflowStore.setState({
      workflows: {},
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isLoading: false,
      error: null,
      isConnected: false,
      lastSyncAt: null,
      pendingActions: [],
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should connect to WebSocket on mount', async () => {
    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
      expect(MockWebSocket.instances[0].url).toContain('ws://localhost:8420/ws/events');
    });
  });

  it('should set isConnected when connection opens', async () => {
    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(useWorkflowStore.getState().isConnected).toBe(true);
    });
  });

  it('should subscribe to all workflows on connect', async () => {
    const sendSpy = vi.spyOn(MockWebSocket.prototype, 'send');

    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(sendSpy).toHaveBeenCalledWith(JSON.stringify({ type: 'subscribe_all' }));
    });
  });

  it('should handle incoming event messages', async () => {
    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    const ws = MockWebSocket.instances[0];
    const event = {
      id: 'evt-1',
      workflow_id: 'wf-1',
      sequence: 1,
      timestamp: '2025-12-01T10:00:00Z',
      agent: 'architect',
      event_type: 'workflow_started',
      message: 'Started',
      data: null,
      correlation_id: null,
    };

    ws.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({ type: 'event', data: event }),
      })
    );

    await waitFor(() => {
      const state = useWorkflowStore.getState();
      expect(state.eventsByWorkflow['wf-1']).toHaveLength(1);
      expect(state.eventsByWorkflow['wf-1'][0]).toEqual(event);
    });
  });

  it('should respond to ping with pong', async () => {
    const sendSpy = vi.spyOn(MockWebSocket.prototype, 'send');

    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    const ws = MockWebSocket.instances[0];
    ws.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({ type: 'ping' }),
      })
    );

    expect(sendSpy).toHaveBeenCalledWith(JSON.stringify({ type: 'pong' }));
  });

  it('should reconnect with exponential backoff on disconnect', async () => {
    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    // Simulate disconnect
    MockWebSocket.instances[0].close();

    // First reconnect attempt after 1s
    vi.advanceTimersByTime(1000);
    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(2);
    });

    // Simulate another disconnect
    MockWebSocket.instances[1].close();

    // Second reconnect attempt after 2s
    vi.advanceTimersByTime(2000);
    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(3);
    });
  });

  it('should include since parameter when reconnecting with lastEventId', async () => {
    useWorkflowStore.setState({ lastEventId: 'evt-999' });

    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    // Simulate disconnect
    MockWebSocket.instances[0].close();

    // Reconnect
    vi.advanceTimersByTime(1000);
    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(2);
      expect(MockWebSocket.instances[1].url).toContain('since=evt-999');
    });
  });

  it('should detect sequence gaps and log warning', async () => {
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    const ws = MockWebSocket.instances[0];

    // Send event with sequence 1
    ws.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({
          type: 'event',
          data: {
            id: 'evt-1',
            workflow_id: 'wf-1',
            sequence: 1,
            timestamp: '2025-12-01T10:00:00Z',
            agent: 'architect',
            event_type: 'workflow_started',
            message: 'Started',
            data: null,
            correlation_id: null,
          },
        }),
      })
    );

    // Send event with sequence 5 (gap!)
    ws.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({
          type: 'event',
          data: {
            id: 'evt-5',
            workflow_id: 'wf-1',
            sequence: 5,
            timestamp: '2025-12-01T10:05:00Z',
            agent: 'architect',
            event_type: 'stage_started',
            message: 'Planning',
            data: null,
            correlation_id: null,
          },
        }),
      })
    );

    expect(consoleWarnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Sequence gap detected')
    );
  });

  it('should handle backfill_expired by clearing lastEventId', async () => {
    useWorkflowStore.setState({ lastEventId: 'evt-old' });

    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    const ws = MockWebSocket.instances[0];
    ws.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({
          type: 'backfill_expired',
          message: 'Requested event no longer exists. Full refresh required.',
        }),
      })
    );

    await waitFor(() => {
      expect(useWorkflowStore.getState().lastEventId).toBeNull();
    });
  });

  it('should cap reconnect delay at 30 seconds', async () => {
    renderHook(() => useWebSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    // Simulate multiple disconnects
    for (let i = 0; i < 10; i++) {
      MockWebSocket.instances[MockWebSocket.instances.length - 1].close();
      const delay = Math.min(1000 * Math.pow(2, i), 30000);
      vi.advanceTimersByTime(delay);
      await waitFor(() => {
        expect(MockWebSocket.instances).toHaveLength(i + 2);
      });
    }

    // After 10 attempts, delay should be capped at 30s
    const lastAttemptIndex = MockWebSocket.instances.length - 1;
    MockWebSocket.instances[lastAttemptIndex].close();

    // Should NOT reconnect before 30s
    vi.advanceTimersByTime(29000);
    expect(MockWebSocket.instances).toHaveLength(11);

    // Should reconnect after 30s
    vi.advanceTimersByTime(1000);
    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(12);
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- src/hooks/__tests__/useWebSocket.test.tsx`
Expected: FAIL with module not found

**Step 3: Implement WebSocket hook**

```typescript
// dashboard/src/hooks/useWebSocket.ts
import { useEffect, useRef } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import type { WebSocketMessage, WorkflowEvent } from '../types';

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8420/ws/events';
const MAX_RECONNECT_DELAY = 30000; // 30 seconds
const INITIAL_RECONNECT_DELAY = 1000; // 1 second

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const lastSequenceRef = useRef(new Map<string, number>());

  const { addEvent, setConnected, lastEventId, setLastEventId } = useWorkflowStore();

  const connect = () => {
    // Build WebSocket URL with optional since parameter
    const url = lastEventId ? `${WS_BASE_URL}?since=${lastEventId}` : WS_BASE_URL;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
      reconnectAttemptRef.current = 0; // Reset reconnect counter

      // Subscribe to all workflows
      ws.send(JSON.stringify({ type: 'subscribe_all' }));
    };

    ws.onmessage = (event) => {
      const message: WebSocketMessage = JSON.parse(event.data);

      switch (message.type) {
        case 'event':
          handleEvent(message.data);
          break;

        case 'ping':
          // Respond to heartbeat
          ws.send(JSON.stringify({ type: 'pong' }));
          break;

        case 'backfill_complete':
          console.log(`Backfill complete: ${message.count} events`);
          break;

        case 'backfill_expired':
          console.warn('Backfill expired, clearing lastEventId for full refresh');
          setLastEventId(''); // Clear so next reconnect doesn't use since
          break;
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);
      scheduleReconnect();
    };
  };

  const handleEvent = (event: WorkflowEvent) => {
    // Check for sequence gaps
    const lastSeq = lastSequenceRef.current.get(event.workflow_id) ?? 0;

    if (event.sequence > lastSeq + 1) {
      console.warn(
        `Sequence gap detected for ${event.workflow_id}: ` +
          `expected ${lastSeq + 1}, got ${event.sequence}. ` +
          `Some events may have been missed.`
      );
      // Note: In a full implementation, we might trigger a state refresh here
    }

    lastSequenceRef.current.set(event.workflow_id, event.sequence);
    addEvent(event);

    // Dispatch custom event for pages to listen to for revalidation hints
    window.dispatchEvent(new CustomEvent('workflow-event', { detail: event }));
  };

  const scheduleReconnect = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (capped)
    const delay = Math.min(
      INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttemptRef.current),
      MAX_RECONNECT_DELAY
    );

    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current + 1})`);

    reconnectTimeoutRef.current = window.setTimeout(() => {
      reconnectAttemptRef.current++;
      connect();
    }, delay);
  };

  const disconnect = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Connect once on mount

  return {
    reconnect: () => {
      disconnect();
      connect();
    },
  };
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- src/hooks/__tests__/useWebSocket.test.tsx`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/hooks && git commit -m "feat(dashboard): add WebSocket hook with reconnection and backfill"`

---

## Task 6: Implement useWorkflows Hook (Hybrid Loader + Real-time)

**Files:**
- Create: `dashboard/src/hooks/useWorkflows.ts`
- Create: `dashboard/src/hooks/__tests__/useWorkflows.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/hooks/__tests__/useWorkflows.test.tsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useWorkflows } from '../useWorkflows';
import { useWorkflowStore } from '../../store/workflowStore';
import { useLoaderData, useRevalidator } from 'react-router-dom';

vi.mock('react-router-dom', () => ({
  useLoaderData: vi.fn(),
  useRevalidator: vi.fn(),
}));

describe('useWorkflows', () => {
  const mockRevalidate = vi.fn();
  const mockRevalidator = {
    state: 'idle' as const,
    revalidate: mockRevalidate,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkflowStore.setState({
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: new Set(),
    });
    vi.mocked(useRevalidator).mockReturnValue(mockRevalidator);
  });

  it('should return workflows from loader data', () => {
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

    vi.mocked(useLoaderData).mockReturnValue({ workflows: mockWorkflows });

    const { result } = renderHook(() => useWorkflows());

    expect(result.current.workflows).toEqual(mockWorkflows);
    expect(result.current.isConnected).toBe(false);
  });

  it('should return connection state from Zustand store', () => {
    useWorkflowStore.setState({ isConnected: true });
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });

    const { result } = renderHook(() => useWorkflows());

    expect(result.current.isConnected).toBe(true);
  });

  it('should revalidate when status-changing events are received', async () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });

    const { rerender } = renderHook(() => useWorkflows());

    // Add a status-changing event
    useWorkflowStore.setState({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            sequence: 1,
            timestamp: new Date().toISOString(),
            agent: 'architect',
            event_type: 'workflow_completed',
            message: 'Completed',
            data: null,
            correlation_id: null,
          },
        ],
      },
    });

    rerender();

    await waitFor(() => {
      expect(mockRevalidate).toHaveBeenCalled();
    });
  });

  it('should not revalidate for non-status-changing events', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });

    renderHook(() => useWorkflows());

    // Add a non-status-changing event
    useWorkflowStore.setState({
      eventsByWorkflow: {
        'wf-1': [
          {
            id: 'evt-1',
            workflow_id: 'wf-1',
            sequence: 1,
            timestamp: new Date().toISOString(),
            agent: 'architect',
            event_type: 'file_created',
            message: 'File created',
            data: null,
            correlation_id: null,
          },
        ],
      },
    });

    expect(mockRevalidate).not.toHaveBeenCalled();
  });

  it('should provide revalidation state', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });
    vi.mocked(useRevalidator).mockReturnValue({
      state: 'loading',
      revalidate: mockRevalidate,
    });

    const { result } = renderHook(() => useWorkflows());

    expect(result.current.isRevalidating).toBe(true);
  });

  it('should provide manual revalidate function', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });

    const { result } = renderHook(() => useWorkflows());

    result.current.revalidate();

    expect(mockRevalidate).toHaveBeenCalled();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- src/hooks/__tests__/useWorkflows.test.tsx`
Expected: FAIL with module not found

**Step 3: Implement useWorkflows hook**

```typescript
// dashboard/src/hooks/useWorkflows.ts
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { useWorkflowStore } from '../store/workflowStore';
import { useEffect } from 'react';
import type { WorkflowsLoaderData } from '../types';

/**
 * Hook that combines loader data with real-time updates.
 *
 * Data Flow:
 * - Initial data comes from route loader (via useLoaderData)
 * - Real-time updates come from WebSocket via Zustand store
 * - Revalidation is triggered for status-changing events
 *
 * This is a hybrid approach: loaders for initial data, Zustand for real-time state.
 */
export function useWorkflows() {
  const { workflows } = useLoaderData() as WorkflowsLoaderData;
  const { eventsByWorkflow, isConnected } = useWorkflowStore();
  const revalidator = useRevalidator();

  // Revalidate when we receive status-changing events
  useEffect(() => {
    const statusEvents = ['workflow_completed', 'workflow_failed', 'workflow_started'];
    const recentEvents = Object.values(eventsByWorkflow).flat();
    const hasStatusChange = recentEvents.some(
      (e) =>
        statusEvents.includes(e.event_type) &&
        Date.now() - new Date(e.timestamp).getTime() < 5000 // Within last 5 seconds
    );

    if (hasStatusChange && revalidator.state === 'idle') {
      revalidator.revalidate();
    }
  }, [eventsByWorkflow, revalidator]);

  return {
    workflows,
    isConnected,
    isRevalidating: revalidator.state === 'loading',
    revalidate: () => revalidator.revalidate(),
  };
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- src/hooks/__tests__/useWorkflows.test.tsx`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/hooks && git commit -m "feat(dashboard): add useWorkflows hook combining loaders with real-time updates"`

---

## Task 7: Implement Route Actions for Mutations

**Files:**
- Create: `dashboard/src/actions/workflows.ts`
- Create: `dashboard/src/actions/__tests__/workflows.test.ts`
- Create: `dashboard/src/actions/index.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/actions/__tests__/workflows.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { approveAction, rejectAction, cancelAction } from '../workflows';
import { api } from '../../api/client';

vi.mock('../../api/client');

describe('Workflow Actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('approveAction', () => {
    it('should approve workflow by ID from params', async () => {
      vi.mocked(api.approveWorkflow).mockResolvedValueOnce(undefined);

      const result = await approveAction({
        params: { id: 'wf-1' },
        request: new Request('http://localhost/workflows/wf-1/approve', { method: 'POST' }),
      } as any);

      expect(api.approveWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ success: true, action: 'approved' });
    });

    it('should throw 400 if ID is missing', async () => {
      try {
        await approveAction({
          params: {},
          request: new Request('http://localhost/workflows/approve', { method: 'POST' }),
        } as any);
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(Response);
        expect((error as Response).status).toBe(400);
      }
    });

    it('should propagate API errors', async () => {
      vi.mocked(api.approveWorkflow).mockRejectedValueOnce(new Error('Server error'));

      await expect(
        approveAction({
          params: { id: 'wf-1' },
          request: new Request('http://localhost/workflows/wf-1/approve', { method: 'POST' }),
        } as any)
      ).rejects.toThrow('Server error');
    });
  });

  describe('rejectAction', () => {
    it('should reject workflow with feedback from form data', async () => {
      vi.mocked(api.rejectWorkflow).mockResolvedValueOnce(undefined);

      const formData = new FormData();
      formData.append('feedback', 'Plan needs revision');

      const request = new Request('http://localhost/workflows/wf-1/reject', {
        method: 'POST',
        body: formData,
      });

      const result = await rejectAction({
        params: { id: 'wf-1' },
        request,
      } as any);

      expect(api.rejectWorkflow).toHaveBeenCalledWith('wf-1', 'Plan needs revision');
      expect(result).toEqual({ success: true, action: 'rejected' });
    });

    it('should throw 400 if ID is missing', async () => {
      const formData = new FormData();
      formData.append('feedback', 'Test');

      const request = new Request('http://localhost/workflows/reject', {
        method: 'POST',
        body: formData,
      });

      try {
        await rejectAction({
          params: {},
          request,
        } as any);
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(Response);
        expect((error as Response).status).toBe(400);
      }
    });
  });

  describe('cancelAction', () => {
    it('should cancel workflow by ID from params', async () => {
      vi.mocked(api.cancelWorkflow).mockResolvedValueOnce(undefined);

      const result = await cancelAction({
        params: { id: 'wf-1' },
        request: new Request('http://localhost/workflows/wf-1/cancel', { method: 'POST' }),
      } as any);

      expect(api.cancelWorkflow).toHaveBeenCalledWith('wf-1');
      expect(result).toEqual({ success: true, action: 'cancelled' });
    });

    it('should throw 400 if ID is missing', async () => {
      try {
        await cancelAction({
          params: {},
          request: new Request('http://localhost/workflows/cancel', { method: 'POST' }),
        } as any);
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(Response);
        expect((error as Response).status).toBe(400);
      }
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- src/actions/__tests__/workflows.test.ts`
Expected: FAIL with module not found

**Step 3: Implement route actions**

```typescript
// dashboard/src/actions/workflows.ts
import { api } from '@/api/client';
import type { ActionFunctionArgs } from 'react-router-dom';
import type { ActionResult } from '@/types';

/**
 * Action for approving a workflow's plan.
 * Triggered by POST to /workflows/:id/approve
 */
export async function approveAction({ params }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  await api.approveWorkflow(params.id);
  return { success: true, action: 'approved' };
}

/**
 * Action for rejecting a workflow's plan with feedback.
 * Triggered by POST to /workflows/:id/reject
 */
export async function rejectAction({ params, request }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  const formData = await request.formData();
  const feedback = formData.get('feedback') as string;

  await api.rejectWorkflow(params.id, feedback);
  return { success: true, action: 'rejected' };
}

/**
 * Action for cancelling a running workflow.
 * Triggered by POST to /workflows/:id/cancel
 */
export async function cancelAction({ params }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    throw new Response('Workflow ID required', { status: 400 });
  }

  await api.cancelWorkflow(params.id);
  return { success: true, action: 'cancelled' };
}
```

```typescript
// dashboard/src/actions/index.ts
export { approveAction, rejectAction, cancelAction } from './workflows';
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- src/actions/__tests__/workflows.test.ts`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/actions && git commit -m "feat(dashboard): add React Router actions for workflow mutations"`

---

## Task 8: Implement useWorkflowActions Hook with useFetcher

**Files:**
- Create: `dashboard/src/hooks/useWorkflowActions.ts`
- Create: `dashboard/src/hooks/__tests__/useWorkflowActions.test.tsx`
- Create: `dashboard/src/components/Toast.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/hooks/__tests__/useWorkflowActions.test.tsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWorkflowActions } from '../useWorkflowActions';
import { useFetcher } from 'react-router-dom';

vi.mock('react-router-dom', () => ({
  useFetcher: vi.fn(),
}));

describe('useWorkflowActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkflowStore.setState({
      workflows: {
        'wf-1': {
          id: 'wf-1',
          issue_id: 'ISSUE-1',
          worktree_name: 'main',
          status: 'blocked',
          started_at: '2025-12-01T10:00:00Z',
          current_stage: 'architect',
        },
      },
      selectedWorkflowId: 'wf-1',
      eventsByWorkflow: {},
      lastEventId: null,
      isLoading: false,
      error: null,
      isConnected: false,
      lastSyncAt: null,
      pendingActions: [],
    });
  });

  describe('approveWorkflow', () => {
    it('should optimistically update status to in_progress', async () => {
      vi.mocked(api.approveWorkflow).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useWorkflowActions());

      result.current.approveWorkflow('wf-1');

      // Should update immediately (optimistic)
      await waitFor(() => {
        expect(useWorkflowStore.getState().workflows['wf-1'].status).toBe('in_progress');
      });
    });

    it('should add pending action during request', async () => {
      vi.mocked(api.approveWorkflow).mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            setTimeout(resolve, 100);
          })
      );

      const { result } = renderHook(() => useWorkflowActions());

      result.current.approveWorkflow('wf-1');

      await waitFor(() => {
        expect(useWorkflowStore.getState().pendingActions).toContain('approve-wf-1');
      });

      await waitFor(() => {
        expect(useWorkflowStore.getState().pendingActions).not.toContain('approve-wf-1');
      });
    });

    it('should rollback on API error', async () => {
      vi.mocked(api.approveWorkflow).mockRejectedValueOnce(new Error('Server error'));

      const { result } = renderHook(() => useWorkflowActions());

      await result.current.approveWorkflow('wf-1');

      // Should rollback to original status
      await waitFor(() => {
        expect(useWorkflowStore.getState().workflows['wf-1'].status).toBe('blocked');
      });
    });

    it('should show success toast on success', async () => {
      vi.mocked(api.approveWorkflow).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useWorkflowActions());

      await result.current.approveWorkflow('wf-1');

      await waitFor(() => {
        expect(Toast.success).toHaveBeenCalledWith('Plan approved');
      });
    });

    it('should show error toast on failure', async () => {
      vi.mocked(api.approveWorkflow).mockRejectedValueOnce(new Error('Server error'));

      const { result } = renderHook(() => useWorkflowActions());

      await result.current.approveWorkflow('wf-1');

      await waitFor(() => {
        expect(Toast.error).toHaveBeenCalledWith('Approval failed: Server error');
      });
    });
  });

  describe('rejectWorkflow', () => {
    it('should optimistically update status to failed', async () => {
      vi.mocked(api.rejectWorkflow).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useWorkflowActions());

      result.current.rejectWorkflow('wf-1', 'Needs revision');

      await waitFor(() => {
        expect(useWorkflowStore.getState().workflows['wf-1'].status).toBe('failed');
      });
    });

    it('should rollback on API error', async () => {
      vi.mocked(api.rejectWorkflow).mockRejectedValueOnce(new Error('Server error'));

      const { result } = renderHook(() => useWorkflowActions());

      await result.current.rejectWorkflow('wf-1', 'Needs revision');

      await waitFor(() => {
        expect(useWorkflowStore.getState().workflows['wf-1'].status).toBe('blocked');
      });
    });
  });

  describe('cancelWorkflow', () => {
    it('should optimistically update status to cancelled', async () => {
      useWorkflowStore.setState({
        workflows: {
          'wf-1': {
            id: 'wf-1',
            issue_id: 'ISSUE-1',
            worktree_name: 'main',
            status: 'in_progress',
            started_at: '2025-12-01T10:00:00Z',
            current_stage: 'developer',
          },
        },
        selectedWorkflowId: 'wf-1',
        eventsByWorkflow: {},
        lastEventId: null,
        isLoading: false,
        error: null,
        isConnected: false,
        lastSyncAt: null,
        pendingActions: [],
      });

      vi.mocked(api.cancelWorkflow).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useWorkflowActions());

      result.current.cancelWorkflow('wf-1');

      await waitFor(() => {
        expect(useWorkflowStore.getState().workflows['wf-1'].status).toBe('cancelled');
      });
    });

    it('should rollback on API error', async () => {
      useWorkflowStore.setState({
        workflows: {
          'wf-1': {
            id: 'wf-1',
            issue_id: 'ISSUE-1',
            worktree_name: 'main',
            status: 'in_progress',
            started_at: '2025-12-01T10:00:00Z',
            current_stage: 'developer',
          },
        },
        selectedWorkflowId: 'wf-1',
        eventsByWorkflow: {},
        lastEventId: null,
        isLoading: false,
        error: null,
        isConnected: false,
        lastSyncAt: null,
        pendingActions: [],
      });

      vi.mocked(api.cancelWorkflow).mockRejectedValueOnce(new Error('Server error'));

      const { result } = renderHook(() => useWorkflowActions());

      await result.current.cancelWorkflow('wf-1');

      await waitFor(() => {
        expect(useWorkflowStore.getState().workflows['wf-1'].status).toBe('in_progress');
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
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- src/hooks/__tests__/useWorkflowActions.test.tsx`
Expected: FAIL with module not found

**Step 3: Implement Toast component**

```typescript
// dashboard/src/components/Toast.tsx
/**
 * Simple toast notification utilities.
 * In a real implementation, this would integrate with a toast library like react-hot-toast.
 * For now, we use console logging and could add a toast UI component later.
 */

export function success(message: string): void {
  console.log(`✓ ${message}`);
  // TODO: Integrate with toast UI library
}

export function error(message: string): void {
  console.error(`✗ ${message}`);
  // TODO: Integrate with toast UI library
}

export function info(message: string): void {
  console.info(`ℹ ${message}`);
  // TODO: Integrate with toast UI library
}
```

**Step 4: Implement useWorkflowActions hook**

```typescript
// dashboard/src/hooks/useWorkflowActions.ts
import { useCallback } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import { api } from '../api/client';
import * as toast from '../components/Toast';
import type { WorkflowStatus } from '../types';

interface UseWorkflowActionsResult {
  approveWorkflow: (workflowId: string) => Promise<void>;
  rejectWorkflow: (workflowId: string, feedback: string) => Promise<void>;
  cancelWorkflow: (workflowId: string) => Promise<void>;
  isActionPending: (workflowId: string) => boolean;
}

export function useWorkflowActions(): UseWorkflowActionsResult {
  const { updateWorkflow, addPendingAction, removePendingAction, pendingActions, workflows } =
    useWorkflowStore();

  const approveWorkflow = useCallback(
    async (workflowId: string) => {
      const actionId = `approve-${workflowId}`;

      // Capture previous state for rollback
      const workflow = workflows[workflowId];
      const previousStatus = workflow?.status;

      if (!previousStatus) {
        toast.error('Workflow not found');
        return;
      }

      // Optimistic update
      updateWorkflow(workflowId, { status: 'in_progress' });
      addPendingAction(actionId);

      try {
        await api.approveWorkflow(workflowId);
        toast.success('Plan approved');
      } catch (error) {
        // Rollback on failure
        updateWorkflow(workflowId, { status: previousStatus });
        toast.error(`Approval failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      } finally {
        removePendingAction(actionId);
      }
    },
    [updateWorkflow, addPendingAction, removePendingAction, workflows]
  );

  const rejectWorkflow = useCallback(
    async (workflowId: string, feedback: string) => {
      const actionId = `reject-${workflowId}`;

      const workflow = workflows[workflowId];
      const previousStatus = workflow?.status;

      if (!previousStatus) {
        toast.error('Workflow not found');
        return;
      }

      // Optimistic update
      updateWorkflow(workflowId, { status: 'failed' });
      addPendingAction(actionId);

      try {
        await api.rejectWorkflow(workflowId, feedback);
        toast.success('Plan rejected');
      } catch (error) {
        updateWorkflow(workflowId, { status: previousStatus });
        toast.error(`Rejection failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      } finally {
        removePendingAction(actionId);
      }
    },
    [updateWorkflow, addPendingAction, removePendingAction, workflows]
  );

  const cancelWorkflow = useCallback(
    async (workflowId: string) => {
      const actionId = `cancel-${workflowId}`;

      const workflow = workflows[workflowId];
      const previousStatus = workflow?.status;

      if (!previousStatus) {
        toast.error('Workflow not found');
        return;
      }

      // Optimistic update
      updateWorkflow(workflowId, { status: 'cancelled' });
      addPendingAction(actionId);

      try {
        await api.cancelWorkflow(workflowId);
        toast.success('Workflow cancelled');
      } catch (error) {
        updateWorkflow(workflowId, { status: previousStatus });
        toast.error(
          `Cancellation failed: ${error instanceof Error ? error.message : 'Unknown error'}`
        );
      } finally {
        removePendingAction(actionId);
      }
    },
    [updateWorkflow, addPendingAction, removePendingAction, workflows]
  );

  const isActionPending = useCallback(
    (workflowId: string) => {
      return pendingActions.some((id) => id.endsWith(workflowId));
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
```

**Step 5: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- src/hooks/__tests__/useWorkflowActions.test.tsx`
Expected: PASS

**Step 6: Commit**

Run: `git add dashboard/src/hooks dashboard/src/components/Toast.tsx && git commit -m "feat(dashboard): add useWorkflowActions hook using useFetcher"`

---

## Task 9: Add Router Configuration Reference

**Description:** Document how loaders and actions connect to routes in the router configuration from Plan 08.

```typescript
// Example router configuration showing loader/action integration
// (Full implementation in Plan 10 - Dashboard Components)

{
  path: 'workflows',
  lazy: async () => {
    const { default: Component } = await import('@/pages/WorkflowsPage');
    const { workflowsLoader } = await import('@/loaders/workflows');
    return { Component, loader: workflowsLoader };
  },
  children: [
    {
      path: ':id',
      lazy: async () => {
        const { default: Component } = await import('@/pages/WorkflowDetailPage');
        const { workflowDetailLoader } = await import('@/loaders/workflows');
        return { Component, loader: workflowDetailLoader };
      },
      children: [
        {
          path: 'approve',
          lazy: async () => {
            const { approveAction } = await import('@/actions/workflows');
            return { action: approveAction };
          },
        },
        {
          path: 'reject',
          lazy: async () => {
            const { rejectAction } = await import('@/actions/workflows');
            return { action: rejectAction };
          },
        },
        {
          path: 'cancel',
          lazy: async () => {
            const { cancelAction } = await import('@/actions/workflows');
            return { action: cancelAction };
          },
        },
      ],
    },
  ],
},
{
  path: 'history',
  lazy: async () => {
    const { default: Component } = await import('@/pages/HistoryPage');
    const { historyLoader } = await import('@/loaders/workflows');
    return { Component, loader: historyLoader };
  },
}
```

---

## Task 10: Add Barrel Exports for Hooks, Actions, Loaders, and Components

**Files:**
- Create: `dashboard/src/hooks/index.ts`
- Create: `dashboard/src/components/index.ts`

**Step 1: Create barrel export files**

```typescript
// dashboard/src/hooks/index.ts
export { useWebSocket } from './useWebSocket';
export { useWorkflows } from './useWorkflows';
export { useWorkflowActions } from './useWorkflowActions';
```

```typescript
// dashboard/src/components/index.ts
export * as toast from './Toast';
```

**Step 2: Commit**

Run: `git add dashboard/src/hooks/index.ts dashboard/src/components/index.ts && git commit -m "feat(dashboard): add barrel exports for hooks and components"`

---

## Verification Checklist

After completing all tasks, verify:

- [ ] All TypeScript types compile without errors (`pnpm run type-check`)
- [ ] All tests pass (`pnpm test`)
- [ ] API client handles errors gracefully with proper error messages
- [ ] React Router loaders fetch data before render
- [ ] useLoaderData returns typed data in components
- [ ] Zustand store persists only UI state (selectedWorkflowId, lastEventId) to sessionStorage
- [ ] Zustand store does NOT store workflow data (comes from loaders)
- [ ] Zustand store enforces MAX_EVENTS_PER_WORKFLOW limit (500 events)
- [ ] WebSocket hook connects on mount and disconnects on unmount
- [ ] WebSocket hook reconnects with exponential backoff (1s, 2s, 4s, ..., max 30s)
- [ ] WebSocket hook includes `?since=` parameter when reconnecting with lastEventId
- [ ] WebSocket hook detects sequence gaps and logs warnings
- [ ] WebSocket hook handles backfill_expired by clearing lastEventId
- [ ] WebSocket hook dispatches 'workflow-event' custom events for revalidation hints
- [ ] useWorkflows hook combines loader data with real-time event state
- [ ] useWorkflows hook triggers revalidation for status-changing events
- [ ] React Router actions handle mutations (approve, reject, cancel)
- [ ] Revalidation works after actions complete
- [ ] useFetcher handles mutations with loading states
- [ ] No duplicate data fetching between loader and Zustand
- [ ] Pending actions prevent duplicate requests
- [ ] Toast notifications appear for action success/failure
- [ ] No console errors in browser during normal operation
- [ ] Code follows TypeScript best practices (strict mode, no `any` types)

---

## Summary

This plan implements a **hybrid data architecture** for the Amelia dashboard, combining React Router v7's data features with Zustand for real-time state:

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Data Flow                                │
├─────────────────────────────────────────────────────────────┤
│  React Router v7              │  Zustand Store              │
│  ────────────────────────     │  ────────────────────────   │
│  • Loaders for initial data   │  • WebSocket events         │
│  • Actions for mutations      │  • Connection state         │
│  • Automatic revalidation     │  • Selected workflow ID     │
│  • Type-safe data loading     │  • Pending actions          │
│                               │  • Real-time updates        │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

1. **Type Safety**: Comprehensive TypeScript types mirroring the FastAPI server models, including loader/action return types
2. **API Client**: Clean REST API abstraction with error handling
3. **Route Loaders**: Initial data fetching for workflows, workflow detail, and history pages
4. **Zustand Store**: Real-time WebSocket events and UI state only (no workflow data)
5. **WebSocket Hook**: Connection management, backfill, sequence gap detection, and revalidation hints
6. **Hybrid Hook (useWorkflows)**: Combines loader data with real-time events, triggers revalidation
7. **Route Actions**: Type-safe mutations with automatic revalidation
8. **useFetcher Hook**: Background mutations without navigation
9. **User Feedback**: Toast notifications for action outcomes

### Benefits of Hybrid Approach

- **Best of Both Worlds**: Route loaders for initial data, Zustand for real-time updates
- **Automatic Revalidation**: Actions trigger re-fetching of loader data
- **Type Safety**: End-to-end type safety from API to components
- **Optimistic UI**: Pending states via useFetcher, real-time events via Zustand
- **No Duplication**: Single source of truth - loader for data, Zustand for events
- **Server Authority**: Loaders always fetch fresh data from server
- **Real-time**: WebSocket events update UI instantly between revalidations

The architecture supports multi-workflow monitoring, graceful reconnection, responsive UI updates, and maintains React Router v7 best practices while leveraging Zustand's strengths for real-time state management.
