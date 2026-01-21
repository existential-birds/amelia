// dashboard/src/utils/layout.ts
/**
 * @fileoverview Automatic graph layout using dagre for workflow visualization.
 *
 * Uses dagre to compute node positions based on graph structure with
 * horizontal left-to-right layout optimized for workflow pipelines.
 */
import Dagre from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/react';

/** Fixed node width for layout calculation (matches AgentNode card width). */
export const NODE_WIDTH = 180;

/** Fixed node height for layout calculation (matches AgentNode card height). */
export const NODE_HEIGHT = 128;

/** Horizontal spacing between nodes in the same rank. */
const NODE_SEP = 50;

/** Spacing between ranks (levels) in the graph. */
const RANK_SEP = 100;

/**
 * Positions nodes using dagre automatic graph layout.
 *
 * Creates a directed graph with horizontal (LR) layout and computes
 * optimal positions based on edges. React Flow's fitView will scale
 * and center the result.
 *
 * @param nodes - React Flow nodes to layout
 * @param edges - Edges defining the graph structure
 * @returns Nodes with updated positions computed by dagre
 */
export function getLayoutedElements<T extends Node>(
  nodes: T[],
  edges: Edge[]
): T[] {
  // Handle empty input
  if (nodes.length === 0) {
    return [];
  }

  // Create new dagre graph
  const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));

  // Configure graph for horizontal left-to-right layout
  g.setGraph({
    rankdir: 'LR',
    nodesep: NODE_SEP,
    ranksep: RANK_SEP,
  });

  // Add nodes with fixed dimensions
  nodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  // Add edges to define graph structure
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  // Compute layout
  Dagre.layout(g);

  // Apply computed positions to nodes
  // Note: dagre returns center positions, but React Flow uses top-left positions
  // We adjust by subtracting half width/height to convert from center to top-left
  return nodes.map((node) => {
    const position = g.node(node.id);
    return {
      ...node,
      position: {
        x: position.x - NODE_WIDTH / 2,
        y: position.y - NODE_HEIGHT / 2,
      },
    };
  });
}
