/**
 * Shared test fixtures for the Amelia Dashboard.
 * Provides factory functions to create mock data with sensible defaults.
 */

import type { WorkflowSummary, WorkflowDetail, WorkflowEvent } from '../types';

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
