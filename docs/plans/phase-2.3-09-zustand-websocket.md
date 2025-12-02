# Zustand Store & WebSocket Hook Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Zustand store for workflow state management, WebSocket connection hook with reconnection logic, API client module, and optimistic UI update pattern for workflow actions.

**Architecture:** Zustand store with sessionStorage persistence for UI state, WebSocket hook with exponential backoff reconnection and sequence gap detection, REST API client using fetch, custom hooks for workflows and actions with optimistic updates and rollback on failure.

**Tech Stack:** Zustand, TypeScript, Vitest, React Testing Library, native fetch API

**Depends on:** Plan 8 (React Dashboard Setup)

---

## Task 1: Create TypeScript Types for API Models

**Files:**
- Create: `dashboard/src/types/index.ts`
- Create: `dashboard/src/types/api.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/types/__tests__/api.test.ts
import { describe, it, expect } from 'vitest';
import type {
  WorkflowStatus,
  EventType,
  WorkflowSummary,
  WorkflowEvent,
  TokenUsage,
  WorkflowDetailResponse,
} from '../api';

describe('API Type Definitions', () => {
  it('should define WorkflowStatus as literal union', () => {
    const statuses: WorkflowStatus[] = [
      'pending',
      'in_progress',
      'blocked',
      'completed',
      'failed',
      'cancelled',
    ];

    statuses.forEach((status) => {
      expect(['pending', 'in_progress', 'blocked', 'completed', 'failed', 'cancelled']).toContain(
        status
      );
    });
  });

  it('should create valid WorkflowSummary object', () => {
    const summary: WorkflowSummary = {
      id: 'wf-123',
      issue_id: 'ISSUE-456',
      worktree_name: 'feature-branch',
      status: 'in_progress',
      started_at: '2025-12-01T10:00:00Z',
      current_stage: 'architect',
    };

    expect(summary.id).toBe('wf-123');
    expect(summary.status).toBe('in_progress');
  });

  it('should create valid WorkflowEvent object', () => {
    const event: WorkflowEvent = {
      id: 'evt-789',
      workflow_id: 'wf-123',
      sequence: 5,
      timestamp: '2025-12-01T10:05:00Z',
      agent: 'architect',
      event_type: 'stage_started',
      message: 'Planning started',
      data: { stage: 'architect' },
      correlation_id: null,
    };

    expect(event.id).toBe('evt-789');
    expect(event.sequence).toBe(5);
    expect(event.event_type).toBe('stage_started');
  });

  it('should create valid TokenUsage object', () => {
    const usage: TokenUsage = {
      workflow_id: 'wf-123',
      agent: 'architect',
      model: 'claude-sonnet-4-20250514',
      input_tokens: 1000,
      output_tokens: 500,
      cache_read_tokens: 200,
      cache_creation_tokens: 50,
      cost_usd: 0.015,
      timestamp: '2025-12-01T10:00:00Z',
    };

    expect(usage.input_tokens).toBe(1000);
    expect(usage.cache_read_tokens).toBe(200);
  });

  it('should create valid WorkflowDetailResponse object', () => {
    const detail: WorkflowDetailResponse = {
      id: 'wf-123',
      issue_id: 'ISSUE-456',
      worktree_path: '/home/user/project',
      worktree_name: 'feature-branch',
      status: 'blocked',
      started_at: '2025-12-01T10:00:00Z',
      completed_at: null,
      failure_reason: null,
      current_stage: 'architect',
      plan: null,
      token_usage: {
        architect: {
          input_tokens: 1000,
          output_tokens: 500,
          total_tokens: 1500,
          estimated_cost_usd: 0.015,
        },
      },
      recent_events: [],
    };

    expect(detail.status).toBe('blocked');
    expect(detail.token_usage.architect.total_tokens).toBe(1500);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test -- src/types/__tests__/api.test.ts`
Expected: FAIL with module not found or type errors

**Step 3: Implement TypeScript type definitions**

