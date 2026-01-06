/**
 * @fileoverview React Flow canvas for visualizing workflow pipelines.
 *
 * Simplified component that accepts an EventDrivenPipeline and renders
 * agent nodes with status-based styling.
 */
import { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import type { NodeTypes } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { AgentNode } from './AgentNode';
import { getLayoutedElements } from '@/utils/layout';
import type { EventDrivenPipeline } from '@/utils/pipeline';

const nodeTypes: NodeTypes = {
  agent: AgentNode,
};

interface WorkflowCanvasProps {
  pipeline: EventDrivenPipeline;
  className?: string;
}

/**
 * Visualizes a workflow pipeline using React Flow.
 *
 * Displays agent nodes with status-based styling in a horizontal layout.
 * Shows empty state when pipeline has no nodes.
 *
 * @param props - Component props
 * @param props.pipeline - Event-driven pipeline data with nodes and edges
 * @param props.className - Optional additional CSS classes
 * @returns The workflow canvas visualization
 */
export function WorkflowCanvas({ pipeline, className }: WorkflowCanvasProps) {
  // Apply Dagre layout to nodes
  const layoutedNodes = useMemo(() => {
    if (pipeline.nodes.length === 0) return [];
    return getLayoutedElements(pipeline.nodes, pipeline.edges);
  }, [pipeline.nodes, pipeline.edges]);

  const [nodes] = useNodesState(layoutedNodes);
  const [edges] = useEdgesState(pipeline.edges);

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
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background color="var(--border)" gap={16} />
      </ReactFlow>
    </div>
  );
}
