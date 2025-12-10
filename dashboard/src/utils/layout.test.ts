// dashboard/src/utils/layout.test.ts
import { describe, it, expect } from 'vitest';
import { getLayoutedElements, NODE_WIDTH, NODE_HEIGHT } from './layout';
import type { WorkflowNodeType } from '@/components/flow/WorkflowNode';
import type { WorkflowEdgeType } from '@/components/flow/WorkflowEdge';

describe('getLayoutedElements', () => {
  it('returns empty array for empty input', () => {
    const result = getLayoutedElements([], []);
    expect(result).toEqual([]);
  });

  it('positions a single node at origin area', () => {
    const nodes: WorkflowNodeType[] = [
      {
        id: 'task-1',
        type: 'workflow',
        position: { x: 0, y: 0 },
        data: { label: 'Task 1', status: 'pending' },
      },
    ];
    const edges: WorkflowEdgeType[] = [];

    const result = getLayoutedElements(nodes, edges);

    expect(result).toHaveLength(1);
    const node = result[0];
    expect(node).toBeDefined();
    expect(node.id).toBe('task-1');
    // Position should be set by dagre (not exactly 0,0)
    expect(typeof node.position.x).toBe('number');
    expect(typeof node.position.y).toBe('number');
  });

  it('positions dependent nodes in sequence (LR direction)', () => {
    const nodes: WorkflowNodeType[] = [
      {
        id: 'task-1',
        type: 'workflow',
        position: { x: 0, y: 0 },
        data: { label: 'First', status: 'completed' },
      },
      {
        id: 'task-2',
        type: 'workflow',
        position: { x: 0, y: 0 },
        data: { label: 'Second', status: 'pending' },
      },
    ];
    const edges: WorkflowEdgeType[] = [
      {
        id: 'e-task-1-task-2',
        source: 'task-1',
        target: 'task-2',
        type: 'workflow',
        data: { label: '', status: 'completed' },
      },
    ];

    const result = getLayoutedElements(nodes, edges);

    expect(result).toHaveLength(2);
    const first = result.find((n) => n.id === 'task-1')!;
    const second = result.find((n) => n.id === 'task-2')!;
    // In LR layout, second should be to the right of first
    expect(second.position.x).toBeGreaterThan(first.position.x);
  });

  it('positions parallel nodes vertically', () => {
    // task-1 -> task-2a, task-2b (fan-out)
    const nodes: WorkflowNodeType[] = [
      {
        id: 'task-1',
        type: 'workflow',
        position: { x: 0, y: 0 },
        data: { label: 'Start', status: 'completed' },
      },
      {
        id: 'task-2a',
        type: 'workflow',
        position: { x: 0, y: 0 },
        data: { label: 'Parallel A', status: 'pending' },
      },
      {
        id: 'task-2b',
        type: 'workflow',
        position: { x: 0, y: 0 },
        data: { label: 'Parallel B', status: 'pending' },
      },
    ];
    const edges: WorkflowEdgeType[] = [
      {
        id: 'e-1-2a',
        source: 'task-1',
        target: 'task-2a',
        type: 'workflow',
        data: { label: '', status: 'pending' },
      },
      {
        id: 'e-1-2b',
        source: 'task-1',
        target: 'task-2b',
        type: 'workflow',
        data: { label: '', status: 'pending' },
      },
    ];

    const result = getLayoutedElements(nodes, edges);

    const parallelA = result.find((n) => n.id === 'task-2a')!;
    const parallelB = result.find((n) => n.id === 'task-2b')!;
    // Parallel nodes should be at same x (same rank) but different y
    expect(parallelA.position.x).toBeCloseTo(parallelB.position.x, 0);
    expect(parallelA.position.y).not.toBe(parallelB.position.y);
  });

  it('exports NODE_WIDTH and NODE_HEIGHT constants', () => {
    expect(NODE_WIDTH).toBeGreaterThan(0);
    expect(NODE_HEIGHT).toBeGreaterThan(0);
  });

  it('preserves node data and type', () => {
    const nodes: WorkflowNodeType[] = [
      {
        id: 'task-1',
        type: 'workflow',
        position: { x: 0, y: 0 },
        data: { label: 'Test', subtitle: 'Running...', status: 'active', tokens: '1.2k' },
      },
    ];

    const result = getLayoutedElements(nodes, []);

    expect(result).toHaveLength(1);
    const node = result[0];
    expect(node.type).toBe('workflow');
    expect(node.data).toEqual({
      label: 'Test',
      subtitle: 'Running...',
      status: 'active',
      tokens: '1.2k',
    });
  });
});
