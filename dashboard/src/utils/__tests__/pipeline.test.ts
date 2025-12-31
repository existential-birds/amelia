import { describe, it, expect } from 'vitest';
import { buildPipeline } from '../pipeline';
import type { WorkflowDetail } from '@/types';

// Helper to create a minimal workflow detail
function createWorkflowDetail(
  currentStage: string | null,
  status: WorkflowDetail['status'] = 'in_progress'
): WorkflowDetail {
  return {
    id: 'test-id',
    issue_id: 'TEST-1',
    worktree_name: 'test-worktree',
    worktree_path: '/tmp/test-worktree',
    status,
    current_stage: currentStage,
    started_at: '2025-01-01T00:00:00Z',
    completed_at: null,
    failure_reason: null,
    token_usage: {},
    recent_events: [],
    goal: 'Test goal',
    plan_markdown: null,
    plan_path: null,
  };
}

describe('buildPipeline', () => {
  it('should create nodes for all agent stages', () => {
    const workflow = createWorkflowDetail('developer_node');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.nodes).toHaveLength(3);
    expect(result.nodes.map(n => n.id)).toEqual(['architect', 'developer', 'reviewer']);
  });

  it('should label nodes with capitalized stage names', () => {
    const workflow = createWorkflowDetail('architect_node');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.nodes[0]).toMatchObject({
      id: 'architect',
      label: 'Architect',
    });
    expect(result.nodes[1]).toMatchObject({
      id: 'developer',
      label: 'Developer',
    });
    expect(result.nodes[2]).toMatchObject({
      id: 'reviewer',
      label: 'Reviewer',
    });
  });

  it('should create edges between stages', () => {
    const workflow = createWorkflowDetail('developer_node');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.edges).toHaveLength(2);
    // Edge status is based on source stage: architect is completed, developer is active
    expect(result.edges[0]).toMatchObject({
      from: 'architect',
      to: 'developer',
      label: '',
      status: 'completed',
    });
    expect(result.edges[1]).toMatchObject({
      from: 'developer',
      to: 'reviewer',
      label: '',
      status: 'active',
    });
  });

  it('should mark current stage as active', () => {
    const workflow = createWorkflowDetail('developer_node');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.nodes[1]).toMatchObject({
      id: 'developer',
      status: 'active',
      subtitle: 'In progress...',
    });
  });

  it('should mark previous stages as completed', () => {
    const workflow = createWorkflowDetail('reviewer_node');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.nodes[0]?.status).toBe('completed');
    expect(result.nodes[1]?.status).toBe('completed');
    expect(result.nodes[2]?.status).toBe('active');
  });

  it('should mark future stages as pending', () => {
    const workflow = createWorkflowDetail('architect_node');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.nodes[0]?.status).toBe('active');
    expect(result.nodes[1]?.status).toBe('pending');
    expect(result.nodes[2]?.status).toBe('pending');
  });

  it('should handle null current_stage', () => {
    const workflow = createWorkflowDetail(null);
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.nodes).toHaveLength(3);
    // All nodes should be pending when no stage is active
    expect(result.nodes[0]?.status).toBe('pending');
    expect(result.nodes[1]?.status).toBe('pending');
    expect(result.nodes[2]?.status).toBe('pending');
  });

  it('should mark blocked workflow stage as blocked', () => {
    const workflow = createWorkflowDetail('developer_node', 'blocked');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.nodes[1]).toMatchObject({
      id: 'developer',
      status: 'blocked',
    });
  });

  it('should handle human_approval_node as architect stage', () => {
    const workflow = createWorkflowDetail('human_approval_node');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    // human_approval_node should map to architect stage
    expect(result.nodes[0]?.status).toBe('active');
    expect(result.nodes[1]?.status).toBe('pending');
    expect(result.nodes[2]?.status).toBe('pending');
  });

  it('should mark all stages completed for completed workflow', () => {
    const workflow = createWorkflowDetail('reviewer_node', 'completed');
    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Expected result');
    expect(result.nodes[0]?.status).toBe('completed');
    expect(result.nodes[1]?.status).toBe('completed');
    expect(result.nodes[2]?.status).toBe('completed');
  });

  describe('edge status computation', () => {
    it('marks edges as completed when source stage is completed', () => {
      const workflow = createWorkflowDetail('reviewer_node');
      const result = buildPipeline(workflow);

      expect(result).not.toBeNull();
      if (!result) throw new Error('Expected result');
      // Both architect and developer are completed when reviewer is active
      expect(result.edges[0]).toMatchObject({
        from: 'architect',
        to: 'developer',
        status: 'completed',
      });
      expect(result.edges[1]).toMatchObject({
        from: 'developer',
        to: 'reviewer',
        status: 'completed',
      });
    });

    it('marks edges based on source stage status', () => {
      const workflow = createWorkflowDetail('developer_node');
      const result = buildPipeline(workflow);

      expect(result).not.toBeNull();
      if (!result) throw new Error('Expected result');
      // Architect is completed, developer is active
      expect(result.edges[0]).toMatchObject({
        from: 'architect',
        to: 'developer',
        status: 'completed',
      });
      expect(result.edges[1]).toMatchObject({
        from: 'developer',
        to: 'reviewer',
        status: 'active',
      });
    });

    it('marks edges as pending when source stage is pending', () => {
      const workflow = createWorkflowDetail('architect_node');
      const result = buildPipeline(workflow);

      expect(result).not.toBeNull();
      if (!result) throw new Error('Expected result');
      // Architect is active, developer and reviewer are pending
      expect(result.edges[0]).toMatchObject({
        from: 'architect',
        to: 'developer',
        status: 'active',
      });
      expect(result.edges[1]).toMatchObject({
        from: 'developer',
        to: 'reviewer',
        status: 'pending',
      });
    });
  });
});
