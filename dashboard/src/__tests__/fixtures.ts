/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * Comprehensive test fixtures for the Amelia Dashboard.
 * Provides both factory functions and pre-configured mock data for various workflow states.
 */

import {
  StreamEventType,
  type WorkflowSummary,
  type WorkflowDetail,
  type WorkflowEvent,
  type StreamEvent,
  type TaskDAG,
  type TaskNode,
} from '../types';

// ============================================================================
// Factory Functions
// ============================================================================

/**
 * Creates a mock WorkflowSummary with sensible defaults.
 * @param overrides - Optional partial object to override default values
 */
export function createMockWorkflowSummary(
  overrides?: Partial<WorkflowSummary>
): WorkflowSummary {
  return {
    id: 'wf-test-123',
    issue_id: 'ISSUE-123',
    worktree_name: 'test-worktree',
    status: 'in_progress',
    started_at: '2025-12-06T10:00:00Z',
    current_stage: 'architect',
    ...overrides,
  };
}

/**
 * Creates a mock WorkflowDetail with sensible defaults.
 * @param overrides - Optional partial object to override default values
 */
export function createMockWorkflowDetail(
  overrides?: Partial<WorkflowDetail>
): WorkflowDetail {
  return {
    id: 'wf-test-123',
    issue_id: 'ISSUE-123',
    worktree_name: 'test-worktree',
    status: 'in_progress',
    started_at: '2025-12-06T10:00:00Z',
    current_stage: 'architect',
    worktree_path: '/tmp/test-worktree',
    completed_at: null,
    failure_reason: null,
    plan: null,
    token_usage: {},
    recent_events: [],
    ...overrides,
  };
}

/**
 * Creates a mock WorkflowEvent with sensible defaults.
 * @param overrides - Optional partial object to override default values
 */
export function createMockEvent(
  overrides?: Partial<WorkflowEvent>
): WorkflowEvent {
  return {
    id: 'evt-test-1',
    workflow_id: 'wf-test-123',
    sequence: 1,
    timestamp: '2025-12-06T10:00:00Z',
    agent: 'architect',
    event_type: 'workflow_started',
    message: 'Test event',
    data: undefined,
    correlation_id: undefined,
    ...overrides,
  };
}

/**
 * Creates a mock StreamEvent with sensible defaults.
 * Uses `subtype` (not `type`) to match the WebSocket payload format.
 * @param overrides - Optional partial object to override default values
 */
export function createMockStreamEvent(
  overrides?: Partial<StreamEvent>
): StreamEvent {
  return {
    subtype: StreamEventType.CLAUDE_THINKING,
    content: 'Test thinking content',
    timestamp: '2025-12-13T10:00:00Z',
    agent: 'architect',
    workflow_id: 'wf-test-123',
    tool_name: null,
    tool_input: null,
    ...overrides,
  };
}

// ============================================================================
// Workflow Summary Fixtures
// ============================================================================

/**
 * Array of mock workflow summaries representing various workflow states.
 * Includes workflows in different stages and statuses for comprehensive testing.
 */
export const mockWorkflowSummaries: WorkflowSummary[] = [
  {
    id: 'wf-pending-001',
    issue_id: 'ISSUE-001',
    worktree_name: 'amelia-issue-001',
    status: 'pending',
    started_at: null,
    current_stage: null,
  },
  {
    id: 'wf-in-progress-002',
    issue_id: 'ISSUE-002',
    worktree_name: 'amelia-issue-002',
    status: 'in_progress',
    started_at: '2025-12-06T10:00:00Z',
    current_stage: 'architect',
  },
  {
    id: 'wf-blocked-003',
    issue_id: 'ISSUE-003',
    worktree_name: 'amelia-issue-003',
    status: 'blocked',
    started_at: '2025-12-06T11:00:00Z',
    current_stage: 'developer',
  },
  {
    id: 'wf-completed-004',
    issue_id: 'ISSUE-004',
    worktree_name: 'amelia-issue-004',
    status: 'completed',
    started_at: '2025-12-05T09:00:00Z',
    current_stage: 'reviewer',
  },
  {
    id: 'wf-failed-005',
    issue_id: 'ISSUE-005',
    worktree_name: 'amelia-issue-005',
    status: 'failed',
    started_at: '2025-12-05T08:00:00Z',
    current_stage: 'developer',
  },
  {
    id: 'wf-cancelled-006',
    issue_id: 'ISSUE-006',
    worktree_name: 'amelia-issue-006',
    status: 'cancelled',
    started_at: '2025-12-04T14:00:00Z',
    current_stage: 'architect',
  },
];

// ============================================================================
// Task DAG Fixtures
// ============================================================================