```typescript
// dashboard/src/types/api.ts
/**
 * TypeScript types mirroring the FastAPI server models.
 * Keep in sync with amelia/server/models/*.py
 */

export type WorkflowStatus =
  | 'pending'
  | 'in_progress'
  | 'blocked'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type EventType =
  // Lifecycle
  | 'workflow_started'
  | 'workflow_completed'
  | 'workflow_failed'
  | 'workflow_cancelled'
  // Stages
  | 'stage_started'
  | 'stage_completed'
  // Approval
  | 'approval_required'
  | 'approval_granted'
  | 'approval_rejected'
  // Artifacts
  | 'file_created'
  | 'file_modified'
  | 'file_deleted'
  // Review cycle
  | 'review_requested'
  | 'review_completed'
  | 'revision_requested'
  // System
  | 'system_error'
  | 'system_warning';

export interface WorkflowSummary {
  id: string;
  issue_id: string;
  worktree_name: string;
  status: WorkflowStatus;
  started_at: string | null; // ISO 8601 datetime
  current_stage: string | null;
}

export interface WorkflowEvent {
  id: string;
  workflow_id: string;
  sequence: number;
  timestamp: string; // ISO 8601 datetime
  agent: string;
  event_type: EventType;
  message: string;
  data: Record<string, unknown> | null;
  correlation_id: string | null;
}

export interface TokenSummary {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
}

export interface TokenUsage {
  workflow_id: string;
  agent: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cost_usd: number | null;
  timestamp: string; // ISO 8601 datetime
}

export interface WorkflowDetailResponse {
  id: string;
  issue_id: string;
  worktree_path: string;
  worktree_name: string;
  status: WorkflowStatus;
  started_at: string | null;
  completed_at: string | null;
  failure_reason: string | null;
  current_stage: string | null;
  plan: unknown | null; // TaskDAG - complex type, use unknown for now
  token_usage: Record<string, TokenSummary>;
  recent_events: WorkflowEvent[];
}

export interface WorkflowListResponse {
  workflows: WorkflowSummary[];
  total: number;
  cursor: string | null;
  has_more: boolean;
}

export interface CreateWorkflowRequest {
  issue_id: string;
  worktree_path: string;
  worktree_name: string | null;
}

export interface CreateWorkflowResponse {
  id: string;
  status: WorkflowStatus;
  message: string;
}

export interface RejectRequest {
  feedback: string;
}

export interface ErrorResponse {
  error: string;
  code: string;
  details?: Record<string, unknown>;
}

// WebSocket message types
export type WebSocketMessage =
  | { type: 'event'; payload: WorkflowEvent }
  | { type: 'ping' }
  | { type: 'backfill_complete'; count: number }
  | { type: 'backfill_expired'; message: string };

export type WebSocketClientMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' };
```

```typescript
// dashboard/src/types/index.ts
export * from './api';
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && npm test -- src/types/__tests__/api.test.ts`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/types && git commit -m "feat(dashboard): add TypeScript types for API models"`

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

Run: `cd dashboard && npm test -- src/api/__tests__/client.test.ts`
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

Run: `cd dashboard && npm test -- src/api/__tests__/client.test.ts`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/api && git commit -m "feat(dashboard): add REST API client module"`

---

