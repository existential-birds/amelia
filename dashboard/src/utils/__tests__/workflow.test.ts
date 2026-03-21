import { describe, it, expect } from 'vitest';
import { getActiveWorkflow, getMostRecentCompleted, formatTokens, formatCost, formatDuration } from '../workflow';
import { createMockWorkflowSummary } from '@/__tests__/fixtures';

describe('getActiveWorkflow', () => {
  it('should return running workflow when one exists', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'completed' }),
      createMockWorkflowSummary({ id: '2', status: 'in_progress' }),
      createMockWorkflowSummary({ id: '3', status: 'pending' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should return most recent completed workflow when no running', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
      createMockWorkflowSummary({ id: '2', status: 'completed', started_at: '2025-01-03T00:00:00Z' }),
      createMockWorkflowSummary({ id: '3', status: 'completed', started_at: '2025-01-02T00:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should return null when no workflows exist', () => {
    expect(getActiveWorkflow([])).toBeNull();
  });

  it('should prioritize running over completed', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'completed', started_at: '2025-12-01T00:00:00Z' }),
      createMockWorkflowSummary({ id: '2', status: 'in_progress', started_at: '2025-01-01T00:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should sort completed by started_at descending', () => {
    const workflows = [
      createMockWorkflowSummary({ id: 'oldest', status: 'completed', started_at: '2024-01-01T00:00:00Z' }),
      createMockWorkflowSummary({ id: 'newest', status: 'completed', started_at: '2025-06-01T00:00:00Z' }),
      createMockWorkflowSummary({ id: 'middle', status: 'completed', started_at: '2025-03-01T00:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('newest');
  });

  it('should return blocked workflow when no running exists', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'completed' }),
      createMockWorkflowSummary({ id: '2', status: 'blocked' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should prioritize running over blocked', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'blocked' }),
      createMockWorkflowSummary({ id: '2', status: 'in_progress' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should prioritize blocked over completed', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'completed', started_at: '2025-12-01T00:00:00Z' }),
      createMockWorkflowSummary({ id: '2', status: 'blocked', started_at: '2025-01-01T00:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('2');
  });

  it('should handle null started_at in completed workflows', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'completed', started_at: null }),
      createMockWorkflowSummary({ id: '2', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
      createMockWorkflowSummary({ id: '3', status: 'completed', started_at: null }),
    ];
    // Should not throw, should return one of them
    const result = getActiveWorkflow(workflows);
    expect(result).not.toBeNull();
  });

  it('should return most recently started running workflow when multiple are in progress', () => {
    const workflows = [
      createMockWorkflowSummary({ id: 'oldest-running', status: 'in_progress', started_at: '2025-01-01T05:00:00Z' }),
      createMockWorkflowSummary({ id: 'newest-running', status: 'in_progress', started_at: '2025-01-01T01:00:00Z' }),
      createMockWorkflowSummary({ id: 'middle-running', status: 'in_progress', started_at: '2025-01-01T03:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('oldest-running');
  });

  it('should return most recently started blocked workflow when multiple are blocked', () => {
    const workflows = [
      createMockWorkflowSummary({ id: 'oldest-blocked', status: 'blocked', started_at: '2025-01-01T05:00:00Z' }),
      createMockWorkflowSummary({ id: 'newest-blocked', status: 'blocked', started_at: '2025-01-01T01:00:00Z' }),
      createMockWorkflowSummary({ id: 'middle-blocked', status: 'blocked', started_at: '2025-01-01T03:00:00Z' }),
    ];
    expect(getActiveWorkflow(workflows)?.id).toBe('oldest-blocked');
  });

  it('should work correctly regardless of array order', () => {
    // Test with completed workflows listed first (like in the bug scenario)
    const workflows = [
      createMockWorkflowSummary({ id: 'completed-1', status: 'completed', started_at: '2025-01-01T10:00:00Z' }),
      createMockWorkflowSummary({ id: 'completed-2', status: 'completed', started_at: '2025-01-01T12:00:00Z' }),
      createMockWorkflowSummary({ id: 'running-oldest', status: 'in_progress', started_at: '2025-01-01T03:00:00Z' }),
      createMockWorkflowSummary({ id: 'running-newest', status: 'in_progress', started_at: '2025-01-01T01:00:00Z' }),
      createMockWorkflowSummary({ id: 'blocked', status: 'blocked', started_at: '2025-01-01T02:00:00Z' }),
    ];
    // Should select the most recent running workflow (running-oldest), not the first in array
    expect(getActiveWorkflow(workflows)?.id).toBe('running-oldest');
  });
});

describe('getMostRecentCompleted', () => {
  it('should return the most recently completed workflow', () => {
    const workflows = [
      createMockWorkflowSummary({ id: 'oldest', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
      createMockWorkflowSummary({ id: 'newest', status: 'completed', started_at: '2025-01-03T00:00:00Z' }),
      createMockWorkflowSummary({ id: 'middle', status: 'completed', started_at: '2025-01-02T00:00:00Z' }),
    ];
    expect(getMostRecentCompleted(workflows)?.id).toBe('newest');
  });

  it('should return null when no completed workflows exist', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'in_progress' }),
      createMockWorkflowSummary({ id: '2', status: 'blocked' }),
    ];
    expect(getMostRecentCompleted(workflows)).toBeNull();
  });

  it('should return null for empty array', () => {
    expect(getMostRecentCompleted([])).toBeNull();
  });

  it('should ignore non-completed workflows', () => {
    const workflows = [
      createMockWorkflowSummary({ id: 'completed', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
      createMockWorkflowSummary({ id: 'running', status: 'in_progress', started_at: '2025-01-03T00:00:00Z' }),
      createMockWorkflowSummary({ id: 'failed', status: 'failed', started_at: '2025-01-02T00:00:00Z' }),
    ];
    expect(getMostRecentCompleted(workflows)?.id).toBe('completed');
  });

  it('should handle workflows with null started_at', () => {
    const workflows = [
      createMockWorkflowSummary({ id: '1', status: 'completed', started_at: null }),
      createMockWorkflowSummary({ id: '2', status: 'completed', started_at: '2025-01-01T00:00:00Z' }),
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
  it.each([
    [0, '0'],
    [500, '500'],
    [999, '999'],
    [1000, '1K'],
    [1500, '1.5K'],
    [2000, '2K'],
    [2100, '2.1K'],
    [10000, '10K'],
    [13700, '13.7K'],
    [15200, '15.2K'],
    [100000, '100K'],
  ])('formatTokens(%i) === "%s"', (input, expected) => {
    expect(formatTokens(input)).toBe(expected);
  });
});

describe('formatCost', () => {
  it.each([
    [0, '$0.00'],
    [0.08, '$0.08'],
    [0.42, '$0.42'],
    [1.5, '$1.50'],
    [10, '$10.00'],
    [0.125, '$0.13'],
    [0.126, '$0.13'],
    [0.124, '$0.12'],
    [0.999, '$1.00'],
  ])('formatCost(%s) === "%s"', (input, expected) => {
    expect(formatCost(input)).toBe(expected);
  });
});

describe('formatDuration', () => {
  it.each([
    [0, '0s'],
    [15000, '15s'],
    [59000, '59s'],
    [60000, '1m'],
    [97000, '1m 37s'],
    [120000, '2m'],
    [154000, '2m 34s'],
    [300000, '5m'],
    [3600000, '60m'],
    [3661000, '61m 1s'],
  ])('formatDuration(%i) === "%s"', (input, expected) => {
    expect(formatDuration(input)).toBe(expected);
  });
});
