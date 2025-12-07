import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';

type NodeStatus = 'completed' | 'active' | 'pending' | 'blocked';

export interface WorkflowNodeData {
  label: string;
  subtitle?: string;
  status: NodeStatus;
  tokens?: string;
}

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

function WorkflowNodeComponent({ data }: NodeProps<WorkflowNodeData>) {
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
        className="!w-2 !h-2 !bg-muted-foreground !border-0"
      />

      <div className={cn('rounded-full p-2', styles.glowClass)}>
        <MapPin
          className={cn('lucide-map-pin w-8 h-8', styles.pinClass)}
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
        className="!w-2 !h-2 !bg-muted-foreground !border-0"
      />
    </div>
  );
}

export const WorkflowNode = memo(WorkflowNodeComponent);
