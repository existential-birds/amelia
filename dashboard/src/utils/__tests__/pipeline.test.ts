import { describe, it, expect } from 'vitest';
import { buildPipeline } from '../pipeline';
import type { WorkflowDetail, TaskDAG, TaskNode } from '@/types';

// Helper to create a minimal workflow detail
function createWorkflowDetail(plan: TaskDAG | null): WorkflowDetail {
  return {
    id: 'test-id',
    issue_id: 'TEST-1',
    worktree_name: 'test-worktree',
    worktree_path: '/tmp/test-worktree',
    status: 'in_progress',
    current_stage: 'developer',
    started_at: '2025-01-01T00:00:00Z',
    completed_at: null,
    failure_reason: null,
    plan,
    token_usage: {},
    recent_events: [],
  };
}

function createTask(overrides: Partial<TaskNode> = {}): TaskNode {
  return {
    id: 'task-1',
    description: 'Test task',
    status: 'pending',
    dependencies: [],
    ...overrides,
  };
}

describe('buildPipeline', () => {
  it('should convert workflow detail to pipeline nodes', () => {
    const workflow = createWorkflowDetail({
      tasks: [
        createTask({
          id: 't1',
          description: 'Plan the architecture',
          status: 'completed',
          started_at: '2025-01-01T00:00:00Z',
          completed_at: '2025-01-01T00:01:23Z', // 1m 23s duration
        }),
        createTask({ id: 't2', description: 'Write the code', status: 'in_progress' }),
      ],
      execution_order: ['t1', 't2'],
    });

    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    expect(result!.nodes).toHaveLength(2);
    expect(result!.nodes[0]).toEqual({
      id: 't1',
      label: 'Plan the architectu…', // truncated to 20 chars
      subtitle: '1m 23s',
      status: 'completed',
      tokens: undefined,
    });
    expect(result!.nodes[1]).toEqual({
      id: 't2',
      label: 'Write the code', // under 20 chars, no truncation
      subtitle: 'Running...',
      status: 'active',
      tokens: undefined,
    });
  });

  it('should create edges between sequential stages', () => {
    const workflow = createWorkflowDetail({
      tasks: [
        createTask({ id: 't1', status: 'pending', dependencies: [] }),
        createTask({ id: 't2', status: 'pending', dependencies: ['t1'] }),
        createTask({ id: 't3', status: 'pending', dependencies: ['t2'] }),
      ],
      execution_order: ['t1', 't2', 't3'],
    });

    const result = buildPipeline(workflow);

    expect(result!.edges).toHaveLength(2);
    expect(result!.edges).toContainEqual({
      from: 't1',
      to: 't2',
      label: '',
      status: 'pending',
    });
    expect(result!.edges).toContainEqual({
      from: 't2',
      to: 't3',
      label: '',
      status: 'pending',
    });
  });

  it('should mark current stage as active', () => {
    const workflow = createWorkflowDetail({
      tasks: [
        createTask({ id: 't1', status: 'in_progress' }),
      ],
      execution_order: ['t1'],
    });

    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Result should not be null');

    expect(result!.nodes[0]!.status).toBe('active');
  });

  it('should handle empty stages array', () => {
    const workflow = createWorkflowDetail({ tasks: [], execution_order: [] });

    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    expect(result!.nodes).toHaveLength(0);
    expect(result!.edges).toHaveLength(0);
  });

  it('should handle workflow detail with null plan', () => {
    const workflow = createWorkflowDetail(null);

    const result = buildPipeline(workflow);

    expect(result).toBeNull();
  });

  it('should handle stages with no dependencies', () => {
    const workflow = createWorkflowDetail({
      tasks: [
        createTask({ id: 't1', dependencies: [] }),
        createTask({ id: 't2', dependencies: [] }),
      ],
      execution_order: ['t1', 't2'],
    });

    const result = buildPipeline(workflow);

    expect(result!.edges).toHaveLength(0);
  });

  it('should filter out edges referencing non-existent tasks', () => {
    const workflow = createWorkflowDetail({
      tasks: [
        createTask({ id: 't1', status: 'pending', dependencies: ['non-existent'] }),
        createTask({ id: 't2', status: 'pending', dependencies: ['t1'] }),
      ],
      execution_order: ['t1', 't2'],
    });

    const result = buildPipeline(workflow);

    // Only t1 -> t2 edge should exist, not non-existent -> t1
    expect(result!.edges).toHaveLength(1);
    expect(result!.edges[0]).toEqual({
      from: 't1',
      to: 't2',
      label: '',
      status: 'pending',
    });
  });

  it('should map failed status to blocked', () => {
    const workflow = createWorkflowDetail({
      tasks: [
        createTask({ id: 't1', status: 'failed' }),
      ],
      execution_order: ['t1'],
    });

    const result = buildPipeline(workflow);

    expect(result).not.toBeNull();
    if (!result) throw new Error('Result should not be null');

    expect(result!.nodes[0]!.status).toBe('blocked');
  });

  describe('edge status computation', () => {
    it.each([
      { targetStatus: 'completed' as const, expectedEdgeStatus: 'completed' },
      { targetStatus: 'in_progress' as const, expectedEdgeStatus: 'active' },
      { targetStatus: 'pending' as const, expectedEdgeStatus: 'pending' },
      { targetStatus: 'failed' as const, expectedEdgeStatus: 'pending' },
    ])('marks edge as $expectedEdgeStatus when target task is $targetStatus', ({ targetStatus, expectedEdgeStatus }) => {
      const workflow = createWorkflowDetail({
        tasks: [
          createTask({ id: 't1', status: 'completed' }),
          createTask({ id: 't2', status: targetStatus, dependencies: ['t1'] }),
        ],
        execution_order: ['t1', 't2'],
      });

      const result = buildPipeline(workflow);

      expect(result!.edges).toHaveLength(1);
      expect(result!.edges[0]).toEqual({
        from: 't1',
        to: 't2',
        label: '',
        status: expectedEdgeStatus,
      });
    });

    it('computes edge status independently for multiple edges', () => {
      const workflow = createWorkflowDetail({
        tasks: [
          createTask({ id: 't1', status: 'completed' }),
          createTask({ id: 't2', status: 'completed', dependencies: ['t1'] }),
          createTask({ id: 't3', status: 'in_progress', dependencies: ['t2'] }),
          createTask({ id: 't4', status: 'pending', dependencies: ['t3'] }),
        ],
        execution_order: ['t1', 't2', 't3', 't4'],
      });

      const result = buildPipeline(workflow);

      expect(result!.edges).toHaveLength(3);
      expect(result!.edges.find(e => e.from === 't1' && e.to === 't2')).toMatchObject({ status: 'completed' });
      expect(result!.edges.find(e => e.from === 't2' && e.to === 't3')).toMatchObject({ status: 'active' });
      expect(result!.edges.find(e => e.from === 't3' && e.to === 't4')).toMatchObject({ status: 'pending' });
    });
  });
});
