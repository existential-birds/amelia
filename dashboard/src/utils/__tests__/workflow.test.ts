import { describe, it, expect } from 'vitest';
import { getActiveWorkflow, getMostRecentCompleted, formatTokens, formatCost, formatDuration } from '../workflow';
import type { WorkflowSummary } from '@/types';

// Helper to create workflow summaries
function createWorkflow(overrides: Partial<WorkflowSummary> = {}): WorkflowSummary {
  return {
    id: 'test-id',
    issue_id: 'TEST-1',
    worktree_path: '/tmp/worktrees/test-worktree',
    profile: null,
    status: 'completed',
    current_stage: 'done',
    created_at: '2024-12-31T23:55:00Z',
    started_at: '2025-01-01T00:00:00Z',
    total_cost_usd: null,
    total_tokens: null,
    total_duration_ms: null,
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

describe('getMostRecentCompleted', () => {
  it('should return the most recently completed workflow', () => {
    const workflows = [
      createWorkflow({ id: 'oldest', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
      createWorkflow({ id: 'newest', status: 'completed', started_at: '2025-01-03T00:00:00Z' }),
      createWorkflow({ id: 'middle', status: 'completed', started_at: '2025-01-02T00:00:00Z' }),
    ];
    expect(getMostRecentCompleted(workflows)?.id).toBe('newest');
  });

  it('should return null when no completed workflows exist', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'in_progress' }),
      createWorkflow({ id: '2', status: 'blocked' }),
    ];
    expect(getMostRecentCompleted(workflows)).toBeNull();
  });

  it('should return null for empty array', () => {
    expect(getMostRecentCompleted([])).toBeNull();
  });

  it('should ignore non-completed workflows', () => {
    const workflows = [
      createWorkflow({ id: 'completed', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
      createWorkflow({ id: 'running', status: 'in_progress', started_at: '2025-01-03T00:00:00Z' }),
      createWorkflow({ id: 'failed', status: 'failed', started_at: '2025-01-02T00:00:00Z' }),
    ];
    expect(getMostRecentCompleted(workflows)?.id).toBe('completed');
  });

  it('should handle workflows with null started_at', () => {
    const workflows = [
      createWorkflow({ id: '1', status: 'completed', started_at: null }),
      createWorkflow({ id: '2', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
    ];
    // Should return one of them without throwing
    const result = getMostRecentCompleted(workflows);
    expect(result).not.toBeNull();
  });
});

// ============================================================================
// Formatting Functions
// ============================================================================

describe('formatTokens', () => {
  it('returns raw number for values under 1000', () => {
    expect(formatTokens(0)).toBe('0');
    expect(formatTokens(500)).toBe('500');
    expect(formatTokens(999)).toBe('999');
  });

  it('formats thousands with K suffix', () => {
    expect(formatTokens(1000)).toBe('1K');
    expect(formatTokens(1500)).toBe('1.5K');
    expect(formatTokens(2100)).toBe('2.1K');
  });

  it('formats larger values correctly', () => {
    expect(formatTokens(15200)).toBe('15.2K');
    expect(formatTokens(13700)).toBe('13.7K');
    expect(formatTokens(100000)).toBe('100K');
  });

  it('removes trailing zeros after decimal', () => {
    expect(formatTokens(1000)).toBe('1K');
    expect(formatTokens(2000)).toBe('2K');
    expect(formatTokens(10000)).toBe('10K');
  });
});

describe('formatCost', () => {
  it('formats cost with dollar sign and 2 decimal places', () => {
    expect(formatCost(0)).toBe('$0.00');
    expect(formatCost(0.08)).toBe('$0.08');
    expect(formatCost(0.42)).toBe('$0.42');
    expect(formatCost(1.5)).toBe('$1.50');
    expect(formatCost(10)).toBe('$10.00');
  });

  it('rounds to 2 decimal places', () => {
    // JavaScript uses "round half away from zero" (0.125 rounds to 0.13)
    expect(formatCost(0.125)).toBe('$0.13');
    expect(formatCost(0.126)).toBe('$0.13');
    expect(formatCost(0.124)).toBe('$0.12');
    expect(formatCost(0.999)).toBe('$1.00');
  });
});

describe('formatDuration', () => {
  it('formats durations under a minute as seconds', () => {
    expect(formatDuration(0)).toBe('0s');
    expect(formatDuration(15000)).toBe('15s');
    expect(formatDuration(59000)).toBe('59s');
  });

  it('formats durations with minutes and seconds', () => {
    expect(formatDuration(60000)).toBe('1m');
    expect(formatDuration(97000)).toBe('1m 37s');
    expect(formatDuration(154000)).toBe('2m 34s');
  });

  it('omits seconds when exactly on the minute', () => {
    expect(formatDuration(60000)).toBe('1m');
    expect(formatDuration(120000)).toBe('2m');
    expect(formatDuration(300000)).toBe('5m');
  });

  it('handles larger durations', () => {
    expect(formatDuration(3600000)).toBe('60m');
    expect(formatDuration(3661000)).toBe('61m 1s');
  });
});
