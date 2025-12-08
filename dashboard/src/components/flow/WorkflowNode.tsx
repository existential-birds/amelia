/**
 * @fileoverview Custom React Flow node for workflow pipeline stages.
 */
import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Possible status values for workflow nodes. */
type NodeStatus = 'completed' | 'active' | 'pending' | 'blocked';

/**
 * Data payload for workflow nodes.
 * @property label - Primary label for the node
 * @property subtitle - Optional secondary text
 * @property status - Current node status
 * @property tokens - Optional token count display
 */
export interface WorkflowNodeData extends Record<string, unknown> {
  label: string;
  subtitle?: string;
  status: NodeStatus;
  tokens?: string;
}

/** Type definition for workflow nodes used in React Flow. */
export type WorkflowNodeType = Node<WorkflowNodeData, 'workflow'>;

/** Style configuration for each node status. */
const statusStyles: Record<NodeStatus, {
  pinClass: string;
  containerClass: string;
  glowClass: string;
}> = {
  completed: {
    pinClass: 'text-status-completed',
    containerClass: 'opacity-100',
    glowClass: '',
  },
  active: {
    pinClass: 'text-primary animate-pulse',
    containerClass: 'opacity-100',
    glowClass: 'drop-shadow-[0_0_12px_var(--primary)]',
  },
  pending: {
    pinClass: 'text-muted-foreground',
    containerClass: 'opacity-50',
    glowClass: '',
  },
  blocked: {
    pinClass: 'text-destructive',
    containerClass: 'opacity-100',
    glowClass: '',
  },
};

/**
 * Renders a workflow stage node with status-based styling.
 *
 * Displays a map pin icon, label, optional subtitle, and token count.
 * Visual appearance changes based on status (completed, active, pending, blocked).
 *
 * @param props - React Flow node props
 * @returns The workflow node UI
 */
function WorkflowNodeComponent({ data }: NodeProps<WorkflowNodeType>) {
  const styles = statusStyles[data.status];
  const ariaLabel = `Workflow stage: ${data.label}${data.subtitle ? ` - ${data.subtitle}` : ''} (${data.status})`;

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      data-status={data.status}
      className={cn(
        'flex flex-col items-center min-w-[100px]',
        styles.containerClass
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!w-0 !h-0 !bg-transparent !border-0 !min-w-0 !min-h-0"
      />

      <div className={cn('rounded-full p-2', styles.glowClass)}>
        <MapPin
          className={cn('lucide-map-pin size-8', styles.pinClass)}
          strokeWidth={2}
        />
      </div>

      <span className="font-heading text-sm font-semibold tracking-wider text-foreground mt-2">
        {data.label}
      </span>

      {data.subtitle && (
        <span className="font-body text-xs text-muted-foreground">
          {data.subtitle}
        </span>
      )}

      {data.tokens && (
        <span className="font-mono text-xs text-muted-foreground mt-1">
          {data.tokens} tokens
        </span>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="!w-0 !h-0 !bg-transparent !border-0 !min-w-0 !min-h-0"
      />
    </div>
  );
}

/** Memoized workflow node component for React Flow. */
export const WorkflowNode = memo(WorkflowNodeComponent);
