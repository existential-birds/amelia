/**
 * @fileoverview Custom React Flow edge for workflow pipeline connections.
 */
import { memo } from 'react';
import { getSmoothStepPath, EdgeLabelRenderer, type EdgeProps, type Edge } from '@xyflow/react';

/** Possible status values for workflow edges. */
type EdgeStatus = 'completed' | 'active' | 'pending';

/**
 * Data payload for workflow edges.
 * @property label - Edge label text
 * @property status - Current edge status
 */
export interface WorkflowEdgeData extends Record<string, unknown> {
  label: string;
  status: EdgeStatus;
}

/** Type definition for workflow edges used in React Flow. */
export type WorkflowEdgeType = Edge<WorkflowEdgeData, 'workflow'>;

/**
 * Renders a workflow connection edge with status-based styling.
 *
 * Shows smooth step path with animated dot for active status,
 * dashed lines for non-completed states, and optional label.
 *
 * @param props - React Flow edge props
 * @returns The workflow edge SVG elements
 */
function WorkflowEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<WorkflowEdgeType>) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
  });

  const status = data?.status || 'pending';

  const strokeColor = {
    completed: 'var(--status-completed)',
    active: 'var(--primary)',
    pending: 'var(--muted-foreground)',
  }[status];

  const isDashed = status !== 'completed';
  const strokeOpacity = status === 'pending' ? 0.6 : 1;

  return (
    <>
      <path
        id={id}
        d={edgePath}
        data-status={status}
        data-slot="workflow-edge"
        fill="none"
        strokeWidth={2.5}
        strokeLinecap="round"
        style={{ stroke: strokeColor, opacity: strokeOpacity }}
        {...(isDashed && { strokeDasharray: '8 4' })}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan text-xs font-mono bg-background px-1 rounded border border-border"
            data-status={status}
          >
            <span style={{ color: strokeColor, opacity: strokeOpacity }}>
              {data.label}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

/** Memoized workflow edge component for React Flow. */
export const WorkflowEdge = memo(WorkflowEdgeComponent);
