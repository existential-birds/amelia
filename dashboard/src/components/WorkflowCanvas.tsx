/**
 * @fileoverview React Flow canvas for visualizing workflow pipelines.
 *
 * Uses ai-elements Canvas component as base. Accepts an EventDrivenPipeline
 * and renders agent nodes with status-based styling. Read-only canvas with
 * no user interaction for nodes/edges.
 */
import { useEffect, useMemo } from 'react';
import { useReactFlow } from '@xyflow/react';
import type { NodeTypes } from '@xyflow/react';

import { Canvas } from './ai-elements/canvas';
import { AgentNode } from './AgentNode';
import { getLayoutedElements } from '@/utils/layout';
import type { EventDrivenPipeline } from '@/utils/pipeline';

const nodeTypes: NodeTypes = {
  agent: AgentNode,
};

/**
 * Inner component that triggers fitView when the node count changes.
 * Must be rendered inside Canvas to access the React Flow instance.
 */
function FitViewOnChange({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow();

  useEffect(() => {
    fitView({ padding: 0.2 });
  }, [nodeCount, fitView]);

  return null;
}

interface WorkflowCanvasProps {
  pipeline: EventDrivenPipeline;
  className?: string;
}

/**
 * Visualizes a workflow pipeline using ai-elements Canvas.
 *
 * Displays agent nodes with status-based styling in a horizontal layout.
 * Shows empty state when pipeline has no nodes. Read-only canvas with
 * nodesDraggable, nodesConnectable, and elementsSelectable disabled.
 *
 * @param props - Component props
 * @param props.pipeline - Event-driven pipeline data with nodes and edges
 * @param props.className - Optional additional CSS classes
 * @returns The workflow canvas visualization
 */
export function WorkflowCanvas({ pipeline, className }: WorkflowCanvasProps) {
  // Apply Dagre layout to nodes - memoized to avoid recalculating on every render
  const layoutedNodes = useMemo(() => {
    if (pipeline.nodes.length === 0) return [];
    return getLayoutedElements(pipeline.nodes, pipeline.edges);
  }, [pipeline.nodes, pipeline.edges]);

  if (pipeline.nodes.length === 0) {
    return (
      <div
        role="region"
        aria-label="Workflow pipeline visualization"
        className={className}
      >
        <div className="flex h-full items-center justify-center text-muted-foreground">
          No pipeline data available
        </div>
      </div>
    );
  }

  return (
    <div
      role="region"
      aria-label="Workflow pipeline visualization"
      className={className}
    >
      <Canvas
        nodes={layoutedNodes}
        edges={pipeline.edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        selectionOnDrag={false}
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.5}
        maxZoom={1.5}
      >
        <FitViewOnChange nodeCount={layoutedNodes.length} />
      </Canvas>
    </div>
  );
}