/**
 * Mock task nodes for a complete workflow plan.
 */
export const mockTaskNodes: TaskNode[] = [
  {
    id: 'task-1',
    description: 'Analyze requirements and create high-level architecture',
    dependencies: [],
    status: 'completed',
  },
  {
    id: 'task-2',
    description: 'Implement user authentication module',
    dependencies: ['task-1'],
    status: 'completed',
  },
  {
    id: 'task-3',
    description: 'Implement API endpoints for user management',
    dependencies: ['task-2'],
    status: 'in_progress',
  },
  {
    id: 'task-4',
    description: 'Review authentication implementation',
    dependencies: ['task-2'],
    status: 'pending',
  },
  {
    id: 'task-5',
    description: 'Write integration tests for authentication flow',
    dependencies: ['task-4'],
    status: 'pending',
  },
];

/**
 * Mock task DAG representing a complete execution plan.
 */
export const mockTaskDAG: TaskDAG = {
  tasks: mockTaskNodes,
  execution_order: ['task-1', 'task-2', 'task-3', 'task-4', 'task-5'],
};

// ============================================================================
// Workflow Event Fixtures
// ============================================================================

/**
 * Array of mock workflow events covering all event types.
 */
export const mockWorkflowEvents: WorkflowEvent[] = [
  {
    id: 'evt-001',
    workflow_id: 'wf-in-progress-002',
    sequence: 1,
    timestamp: '2025-12-06T10:00:00Z',
    agent: 'orchestrator',
    event_type: 'workflow_started',
    message: 'Workflow started for issue ISSUE-002',
    data: { issue_id: 'ISSUE-002' },
  },
  {
    id: 'evt-002',
    workflow_id: 'wf-in-progress-002',
    sequence: 2,
    timestamp: '2025-12-06T10:00:05Z',
    agent: 'architect',
    event_type: 'stage_started',
    message: 'Architect agent started planning',
    data: { stage: 'architect' },
  },
  {
    id: 'evt-003',
    workflow_id: 'wf-in-progress-002',
    sequence: 3,
    timestamp: '2025-12-06T10:02:30Z',
    agent: 'architect',
    event_type: 'stage_completed',
    message: 'Architect completed execution plan with 5 tasks',
    data: { task_count: 5 },
  },
  {
    id: 'evt-004',
    workflow_id: 'wf-in-progress-002',
    sequence: 4,
    timestamp: '2025-12-06T10:02:35Z',
    agent: 'orchestrator',
    event_type: 'approval_required',
    message: 'Waiting for human approval of execution plan',
    data: { approval_type: 'plan' },
  },
  {
    id: 'evt-005',
    workflow_id: 'wf-blocked-003',
    sequence: 1,
    timestamp: '2025-12-06T11:00:00Z',
    agent: 'orchestrator',
    event_type: 'workflow_started',
    message: 'Workflow started for issue ISSUE-003',
  },
  {
    id: 'evt-006',
    workflow_id: 'wf-blocked-003',
    sequence: 2,
    timestamp: '2025-12-06T11:05:00Z',
    agent: 'developer',
    event_type: 'file_created',
    message: 'Created new file: src/auth/login.py',
    data: { file_path: 'src/auth/login.py' },
  },
  {
    id: 'evt-007',
    workflow_id: 'wf-blocked-003',
    sequence: 3,
    timestamp: '2025-12-06T11:06:00Z',
    agent: 'developer',
    event_type: 'file_modified',
    message: 'Modified file: src/auth/__init__.py',
    data: { file_path: 'src/auth/__init__.py' },
  },
  {
    id: 'evt-008',
    workflow_id: 'wf-blocked-003',
    sequence: 4,
    timestamp: '2025-12-06T11:10:00Z',
    agent: 'developer',
    event_type: 'review_requested',
    message: 'Developer requested code review',
    data: { files_changed: 5 },
  },
  {
    id: 'evt-009',
    workflow_id: 'wf-completed-004',
    sequence: 10,
    timestamp: '2025-12-05T09:45:00Z',
    agent: 'reviewer',
    event_type: 'review_completed',
    message: 'Reviewer approved all changes',
  },
  {
    id: 'evt-010',
    workflow_id: 'wf-completed-004',
    sequence: 11,
    timestamp: '2025-12-05T09:45:05Z',
    agent: 'orchestrator',
    event_type: 'workflow_completed',
    message: 'Workflow completed successfully',
    data: { total_tasks: 8, duration_seconds: 2705 },
  },
  {
    id: 'evt-011',
    workflow_id: 'wf-failed-005',
    sequence: 5,
    timestamp: '2025-12-05T08:15:00Z',
    agent: 'developer',
    event_type: 'system_error',
    message: 'Failed to execute task: syntax error in generated code',
    data: { error: 'SyntaxError: unexpected token', task_id: 'task-3' },
  },
  {
    id: 'evt-012',
    workflow_id: 'wf-failed-005',
    sequence: 6,
    timestamp: '2025-12-05T08:15:05Z',
    agent: 'orchestrator',
    event_type: 'workflow_failed',
    message: 'Workflow failed due to unrecoverable error',
    data: { reason: 'Task execution error' },
  },
  {
    id: 'evt-013',
    workflow_id: 'wf-cancelled-006',
    sequence: 3,
    timestamp: '2025-12-04T14:15:00Z',
    agent: 'orchestrator',
    event_type: 'workflow_cancelled',
    message: 'Workflow cancelled by user',
    data: { cancelled_by: 'user@example.com' },
  },
];

