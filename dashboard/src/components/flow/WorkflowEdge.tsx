import { memo } from 'react';
import { getSmoothStepPath, type EdgeProps, EdgeLabelRenderer } from '@xyflow/react';

type EdgeStatus = 'completed' | 'active' | 'pending';

export interface WorkflowEdgeData {
  label: string;
  status: EdgeStatus;
}

function WorkflowEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<WorkflowEdgeData>) {
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
  const strokeOpacity = status === 'pending' ? 0.4 : 1;

  return (
    <>
      <path
        id={id}
        d={edgePath}
        data-status={status}
        fill="none"
        strokeWidth={2}
        strokeLinecap="round"
        style={{ stroke: strokeColor, opacity: strokeOpacity }}
        {...(isDashed && { strokeDasharray: '6 4' })}
      />

      {status === 'active' && (
        <circle r={4} fill={strokeColor}>
          <animateMotion dur="1.5s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}

      {data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="px-2 py-0.5 font-mono text-xs text-muted-foreground bg-background/90 border border-border rounded"
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const WorkflowEdge = memo(WorkflowEdgeComponent);
