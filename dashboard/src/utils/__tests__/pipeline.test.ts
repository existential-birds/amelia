import { describe, it, expect } from 'vitest';
import { buildPipelineFromEvents } from '../pipeline';
import type { AgentIteration, AgentNodeData } from '../pipeline';
import type { WorkflowEvent } from '@/types';

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
  /**
   * Create a stage event with proper structure.
   * Stage events have agent: "system" and data.stage contains the actual stage name.
   */
  const makeStageEvent = (
    stage: string,
    event_type: 'stage_started' | 'stage_completed',
    sequence: number,
    timestamp: string = '2026-01-06T10:00:00Z'
  ): WorkflowEvent => ({
    id: `evt-${sequence}`,
    workflow_id: 'wf-1',
    sequence,
    timestamp,
    agent: 'system',
    event_type,
    message: `${stage} ${event_type}`,
    data: { stage: `${stage}_node` },
  });

  /**
   * Create a non-stage event (e.g., workflow_failed).
   */
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
      makeStageEvent('architect', 'stage_started', 1),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.nodes).toHaveLength(1);
    const node = result.nodes[0]!;
    expect(node.id).toBe('architect');
    expect(node.data.status).toBe('active');
    expect(node.data.iterations).toHaveLength(1);
    expect(node.data.iterations[0]!.status).toBe('running');
  });

  it('should create node with completed status when stage completes', () => {
    const events = [
      makeStageEvent('architect', 'stage_started', 1, '2026-01-06T10:00:00Z'),
      makeStageEvent('architect', 'stage_completed', 2, '2026-01-06T10:05:00Z'),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.nodes).toHaveLength(1);
    const node = result.nodes[0]!;
    const iteration = node.data.iterations[0]!;
    expect(node.data.status).toBe('completed');
    expect(iteration.status).toBe('completed');
    expect(iteration.completedAt).toBe('2026-01-06T10:05:00Z');
  });

  it('should track multiple iterations for same agent', () => {
    const events = [
      makeStageEvent('developer', 'stage_started', 1, '2026-01-06T10:00:00Z'),
      makeStageEvent('developer', 'stage_completed', 2, '2026-01-06T10:05:00Z'),
      makeStageEvent('reviewer', 'stage_started', 3, '2026-01-06T10:05:00Z'),
      makeStageEvent('reviewer', 'stage_completed', 4, '2026-01-06T10:10:00Z'),
      makeStageEvent('developer', 'stage_started', 5, '2026-01-06T10:10:00Z'),  // Second iteration
    ];
    const result = buildPipelineFromEvents(events);

    const devNode = result.nodes.find(n => n.id === 'developer')!;
    expect(devNode.data.iterations).toHaveLength(2);
    expect(devNode.data.iterations[0]!.status).toBe('completed');
    expect(devNode.data.iterations[1]!.status).toBe('running');
    expect(devNode.data.status).toBe('active');  // Currently running
  });

  it('should create edges between adjacent agents in order of first appearance', () => {
    const events = [
      makeStageEvent('architect', 'stage_started', 1),
      makeStageEvent('architect', 'stage_completed', 2),
      makeStageEvent('developer', 'stage_started', 3),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.edges).toHaveLength(1);
    const edge = result.edges[0]!;
    expect(edge.source).toBe('architect');
    expect(edge.target).toBe('developer');
  });

  it('should set edge status based on source node completion', () => {
    const events = [
      makeStageEvent('architect', 'stage_started', 1),
      makeStageEvent('architect', 'stage_completed', 2),
      makeStageEvent('developer', 'stage_started', 3),
      makeStageEvent('developer', 'stage_completed', 4),
      makeStageEvent('reviewer', 'stage_started', 5),
    ];
    const result = buildPipelineFromEvents(events);

    const archToDevEdge = result.edges.find(e => e.source === 'architect');
    const devToRevEdge = result.edges.find(e => e.source === 'developer');

    expect(archToDevEdge?.data?.status).toBe('completed');
    expect(devToRevEdge?.data?.status).toBe('active');
  });

  it('should handle workflow_failed by marking current agent as blocked', () => {
    const events = [
      makeStageEvent('developer', 'stage_started', 1),
      makeEvent('system', 'workflow_failed', 2),
    ];
    const result = buildPipelineFromEvents(events);

    const node = result.nodes[0]!;
    expect(node.data.status).toBe('blocked');
    expect(node.data.iterations[0]!.status).toBe('failed');
  });

  it('should create pending nodes for standard pipeline when no events', () => {
    // When called with empty events, should still show the expected pipeline structure
    const result = buildPipelineFromEvents([], { showDefaultPipeline: true });

    expect(result.nodes).toHaveLength(3);
    expect(result.nodes.map(n => n.id)).toEqual(['architect', 'developer', 'reviewer']);
    expect(result.nodes.every(n => n.data.status === 'pending')).toBe(true);
  });

  describe('extractAgentFromStageEvent', () => {
    it('should extract agent name from data.stage with _node suffix', () => {
      const events = [
        makeStageEvent('architect', 'stage_started', 1),
      ];
      const result = buildPipelineFromEvents(events);

      // Verify the agent name was extracted correctly
      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0]!.id).toBe('architect');
      expect(result.nodes[0]!.data.agentType).toBe('architect');
    });

    it('should handle stage names without _node suffix', () => {
      // Create an event with data.stage but no _node suffix
      const event: WorkflowEvent = {
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        timestamp: '2026-01-06T10:00:00Z',
        agent: 'system',
        event_type: 'stage_started',
        message: 'test',
        data: { stage: 'custom_agent' },
      };
      const result = buildPipelineFromEvents([event]);

      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0]!.id).toBe('custom_agent');
    });

    it('should fallback to event.agent when data.stage is missing', () => {
      // Create an event without data.stage
      const event: WorkflowEvent = {
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        timestamp: '2026-01-06T10:00:00Z',
        agent: 'fallback_agent',
        event_type: 'stage_started',
        message: 'test',
      };
      const result = buildPipelineFromEvents([event]);

      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0]!.id).toBe('fallback_agent');
    });

    it('should handle all three standard agents from events with data.stage', () => {
      const events = [
        makeStageEvent('architect', 'stage_started', 1),
        makeStageEvent('architect', 'stage_completed', 2),
        makeStageEvent('developer', 'stage_started', 3),
        makeStageEvent('developer', 'stage_completed', 4),
        makeStageEvent('reviewer', 'stage_started', 5),
        makeStageEvent('reviewer', 'stage_completed', 6),
      ];
      const result = buildPipelineFromEvents(events);

      expect(result.nodes).toHaveLength(3);
      expect(result.nodes.map(n => n.id)).toEqual(['architect', 'developer', 'reviewer']);
    });

    it('should correctly match stage_started and stage_completed events for same agent', () => {
      // Both events have agent: "system" but data.stage should match them
      const events: WorkflowEvent[] = [
        {
          id: 'evt-1',
          workflow_id: 'wf-1',
          sequence: 1,
          timestamp: '2026-01-06T10:00:00Z',
          agent: 'system',
          event_type: 'stage_started',
          message: 'test',
          data: { stage: 'developer_node' },
        },
        {
          id: 'evt-2',
          workflow_id: 'wf-1',
          sequence: 2,
          timestamp: '2026-01-06T10:05:00Z',
          agent: 'system',
          event_type: 'stage_completed',
          message: 'test',
          data: { stage: 'developer_node' },
        },
      ];
      const result = buildPipelineFromEvents(events);

      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0]!.id).toBe('developer');
      expect(result.nodes[0]!.data.status).toBe('completed');
      expect(result.nodes[0]!.data.iterations[0]!.status).toBe('completed');
      expect(result.nodes[0]!.data.iterations[0]!.completedAt).toBe('2026-01-06T10:05:00Z');
    });
  });
});