## Task 3: Implement Zustand Workflow Store

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
    sessionStorageMock.clear();
  });

  describe('setWorkflows', () => {
    it('should convert array to Record and set lastSyncAt', () => {
      const workflows: WorkflowSummary[] = [
        {
          id: 'wf-1',
          issue_id: 'ISSUE-1',
          worktree_name: 'main',
          status: 'in_progress',
          started_at: '2025-12-01T10:00:00Z',
          current_stage: 'architect',
        },
        {
          id: 'wf-2',
          issue_id: 'ISSUE-2',
          worktree_name: 'feature',
          status: 'blocked',
          started_at: '2025-12-01T11:00:00Z',
          current_stage: 'architect',
        },
      ];

      useWorkflowStore.getState().setWorkflows(workflows);

      const state = useWorkflowStore.getState();
      expect(state.workflows['wf-1']).toEqual(workflows[0]);
      expect(state.workflows['wf-2']).toEqual(workflows[1]);
      expect(state.lastSyncAt).not.toBeNull();
      expect(state.isLoading).toBe(false);
    });

    it('should auto-select first workflow if none selected', () => {
      const workflows: WorkflowSummary[] = [
        {
          id: 'wf-1',
          issue_id: 'ISSUE-1',
          worktree_name: 'main',
          status: 'in_progress',
          started_at: '2025-12-01T10:00:00Z',
          current_stage: 'architect',
        },
      ];

      useWorkflowStore.getState().setWorkflows(workflows);

      expect(useWorkflowStore.getState().selectedWorkflowId).toBe('wf-1');
    });

    it('should preserve selectedWorkflowId if already set', () => {
      useWorkflowStore.setState({ selectedWorkflowId: 'wf-2' });

      const workflows: WorkflowSummary[] = [
        {
          id: 'wf-1',
          issue_id: 'ISSUE-1',
          worktree_name: 'main',
          status: 'in_progress',
          started_at: '2025-12-01T10:00:00Z',
          current_stage: 'architect',
        },
      ];

      useWorkflowStore.getState().setWorkflows(workflows);

      expect(useWorkflowStore.getState().selectedWorkflowId).toBe('wf-2');
    });
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

      expect(useWorkflowStore.getState().pendingActions).toContain('approve-wf-1');
    });

    it('should not duplicate pending action', () => {
      useWorkflowStore.getState().addPendingAction('approve-wf-1');
      useWorkflowStore.getState().addPendingAction('approve-wf-1');

      expect(useWorkflowStore.getState().pendingActions).toHaveLength(1);
    });

    it('should remove pending action', () => {
      useWorkflowStore.getState().addPendingAction('approve-wf-1');
      useWorkflowStore.getState().removePendingAction('approve-wf-1');

      expect(useWorkflowStore.getState().pendingActions).toHaveLength(0);
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
      useWorkflowStore.getState().setLastEventId('evt-999');

      const stored = sessionStorageMock.getItem('amelia-workflow-state');
      const parsed = JSON.parse(stored!);
      expect(parsed.state.lastEventId).toBe('evt-999');
    });

    it('should NOT persist workflows to sessionStorage', () => {
      const workflows: WorkflowSummary[] = [
        {
          id: 'wf-1',
          issue_id: 'ISSUE-1',
          worktree_name: 'main',
          status: 'in_progress',
          started_at: '2025-12-01T10:00:00Z',
          current_stage: 'architect',
        },
      ];

      useWorkflowStore.getState().setWorkflows(workflows);

      const stored = sessionStorageMock.getItem('amelia-workflow-state');
      const parsed = JSON.parse(stored!);
      expect(parsed.state.workflows).toBeUndefined();
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test -- src/store/__tests__/workflowStore.test.ts`
Expected: FAIL with module not found

**Step 3: Install Zustand**

Run: `cd dashboard && npm install zustand`

**Step 4: Implement Zustand store**

```typescript
// dashboard/src/store/workflowStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { WorkflowSummary, WorkflowEvent } from '../types';

const MAX_EVENTS_PER_WORKFLOW = 500;

interface WorkflowState {
  // All active workflows (one per worktree)
  workflows: Record<string, WorkflowSummary>;

  // Currently selected workflow for detail view
  selectedWorkflowId: string | null;

  // Events grouped by workflow
  eventsByWorkflow: Record<string, WorkflowEvent[]>;

  // Last seen event ID for reconnection backfill
  lastEventId: string | null;

  // Request/connection states
  isLoading: boolean;
  error: string | null;
  isConnected: boolean;
  lastSyncAt: Date | null;
  pendingActions: string[]; // Action IDs currently in flight

  // Actions
  setWorkflows: (workflows: WorkflowSummary[]) => void;
  selectWorkflow: (id: string | null) => void;
  addEvent: (event: WorkflowEvent) => void;
  updateWorkflow: (id: string, update: Partial<WorkflowSummary>) => void;
  setLastEventId: (id: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setConnected: (connected: boolean) => void;
  addPendingAction: (actionId: string) => void;
  removePendingAction: (actionId: string) => void;
  clearError: () => void;
}

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set, get) => ({
      workflows: {},
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isLoading: false,
      error: null,
      isConnected: false,
      lastSyncAt: null,
      pendingActions: [],

      setWorkflows: (workflows) =>
        set({
          workflows: Object.fromEntries(workflows.map((w) => [w.id, w])),
          // Auto-select first workflow if none selected
          selectedWorkflowId: get().selectedWorkflowId ?? workflows[0]?.id ?? null,
          lastSyncAt: new Date(),
          isLoading: false,
        }),

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

      updateWorkflow: (id, update) =>
        set((state) => {
          const workflow = state.workflows[id];
          if (!workflow) return state;
          return {
            workflows: {
              ...state.workflows,
              [id]: { ...workflow, ...update },
            },
          };
        }),

      setLastEventId: (id) => set({ lastEventId: id }),

      setLoading: (loading) => set({ isLoading: loading }),

      setError: (error) => set({ error, isLoading: false }),

      setConnected: (connected) =>
        set({
          isConnected: connected,
          error: connected ? null : 'Connection lost',
        }),

      addPendingAction: (actionId) =>
        set((state) => ({
          pendingActions: state.pendingActions.includes(actionId)
            ? state.pendingActions
            : [...state.pendingActions, actionId],
        })),

      removePendingAction: (actionId) =>
        set((state) => ({
          pendingActions: state.pendingActions.filter((id) => id !== actionId),
        })),

      clearError: () => set({ error: null }),
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
      // Only persist UI state, not workflow data (re-fetched on reconnect)
      partialize: (state) => ({
        selectedWorkflowId: state.selectedWorkflowId,
        lastEventId: state.lastEventId,
      }),
    }
  )
);
```

**Step 5: Run test to verify it passes**

Run: `cd dashboard && npm test -- src/store/__tests__/workflowStore.test.ts`
Expected: PASS

**Step 6: Commit**

Run: `git add dashboard/src/store dashboard/package.json dashboard/package-lock.json && git commit -m "feat(dashboard): add Zustand store with sessionStorage persistence"`

---

## Task 4: Implement WebSocket Connection Hook

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
        data: JSON.stringify({ type: 'event', payload: event }),
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
          payload: {
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
          payload: {
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

Run: `cd dashboard && npm test -- src/hooks/__tests__/useWebSocket.test.tsx`
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
          handleEvent(message.payload);
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

Run: `cd dashboard && npm test -- src/hooks/__tests__/useWebSocket.test.tsx`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/hooks && git commit -m "feat(dashboard): add WebSocket hook with reconnection and backfill"`

---

## Task 5: Implement useWorkflows Hook

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
import { api } from '../../api/client';

vi.mock('../../api/client');

describe('useWorkflows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
  });

  it('should fetch workflows on mount', async () => {
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

    renderHook(() => useWorkflows());

    await waitFor(() => {
      expect(api.getWorkflows).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      const state = useWorkflowStore.getState();
      expect(state.workflows['wf-1']).toEqual(mockWorkflows[0]);
      expect(state.isLoading).toBe(false);
    });
  });

  it('should set loading state during fetch', async () => {
    vi.mocked(api.getWorkflows).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve([]), 100);
        })
    );

    renderHook(() => useWorkflows());

    // Should be loading initially
    expect(useWorkflowStore.getState().isLoading).toBe(true);

    await waitFor(() => {
      expect(useWorkflowStore.getState().isLoading).toBe(false);
    });
  });

  it('should handle fetch errors', async () => {
    const errorMessage = 'Network error';
    vi.mocked(api.getWorkflows).mockRejectedValueOnce(new Error(errorMessage));

    renderHook(() => useWorkflows());

    await waitFor(() => {
      const state = useWorkflowStore.getState();
      expect(state.error).toBe(errorMessage);
      expect(state.isLoading).toBe(false);
    });
  });

  it('should provide refresh function', async () => {
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

    vi.mocked(api.getWorkflows).mockResolvedValue(mockWorkflows);

    const { result } = renderHook(() => useWorkflows());

    await waitFor(() => {
      expect(api.getWorkflows).toHaveBeenCalledTimes(1);
    });

    // Call refresh
    result.current.refresh();

    await waitFor(() => {
      expect(api.getWorkflows).toHaveBeenCalledTimes(2);
    });
  });

  it('should return workflow array from store', async () => {
    const mockWorkflows = [
      {
        id: 'wf-1',
        issue_id: 'ISSUE-1',
        worktree_name: 'main',
        status: 'in_progress' as const,
        started_at: '2025-12-01T10:00:00Z',
        current_stage: 'architect',
      },
      {
        id: 'wf-2',
        issue_id: 'ISSUE-2',
        worktree_name: 'feature',
        status: 'blocked' as const,
        started_at: '2025-12-01T11:00:00Z',
        current_stage: 'architect',
      },
    ];

    vi.mocked(api.getWorkflows).mockResolvedValueOnce(mockWorkflows);

    const { result } = renderHook(() => useWorkflows());

    await waitFor(() => {
      expect(result.current.workflows).toHaveLength(2);
      expect(result.current.workflows[0].id).toBe('wf-1');
      expect(result.current.workflows[1].id).toBe('wf-2');
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test -- src/hooks/__tests__/useWorkflows.test.tsx`
Expected: FAIL with module not found

**Step 3: Implement useWorkflows hook**

```typescript
// dashboard/src/hooks/useWorkflows.ts
import { useEffect, useCallback } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import { api } from '../api/client';

export function useWorkflows() {
  const { workflows, isLoading, error, setWorkflows, setLoading, setError } = useWorkflowStore();

  const fetchWorkflows = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await api.getWorkflows();
      setWorkflows(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch workflows');
    }
  }, [setWorkflows, setLoading, setError]);

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  return {
    workflows: Object.values(workflows),
    isLoading,
    error,
    refresh: fetchWorkflows,
  };
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && npm test -- src/hooks/__tests__/useWorkflows.test.tsx`
Expected: PASS

**Step 5: Commit**

Run: `git add dashboard/src/hooks && git commit -m "feat(dashboard): add useWorkflows hook for fetching active workflows"`

---

## Task 6: Implement useWorkflowActions Hook with Optimistic Updates

**Files:**
- Create: `dashboard/src/hooks/useWorkflowActions.ts`
- Create: `dashboard/src/hooks/__tests__/useWorkflowActions.test.tsx`
- Create: `dashboard/src/components/Toast.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/hooks/__tests__/useWorkflowActions.test.tsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useWorkflowActions } from '../useWorkflowActions';
import { useWorkflowStore } from '../../store/workflowStore';
import { api } from '../../api/client';
import * as Toast from '../../components/Toast';

vi.mock('../../api/client');
vi.mock('../../components/Toast');

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

Run: `cd dashboard && npm test -- src/hooks/__tests__/useWorkflowActions.test.tsx`
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

Run: `cd dashboard && npm test -- src/hooks/__tests__/useWorkflowActions.test.tsx`
Expected: PASS

**Step 6: Commit**

Run: `git add dashboard/src/hooks dashboard/src/components/Toast.tsx && git commit -m "feat(dashboard): add useWorkflowActions with optimistic updates"`

---

## Task 7: Add Barrel Exports for Hooks and Components

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

- [ ] All TypeScript types compile without errors (`npm run type-check`)
- [ ] All tests pass (`npm test`)
- [ ] API client handles errors gracefully with proper error messages
- [ ] Zustand store persists only UI state (selectedWorkflowId, lastEventId) to sessionStorage
- [ ] Zustand store enforces MAX_EVENTS_PER_WORKFLOW limit (500 events)
- [ ] WebSocket hook connects on mount and disconnects on unmount
- [ ] WebSocket hook reconnects with exponential backoff (1s, 2s, 4s, ..., max 30s)
- [ ] WebSocket hook includes `?since=` parameter when reconnecting with lastEventId
- [ ] WebSocket hook detects sequence gaps and logs warnings
- [ ] WebSocket hook handles backfill_expired by clearing lastEventId
- [ ] useWorkflows hook fetches active workflows on mount
- [ ] useWorkflowActions applies optimistic updates immediately
- [ ] useWorkflowActions rolls back on API errors
- [ ] Pending actions prevent duplicate requests
- [ ] Toast notifications appear for action success/failure
- [ ] No console errors in browser during normal operation
- [ ] Code follows TypeScript best practices (strict mode, no `any` types)

---

## Summary

This plan implements the complete state management and real-time communication layer for the Amelia dashboard:

1. **Type Safety**: Comprehensive TypeScript types mirroring the FastAPI server models
2. **API Client**: Clean REST API abstraction with error handling
3. **State Management**: Zustand store with sessionStorage persistence for UI state only
4. **Real-time Updates**: WebSocket hook with connection management, backfill, and sequence gap detection
5. **Data Fetching**: Custom hooks for workflows with loading and error states
6. **Optimistic UI**: Action hooks with immediate updates and rollback on failure
7. **User Feedback**: Toast notifications for action outcomes

The architecture supports multi-workflow monitoring, graceful reconnection, and responsive UI updates while maintaining a single source of truth on the server.
