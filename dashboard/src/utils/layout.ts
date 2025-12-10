// dashboard/src/utils/layout.ts
/**
 * @fileoverview Dagre-based layout utility for workflow DAG visualization.
 */
import Dagre from '@dagrejs/dagre';
import type { WorkflowNodeType } from '@/components/flow/WorkflowNode';
import type { WorkflowEdgeType } from '@/components/flow/WorkflowEdge';

/** Fixed node width for layout calculation. */
export const NODE_WIDTH = 160;

/** Fixed node height for layout calculation. */
export const NODE_HEIGHT = 112;

/** Horizontal spacing between nodes in the same rank. */
const NODE_SEP = 60;

/** Vertical spacing between ranks (columns in LR layout). */
const RANK_SEP = 80;

/**
 * Calculates node positions using dagre layout algorithm.
 *
 * Uses left-to-right (LR) direction to create a horizontal DAG flow.
 * Nodes are positioned based on their dependency relationships,
 * with parallel tasks aligned vertically.
 *
 * @param nodes - React Flow nodes to layout
 * @param edges - React Flow edges defining dependencies
 * @param direction - Layout direction: 'LR' (default) or 'TB'
 * @returns Nodes with updated positions
 *
 * @example
 * ```tsx
 * const layoutedNodes = getLayoutedElements(nodes, edges);
 * <ReactFlow nodes={layoutedNodes} edges={edges} />
 * ```
 */
export function getLayoutedElements(
  nodes: WorkflowNodeType[],
  edges: WorkflowEdgeType[],
  direction: 'LR' | 'TB' = 'LR'
): WorkflowNodeType[] {
  if (nodes.length === 0) {
    return [];
  }

  const dagreGraph = new Dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: NODE_SEP,
    ranksep: RANK_SEP,
    marginx: 20,
    marginy: 20,
  });

  // Add nodes with fixed dimensions
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, {
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    });
  });

  // Add edges
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Calculate layout
  Dagre.layout(dagreGraph);

  // Apply calculated positions to nodes
  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);

    // Dagre returns center position; adjust to top-left for React Flow
    const x = nodeWithPosition.x - NODE_WIDTH / 2;
    const y = nodeWithPosition.y - NODE_HEIGHT / 2;

    return {
      ...node,
      position: { x, y },
    };
  });
}
