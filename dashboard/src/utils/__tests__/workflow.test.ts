import { describe, it, expect } from 'vitest';
import { getActiveWorkflow } from '../workflow';
import type { WorkflowSummary } from '@/types';

// Helper to create workflow summaries
function createWorkflow(overrides: Partial<WorkflowSummary> = {}): WorkflowSummary {
  return {
    id: 'test-id',
    issue_id: 'TEST-1',
    worktree_name: 'test-worktree',
    status: 'completed',
    current_stage: 'done',
    started_at: '2025-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('getActiveWorkflow', () => {
  it('should return running workflow when one exists', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'completed' }),
      createWorkflow({ id: '2', status: 'in_progress' }),
      createWorkflow({ id: '3', status: 'pending' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should return most recent completed workflow when no running', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
      createWorkflow({ id: '2', status: 'completed', started_at: '2025-01-03T00:00:00Z' }),
      createWorkflow({ id: '3', status: 'completed', started_at: '2025-01-02T00:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should return null when no workflows exist', () => {
    expect(getActiveWorkflow([])).toBeNull();
  });

  it('should prioritize running over completed', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'completed', started_at: '2025-12-01T00:00:00Z' }),
      createWorkflow({ id: '2', status: 'in_progress', started_at: '2025-01-01T00:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should sort completed by started_at descending', () => {
    const workflows = [
      createWorkflow({ id: 'oldest', status: 'completed', started_at: '2024-01-01T00:00:00Z' }),
      createWorkflow({ id: 'newest', status: 'completed', started_at: '2025-06-01T00:00:00Z' }),
      createWorkflow({ id: 'middle', status: 'completed', started_at: '2025-03-01T00:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('newest');
  });

  it('should return blocked workflow when no running exists', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'completed' }),
      createWorkflow({ id: '2', status: 'blocked' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should prioritize running over blocked', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'blocked' }),
      createWorkflow({ id: '2', status: 'in_progress' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should prioritize blocked over completed', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'completed', started_at: '2025-12-01T00:00:00Z' }),
      createWorkflow({ id: '2', status: 'blocked', started_at: '2025-01-01T00:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should handle null started_at in completed workflows', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'completed', started_at: null }),
      createWorkflow({ id: '2', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
      createWorkflow({ id: '3', status: 'completed', started_at: null }),
    ];
    // Should not throw, should return one of them
    const result = getActiveWorkflow(workflows);
    expect(result).not.toBeNull();
  });

  it('should return most recently started running workflow when multiple are in progress', () => {
    const workflows = [
      createWorkflow({ id: 'oldest-running', status: 'in_progress', started_at: '2025-01-01T05:00:00Z' }),
      createWorkflow({ id: 'newest-running', status: 'in_progress', started_at: '2025-01-01T01:00:00Z' }),
      createWorkflow({ id: 'middle-running', status: 'in_progress', started_at: '2025-01-01T03:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('oldest-running');
  });

  it('should return most recently started blocked workflow when multiple are blocked', () => {
    const workflows = [
      createWorkflow({ id: 'oldest-blocked', status: 'blocked', started_at: '2025-01-01T05:00:00Z' }),
      createWorkflow({ id: 'newest-blocked', status: 'blocked', started_at: '2025-01-01T01:00:00Z' }),
      createWorkflow({ id: 'middle-blocked', status: 'blocked', started_at: '2025-01-01T03:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('oldest-blocked');
  });

  it('should work correctly regardless of array order', () => {
    // Test with completed workflows listed first (like in the bug scenario)
    const workflows = [
      createWorkflow({ id: 'completed-1', status: 'completed', started_at: '2025-01-01T10:00:00Z' }),
      createWorkflow({ id: 'completed-2', status: 'completed', started_at: '2025-01-01T12:00:00Z' }),
      createWorkflow({ id: 'running-oldest', status: 'in_progress', started_at: '2025-01-01T03:00:00Z' }),
      createWorkflow({ id: 'running-newest', status: 'in_progress', started_at: '2025-01-01T01:00:00Z' }),
      createWorkflow({ id: 'blocked', status: 'blocked', started_at: '2025-01-01T02:00:00Z' }),
    ];
    // Should select the most recent running workflow (running-oldest), not the first in array
    expect(getActiveWorkflow(workflows)?.id).toBe('running-oldest');
  });
});
