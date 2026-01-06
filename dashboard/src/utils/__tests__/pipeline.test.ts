import { describe, it, expect } from 'vitest';
import { buildPipeline, buildPipelineFromEvents } from '../pipeline';
import type { AgentIteration, AgentNodeData } from '../pipeline';
import type { WorkflowDetail, WorkflowEvent } from '@/types';

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
    total_cost_usd: null,
    total_tokens: null,
    total_duration_ms: null,
    token_usage: null,
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

describe('AgentIteration type', () => {
  it('should have required fields', () => {
    const iteration: AgentIteration = {
      id: 'iter-1',
      startedAt: '2026-01-06T10:00:00Z',
      status: 'running',
    };
    expect(iteration.id).toBe('iter-1');
    expect(iteration.status).toBe('running');
  });

  it('should support optional completedAt and message', () => {
    const iteration: AgentIteration = {
      id: 'iter-2',
      startedAt: '2026-01-06T10:00:00Z',
      completedAt: '2026-01-06T10:05:00Z',
      status: 'completed',
      message: 'Approved',
    };
    expect(iteration.completedAt).toBe('2026-01-06T10:05:00Z');
    expect(iteration.message).toBe('Approved');
  });
});

describe('AgentNodeData type', () => {
  it('should have required fields', () => {
    const nodeData: AgentNodeData = {
      agentType: 'architect',
      status: 'active',
      iterations: [],
      isExpanded: false,
    };
    expect(nodeData.agentType).toBe('architect');
    expect(nodeData.status).toBe('active');
  });
});

describe('buildPipelineFromEvents', () => {
  const makeEvent = (
    agent: string,
    event_type: string,
    sequence: number,
    timestamp: string = '2026-01-06T10:00:00Z'
  ): WorkflowEvent => ({
    id: `evt-${sequence}`,
    workflow_id: 'wf-1',
    sequence,
    timestamp,
    agent,
    event_type: event_type as WorkflowEvent['event_type'],
    message: `${agent} ${event_type}`,
  });

  it('should return empty pipeline for empty events', () => {
    const result = buildPipelineFromEvents([]);
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });

  it('should create node with active status for stage_started without completion', () => {
    const events = [
      makeEvent('architect', 'stage_started', 1),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe('architect');
    expect(result.nodes[0].data.status).toBe('active');
    expect(result.nodes[0].data.iterations).toHaveLength(1);
    expect(result.nodes[0].data.iterations[0].status).toBe('running');
  });

  it('should create node with completed status when stage completes', () => {
    const events = [
      makeEvent('architect', 'stage_started', 1, '2026-01-06T10:00:00Z'),
      makeEvent('architect', 'stage_completed', 2, '2026-01-06T10:05:00Z'),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].data.status).toBe('completed');
    expect(result.nodes[0].data.iterations[0].status).toBe('completed');
    expect(result.nodes[0].data.iterations[0].completedAt).toBe('2026-01-06T10:05:00Z');
  });

  it('should track multiple iterations for same agent', () => {
    const events = [
      makeEvent('developer', 'stage_started', 1, '2026-01-06T10:00:00Z'),
      makeEvent('developer', 'stage_completed', 2, '2026-01-06T10:05:00Z'),
      makeEvent('reviewer', 'stage_started', 3, '2026-01-06T10:05:00Z'),
      makeEvent('reviewer', 'stage_completed', 4, '2026-01-06T10:10:00Z'),
      makeEvent('developer', 'stage_started', 5, '2026-01-06T10:10:00Z'),  // Second iteration
    ];
    const result = buildPipelineFromEvents(events);

    const devNode = result.nodes.find(n => n.id === 'developer');
    expect(devNode?.data.iterations).toHaveLength(2);
    expect(devNode?.data.iterations[0].status).toBe('completed');
    expect(devNode?.data.iterations[1].status).toBe('running');
    expect(devNode?.data.status).toBe('active');  // Currently running
  });

  it('should create edges between adjacent agents in order of first appearance', () => {
    const events = [
      makeEvent('architect', 'stage_started', 1),
      makeEvent('architect', 'stage_completed', 2),
      makeEvent('developer', 'stage_started', 3),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.edges).toHaveLength(1);
    expect(result.edges[0].source).toBe('architect');
    expect(result.edges[0].target).toBe('developer');
  });

  it('should set edge status based on source node completion', () => {
    const events = [
      makeEvent('architect', 'stage_started', 1),
      makeEvent('architect', 'stage_completed', 2),
      makeEvent('developer', 'stage_started', 3),
      makeEvent('developer', 'stage_completed', 4),
      makeEvent('reviewer', 'stage_started', 5),
    ];
    const result = buildPipelineFromEvents(events);

    const archToDevEdge = result.edges.find(e => e.source === 'architect');
    const devToRevEdge = result.edges.find(e => e.source === 'developer');

    expect(archToDevEdge?.data?.status).toBe('completed');
    expect(devToRevEdge?.data?.status).toBe('active');
  });

  it('should handle workflow_failed by marking current agent as blocked', () => {
    const events = [
      makeEvent('developer', 'stage_started', 1),
      makeEvent('system', 'workflow_failed', 2),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.nodes[0].data.status).toBe('blocked');
    expect(result.nodes[0].data.iterations[0].status).toBe('failed');
  });

  it('should create pending nodes for standard pipeline when no events', () => {
    // When called with empty events, should still show the expected pipeline structure
    const result = buildPipelineFromEvents([], { showDefaultPipeline: true });

    expect(result.nodes).toHaveLength(3);
    expect(result.nodes.map(n => n.id)).toEqual(['architect', 'developer', 'reviewer']);
    expect(result.nodes.every(n => n.data.status === 'pending')).toBe(true);
  });
});
