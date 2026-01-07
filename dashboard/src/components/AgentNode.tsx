import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import type { AgentNodeData } from '../utils/pipeline';

/** Node type for agent nodes in the workflow canvas. */
export type AgentNodeType = Node<AgentNodeData, 'agent'>;

const statusClasses: Record<AgentNodeData['status'], string> = {
  pending: 'opacity-50 border-border bg-card/60',
  active: 'border-primary bg-primary/10 shadow-lg shadow-primary/20',
  completed: 'border-status-completed/40 bg-status-completed/5',
  blocked: 'border-destructive/40 bg-destructive/5',
};

const iconClasses: Record<AgentNodeData['status'], string> = {
  pending: 'text-muted-foreground',
  active: 'text-primary animate-pulse',
  completed: 'text-status-completed',
  blocked: 'text-destructive',
};

export const AgentNode = memo(function AgentNode({ data }: NodeProps<AgentNodeType>) {
  const { agentType, status, iterations, isExpanded } = data;

  return (
    <div
      data-status={status}
      className={cn(
        'w-[180px] rounded-lg border p-3 transition-all',
        statusClasses[status]
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-border" />

      <div className="flex items-center gap-2">
        <MapPin className={cn('h-4 w-4', iconClasses[status])} />
        <span className="font-medium capitalize">{agentType}</span>
        {iterations.length > 1 && (
          <Badge variant="secondary" className="ml-auto text-xs">
            {iterations.length} runs
          </Badge>
        )}
      </div>

      {status === 'active' && (
        <p className="mt-2 text-sm text-muted-foreground">In progress...</p>
      )}

      {isExpanded && iterations.length > 0 && (
        <div className="mt-2 space-y-1 text-xs">
          {iterations.map((iter, idx) => (
            <div key={iter.id} className="flex items-center gap-1">
              <span className="text-muted-foreground">Run {idx + 1}:</span>
              <span className={cn(
                iter.status === 'running' && 'text-primary',
                iter.status === 'completed' && 'text-status-completed',
                iter.status === 'failed' && 'text-destructive'
              )}>
                {iter.status === 'running' ? 'Running...' : iter.status}
              </span>
            </div>
          ))}
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!bg-border" />
    </div>
  );
});
