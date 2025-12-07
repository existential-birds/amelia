import type { WorkflowSummary, WorkflowDetail } from '../../types';

/**
 * Creates a mock WorkflowSummary for testing.
 */
export function createMockWorkflowSummary(
  overrides?: Partial<WorkflowSummary>
): WorkflowSummary {
  return {
    id: 'wf-1',
    issue_id: 'ISSUE-1',
    worktree_name: 'main',
    status: 'in_progress',
    started_at: '2025-12-01T10:00:00Z',
    current_stage: 'architect',
    ...overrides,
  };
}

/**
 * Creates a mock WorkflowDetail for testing.
 */
export function createMockWorkflowDetail(
  overrides?: Partial<WorkflowDetail>
): WorkflowDetail {
  return {
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
    ...overrides,
  };
}
