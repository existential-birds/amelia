// dashboard/src/utils/layout.test.ts
import { describe, it, expect } from 'vitest';
import { getLayoutedElements } from './layout';
import type { Node, Edge } from '@xyflow/react';

/** Test node data type for layout tests. */
interface TestNodeData extends Record<string, unknown> {
  label: string;
  status: 'completed' | 'active' | 'pending';
}

/** Test node type for layout tests. */
type TestNode = Node<TestNodeData>;

describe('getLayoutedElements', () => {
  const mockNodes: TestNode[] = [
    { id: '1', type: 'test', position: { x: 0, y: 0 }, data: { label: 'A', status: 'completed' } },
    { id: '2', type: 'test', position: { x: 0, y: 0 }, data: { label: 'B', status: 'active' } },
    { id: '3', type: 'test', position: { x: 0, y: 0 }, data: { label: 'C', status: 'pending' } },
  ];
  const mockEdges: Edge[] = [
    { id: 'e1-2', source: '1', target: '2' },
    { id: 'e2-3', source: '2', target: '3' },
  ];

  it('positions nodes using dagre layout', () => {
    const result = getLayoutedElements(mockNodes, mockEdges);

    // All nodes should have positions
    expect(result[0]?.position.x).toBeGreaterThanOrEqual(0);
    expect(result[0]?.position.y).toBeGreaterThanOrEqual(0);
    expect(result[1]?.position.x).toBeGreaterThanOrEqual(0);
    expect(result[1]?.position.y).toBeGreaterThanOrEqual(0);
    expect(result[2]?.position.x).toBeGreaterThanOrEqual(0);
    expect(result[2]?.position.y).toBeGreaterThanOrEqual(0);

    // Nodes should be positioned left-to-right (increasing x coordinates)
    expect(result[1]?.position.x).toBeGreaterThan(result[0]?.position.x ?? 0);
    expect(result[2]?.position.x).toBeGreaterThan(result[1]?.position.x ?? 0);
  });

  it('returns empty array for empty input', () => {
    const result = getLayoutedElements([], []);
    expect(result).toEqual([]);
  });

  it('preserves node data and type', () => {
    const result = getLayoutedElements(mockNodes, mockEdges);
    expect(result[0]?.data.label).toBe('A');
    expect(result[0]?.type).toBe('test');
  });

  it('uses horizontal left-to-right layout', () => {
    const result = getLayoutedElements(mockNodes, mockEdges);

    // For a linear pipeline (1 -> 2 -> 3), horizontal layout means
    // nodes are arranged left to right with similar Y coordinates
    const yValues = result.map(n => n.position.y);
    const maxYDiff = Math.max(...yValues) - Math.min(...yValues);

    // Y difference should be minimal for horizontal layout
    // (allowing some variation from dagre's centering logic)
    expect(maxYDiff).toBeLessThan(50);
  });

  it('handles nodes with no edges', () => {
    const result = getLayoutedElements(mockNodes, []);

    // Should still position all nodes
    expect(result).toHaveLength(3);
    expect(result[0]?.position.x).toBeGreaterThanOrEqual(0);
    expect(result[1]?.position.x).toBeGreaterThanOrEqual(0);
    expect(result[2]?.position.x).toBeGreaterThanOrEqual(0);
  });
});
