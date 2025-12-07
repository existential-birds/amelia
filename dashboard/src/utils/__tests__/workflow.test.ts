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
      createWorkflow({ id: '3', status: 'queued' }),
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
});