// ============================================================================
// Workflow Detail Fixtures
// ============================================================================

/**
 * Mock workflow detail with complete data including plan, events, and token usage.
 * Represents a workflow in active development with approval pending.
 */
export const mockWorkflowDetail: WorkflowDetail = {
  id: 'wf-in-progress-002',
  issue_id: 'ISSUE-002',
  worktree_name: 'amelia-issue-002',
  worktree_path: '/tmp/amelia-worktrees/amelia-issue-002',
  status: 'blocked',
  started_at: '2025-12-06T10:00:00Z',
  completed_at: null,
  failure_reason: null,
  current_stage: 'developer',
  plan: mockTaskDAG,
  token_usage: {
    architect: {
      total_tokens: 15430,
      total_cost_usd: 0.0462,
    },
    developer: {
      total_tokens: 28750,
      total_cost_usd: 0.0863,
    },
    reviewer: {
      total_tokens: 0,
      total_cost_usd: 0.0,
    },
  },
  recent_events: mockWorkflowEvents.filter(
    (evt) => evt.workflow_id === 'wf-in-progress-002'
  ),
};

/**
 * Mock workflow detail for a completed workflow.
 */
export const mockCompletedWorkflowDetail: WorkflowDetail = {
  id: 'wf-completed-004',
  issue_id: 'ISSUE-004',
  worktree_name: 'amelia-issue-004',
  worktree_path: '/tmp/amelia-worktrees/amelia-issue-004',
  status: 'completed',
  started_at: '2025-12-05T09:00:00Z',
  completed_at: '2025-12-05T09:45:05Z',
  failure_reason: null,
  current_stage: 'reviewer',
  plan: mockTaskDAG,
  token_usage: {
    architect: {
      total_tokens: 12500,
      total_cost_usd: 0.0375,
    },
    developer: {
      total_tokens: 45000,
      total_cost_usd: 0.135,
    },
    reviewer: {
      total_tokens: 18200,
      total_cost_usd: 0.0546,
    },
  },
  recent_events: mockWorkflowEvents.filter(
    (evt) => evt.workflow_id === 'wf-completed-004'
  ),
};

/**
 * Mock workflow detail for a failed workflow.
 */
export const mockFailedWorkflowDetail: WorkflowDetail = {
  id: 'wf-failed-005',
  issue_id: 'ISSUE-005',
  worktree_name: 'amelia-issue-005',
  worktree_path: '/tmp/amelia-worktrees/amelia-issue-005',
  status: 'failed',
  started_at: '2025-12-05T08:00:00Z',
  completed_at: '2025-12-05T08:15:05Z',
  failure_reason: 'Task execution error: syntax error in generated code',
  current_stage: 'developer',
  plan: {
    tasks: mockTaskNodes.slice(0, 3),
    execution_order: ['task-1', 'task-2', 'task-3'],
  },
  token_usage: {
    architect: {
      total_tokens: 11200,
      total_cost_usd: 0.0336,
    },
    developer: {
      total_tokens: 22400,
      total_cost_usd: 0.0672,
    },
    reviewer: {
      total_tokens: 0,
      total_cost_usd: 0.0,
    },
  },
  recent_events: mockWorkflowEvents.filter(
    (evt) => evt.workflow_id === 'wf-failed-005'
  ),
};

/**
 * Mock workflow detail for a pending workflow (not yet started).
 */
export const mockPendingWorkflowDetail: WorkflowDetail = {
  id: 'wf-pending-001',
  issue_id: 'ISSUE-001',
  worktree_name: 'amelia-issue-001',
  worktree_path: '/tmp/amelia-worktrees/amelia-issue-001',
  status: 'pending',
  started_at: null,
  completed_at: null,
  failure_reason: null,
  current_stage: null,
  plan: null,
  token_usage: {},
  recent_events: [],
}
