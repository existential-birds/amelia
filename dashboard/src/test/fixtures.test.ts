import { describe, it, expect } from 'vitest';
import { mockWorkflowSummaries, mockWorkflowDetail } from './fixtures';

describe('Test Fixtures', () => {
  it('should export mockWorkflowSummaries array', () => {
    expect(mockWorkflowSummaries).toBeDefined();
    expect(Array.isArray(mockWorkflowSummaries)).toBe(true);
    expect(mockWorkflowSummaries.length).toBeGreaterThan(0);
  });

  it('should export mockWorkflowDetail object', () => {
    expect(mockWorkflowDetail).toBeDefined();
    expect(mockWorkflowDetail.id).toBeDefined();
    expect(mockWorkflowDetail.issue_id).toBeDefined();
  });

  it('mockWorkflowSummaries should have required fields', () => {
    const summary = mockWorkflowSummaries[0];
    expect(summary.id).toBeDefined();
    expect(summary.status).toBeDefined();
    expect(summary.issue_id).toBeDefined();
    expect(summary.worktree_name).toBeDefined();
  });

  it('mockWorkflowDetail should have all required fields', () => {
    expect(mockWorkflowDetail.id).toBeDefined();
    expect(mockWorkflowDetail.status).toBeDefined();
    expect(mockWorkflowDetail.issue_id).toBeDefined();
    expect(mockWorkflowDetail.plan).toBeDefined();
    expect(mockWorkflowDetail.recent_events).toBeDefined();
  });
});
