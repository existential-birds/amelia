/**
 * @fileoverview React Flow canvas for visualizing workflow pipelines.
 */
import { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { GitBranch, Loader2 } from 'lucide-react';
import { WorkflowNode, type WorkflowNodeType } from '@/components/flow/WorkflowNode';
import { WorkflowEdge, type WorkflowEdgeType } from '@/components/flow/WorkflowEdge';
import { cn } from '@/lib/utils';

/** Possible status values for pipeline nodes. */
type NodeStatus = 'completed' | 'active' | 'pending' | 'blocked';

/** Possible status values for pipeline edges. */
type EdgeStatus = 'completed' | 'active' | 'pending';

/**
 * Represents a node in the workflow pipeline.
 * @property id - Unique node identifier
 * @property label - Display label for the node
 * @property subtitle - Optional secondary text
 * @property status - Current node status
 * @property tokens - Optional token count display
 */
interface PipelineNode {
  id: string;
  label: string;
  subtitle?: string;
  status: NodeStatus;
  tokens?: string;
}

/**
 * Represents an edge connecting two pipeline nodes.
 * @property from - Source node ID
 * @property to - Target node ID
 * @property label - Edge label text
 * @property status - Current edge status
 */
interface PipelineEdge {
  from: string;
  to: string;
  label: string;
  status: EdgeStatus;
}

/**
 * Complete pipeline data structure for the canvas.
 * @property nodes - Array of pipeline nodes
 * @property edges - Array of pipeline edges
 */
interface Pipeline {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

/**
 * Props for the WorkflowCanvas component.
 * @property pipeline - Pipeline data to visualize (optional)
 * @property isLoading - Whether the pipeline is loading
 * @property className - Optional additional CSS classes
 */
interface WorkflowCanvasProps {
  pipeline?: Pipeline;
  isLoading?: boolean;
  className?: string;
}

/** Custom node types for React Flow. */
const nodeTypes = {
  workflow: WorkflowNode,
};

/** Custom edge types for React Flow. */
const edgeTypes = {
  workflow: WorkflowEdge,
};

/**
 * Visualizes a workflow pipeline using React Flow.
 *
 * Converts pipeline data to React Flow format and renders nodes
 * and edges in a non-interactive view. Shows stage progress indicator.
 *
 * Displays three states:
 * 1. Empty state: No pipeline provided
 * 2. Loading state: Pipeline is loading
 * 3. Active state: Pipeline data is available
 *
 * @param props - Component props
 * @returns The workflow canvas visualization
 *
 * @example
 * ```tsx
 * <WorkflowCanvas
 *   pipeline={{
 *     nodes: [{ id: '1', label: 'Plan', status: 'completed' }],
 *     edges: [{ from: '1', to: '2', label: 'approve', status: 'active' }]
 *   }}
 * />
 * ```
 */
export function WorkflowCanvas({ pipeline, isLoading = false, className }: WorkflowCanvasProps) {
  // Convert pipeline data to React Flow format
  const nodes: WorkflowNodeType[] = useMemo(
    () =>
      pipeline?.nodes.map((node, index) => ({
        id: node.id,
        type: 'workflow' as const,
        position: { x: index * 150, y: 80 },
        data: {
          label: node.label,
          subtitle: node.subtitle,
          status: node.status,
          tokens: node.tokens,
        },
        draggable: false,
        selectable: false,
        connectable: false,
      })) ?? [],
    [pipeline?.nodes]
  );

  const edges: WorkflowEdgeType[] = useMemo(
    () =>
      pipeline?.edges.map((edge) => ({
        id: `e-${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        type: 'workflow' as const,
        data: {
          label: edge.label,
          status: edge.status,
        },
      })) ?? [],
    [pipeline?.edges]
  );

  const currentStage = pipeline?.nodes.find((n) => n.status === 'active')?.label || 'Unknown';

  // Empty state - no pipeline selected
  if (!pipeline && !isLoading) {
    return (
      <div
        role="status"
        aria-label="No workflow selected"
        data-slot="workflow-canvas"
        className={cn('h-64 bg-linear-to-b from-card/40 to-background/40 relative overflow-hidden', className)}
        style={{
          backgroundImage: 'radial-gradient(circle, var(--muted-foreground) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          backgroundPosition: '0 0',
          opacity: 0.1,
        }}
      >
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3" style={{ opacity: 1 }}>
          <GitBranch className="h-12 w-12 text-muted-foreground/40" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">Select a workflow to view pipeline</p>
        </div>
      </div>
    );
  }

  // Loading state - workflow selected but loading
  if (isLoading) {
    return (
      <div
        role="status"
        aria-label="Loading pipeline"
        data-slot="workflow-canvas"
        className={cn('h-64 bg-linear-to-b from-card/40 to-background/40 relative overflow-hidden', className)}
        style={{
          backgroundImage: 'radial-gradient(circle, var(--muted-foreground) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          backgroundPosition: '0 0',
          opacity: 0.1,
        }}
      >
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3" style={{ opacity: 1 }}>
          <Loader2 className="h-8 w-8 text-muted-foreground/60 animate-spin" strokeWidth={2} />
          <p className="text-sm text-muted-foreground">Loading pipeline...</p>
        </div>
      </div>
    );
  }

  // Active state - pipeline data available (pipeline is guaranteed defined here)
  const nodeCount = pipeline!.nodes.length;
  return (
    <div
      role="img"
      aria-label={`Workflow pipeline with ${nodeCount} stages. Current stage: ${currentStage}`}
      data-slot="workflow-canvas"
      className={cn('h-40 bg-linear-to-b from-card/40 to-background/40 relative', className)}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.02 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        className="workflow-canvas"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--muted-foreground)"
          style={{ opacity: 0.1 }}
        />
      </ReactFlow>

    </div>
  );
}
