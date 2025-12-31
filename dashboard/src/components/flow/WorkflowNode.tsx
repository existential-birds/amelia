/**
 * @fileoverview Custom React Flow node for workflow pipeline stages.
 */
import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { NODE_WIDTH, NODE_HEIGHT } from '@/utils/layout';

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

/**
 * Style properties for node status.
 * @property pinClass - CSS classes for the map pin icon
 * @property containerClass - CSS classes for the container opacity
 * @property glowClass - CSS classes for glow effects
 * @property borderClass - CSS classes for border styling
 * @property backgroundClass - CSS classes for background color
 * @property shadowClass - CSS classes for shadow effects
 */
type StatusStyle = {
  pinClass: string;
  containerClass: string;
  glowClass: string;
  borderClass: string;
  backgroundClass: string;
  shadowClass: string;
};

/**
 * Style configuration for each node status.
 * Maps each status to its visual appearance (colors, animations, shadows).
 */
const statusStyles: Record<NodeStatus, StatusStyle> = {
  completed: {
    pinClass: 'text-status-completed',
    containerClass: 'opacity-100',
    glowClass: '',
    borderClass: 'border-status-completed/40',
    backgroundClass: 'bg-status-completed/5',
    shadowClass: 'shadow-md',
  },
  active: {
    pinClass: 'text-primary animate-pulse',
    containerClass: 'opacity-100',
    glowClass: 'drop-shadow-[0_0_12px_var(--primary)]',
    borderClass: 'border-primary/60',
    backgroundClass: 'bg-primary/10',
    shadowClass: 'shadow-lg shadow-primary/20',
  },
  pending: {
    pinClass: 'text-muted-foreground',
    containerClass: 'opacity-50',
    glowClass: '',
    borderClass: 'border-border',
    backgroundClass: 'bg-card/60',
    shadowClass: 'shadow-sm',
  },
  blocked: {
    pinClass: 'text-destructive',
    containerClass: 'opacity-100',
    glowClass: '',
    borderClass: 'border-destructive/40',
    backgroundClass: 'bg-destructive/5',
    shadowClass: 'shadow-md',
  },
};

/**
 * Renders a workflow stage node with status-based styling.
 *
 * Displays a map pin icon, label, optional subtitle, and token count.
 * Visual appearance changes based on status (completed, active, pending, blocked).
 * Includes React Flow handles for connecting edges.
 *
 * @param props - React Flow node props containing WorkflowNodeData
 * @returns The workflow node UI
 */
function WorkflowNodeComponent({ data }: NodeProps<WorkflowNodeType>) {
  const styles = statusStyles[data.status];
  const ariaLabel = `Workflow stage: ${data.label}${data.subtitle ? ` - ${data.subtitle}` : ''} (${data.status})`;

  return (
    <Card
      data-testid="workflow-node-card"
      data-slot="workflow-node"
      data-status={data.status}
      role="img"
      aria-label={ariaLabel}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
      className={cn(
        'relative rounded-md transition-all duration-200 overflow-hidden',
        styles.containerClass,
        styles.borderClass,
        styles.backgroundClass,
        styles.shadowClass
      )}
    >
      <CardContent className="flex flex-col items-center p-4">
        <div className={cn('rounded-full p-2', styles.glowClass)}>
          <MapPin
            className={cn('lucide-map-pin size-8', styles.pinClass)}
            strokeWidth={2}
          />
        </div>

        <span className={cn(
          "font-heading text-sm font-semibold tracking-wider mt-2 text-center",
          data.status === 'active' ? 'text-primary' : 'text-foreground'
        )}>
          {data.label}
        </span>

        {data.subtitle && (
          <span className="font-body text-xs text-muted-foreground mt-0.5 text-center">
            {data.subtitle}
          </span>
        )}

        {data.tokens && (
          <span className={cn(
            "font-mono text-xs mt-1",
            data.status === 'active' ? 'text-primary' : 'text-muted-foreground'
          )}>
            {data.tokens} tokens
          </span>
        )}
      </CardContent>

      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </Card>
  );
}

/** Memoized workflow node component for React Flow. */
export const WorkflowNode = memo(WorkflowNodeComponent);
