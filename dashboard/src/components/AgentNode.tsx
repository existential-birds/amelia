import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import {
  Compass,
  Code,
  Eye,
  CircleDot,
  ClipboardCheck,
  Hand,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import type { AgentNodeData } from '../utils/pipeline';

/** Node type for agent nodes in the workflow canvas. */
export type AgentNodeType = Node<AgentNodeData, 'agent'>;

/** Display names for node types (converts internal names to user-friendly labels). */
const NODE_DISPLAY_NAMES: Record<string, string> = {
  architect: 'Architect',
  developer: 'Developer',
  reviewer: 'Reviewer',
  plan_validator: 'Plan Validator',
  human_approval: 'Human Approval',
};

/** Get display name for a node type. */
function getNodeDisplayName(agentType: string): string {
  return NODE_DISPLAY_NAMES[agentType] ?? agentType.replace(/_/g, ' ');
}

/** Agent-specific active state styling (border, background, shadow). */
const AGENT_ACTIVE_CLASSES: Record<string, string> = {
  architect: 'border-agent-architect bg-agent-architect/10 shadow-lg shadow-agent-architect/20',
  developer: 'border-agent-developer bg-agent-developer/10 shadow-lg shadow-agent-developer/20',
  reviewer: 'border-agent-reviewer bg-agent-reviewer/10 shadow-lg shadow-agent-reviewer/20',
  plan_validator: 'border-agent-pm bg-agent-pm/10 shadow-lg shadow-agent-pm/20',
  human_approval: 'border-destructive bg-destructive/10 shadow-lg shadow-destructive/20',
};

/** Agent-specific completed state styling (muted version of active colors). */
const AGENT_COMPLETED_CLASSES: Record<string, string> = {
  architect: 'border-agent-architect/40 bg-agent-architect/5',
  developer: 'border-agent-developer/40 bg-agent-developer/5',
  reviewer: 'border-agent-reviewer/40 bg-agent-reviewer/5',
  plan_validator: 'border-agent-pm/40 bg-agent-pm/5',
  human_approval: 'border-destructive/40 bg-destructive/5',
};

/** Agent-specific active icon styling. */
const AGENT_ACTIVE_ICON_CLASSES: Record<string, string> = {
  architect: 'text-agent-architect animate-pulse',
  developer: 'text-agent-developer animate-pulse',
  reviewer: 'text-agent-reviewer animate-pulse',
  plan_validator: 'text-agent-pm animate-pulse',
  human_approval: 'text-destructive animate-pulse',
};

/** Agent-specific completed icon styling (muted version). */
const AGENT_COMPLETED_ICON_CLASSES: Record<string, string> = {
  architect: 'text-agent-architect/70',
  developer: 'text-agent-developer/70',
  reviewer: 'text-agent-reviewer/70',
  plan_validator: 'text-agent-pm/70',
  human_approval: 'text-destructive/70',
};

/** Default active classes for unknown agent types. */
const DEFAULT_ACTIVE_CLASSES = 'border-primary bg-primary/10 shadow-lg shadow-primary/20';
const DEFAULT_ACTIVE_ICON_CLASSES = 'text-primary animate-pulse';
const DEFAULT_COMPLETED_CLASSES = 'border-primary/40 bg-primary/5';
const DEFAULT_COMPLETED_ICON_CLASSES = 'text-primary/70';

/** Agent-specific icons. */
const AGENT_ICONS: Record<string, LucideIcon> = {
  architect: Compass,
  developer: Code,
  reviewer: Eye,
  plan_validator: ClipboardCheck,
  human_approval: Hand,
};

/** Get the icon component for an agent type. */
function getAgentIcon(agentType: string): LucideIcon {
  return AGENT_ICONS[agentType] ?? CircleDot;
}

const baseStatusClasses: Record<AgentNodeData['status'], string> = {
  pending: 'opacity-50 border-border bg-card/60',
  active: '', // Handled dynamically based on agent type
  completed: '', // Handled dynamically based on agent type
  blocked: 'border-destructive/40 bg-destructive/5',
};

const baseIconClasses: Record<AgentNodeData['status'], string> = {
  pending: 'text-muted-foreground',
  active: '', // Handled dynamically based on agent type
  completed: '', // Handled dynamically based on agent type
  blocked: 'text-destructive',
};

/** Get status classes for a node, with agent-specific styling. */
function getStatusClasses(status: AgentNodeData['status'], agentType: string): string {
  if (status === 'active') {
    return AGENT_ACTIVE_CLASSES[agentType] ?? DEFAULT_ACTIVE_CLASSES;
  }
  if (status === 'completed') {
    return AGENT_COMPLETED_CLASSES[agentType] ?? DEFAULT_COMPLETED_CLASSES;
  }
  return baseStatusClasses[status];
}

/** Get icon classes for a node, with agent-specific styling. */
function getIconClasses(status: AgentNodeData['status'], agentType: string): string {
  if (status === 'active') {
    return AGENT_ACTIVE_ICON_CLASSES[agentType] ?? DEFAULT_ACTIVE_ICON_CLASSES;
  }
  if (status === 'completed') {
    return AGENT_COMPLETED_ICON_CLASSES[agentType] ?? DEFAULT_COMPLETED_ICON_CLASSES;
  }
  return baseIconClasses[status];
}

export const AgentNode = memo(function AgentNode({ data }: NodeProps<AgentNodeType>) {
  const { agentType, status, iterations, isExpanded } = data;
  const Icon = getAgentIcon(agentType);

  return (
    <div
      data-status={status}
      className={cn(
        'w-[180px] rounded-lg border p-3 transition-all',
        getStatusClasses(status, agentType)
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-border" />

      <div className="flex items-center gap-2">
        <Icon className={cn('h-4 w-4', getIconClasses(status, agentType))} />
        <span className="font-medium">{getNodeDisplayName(agentType)}</span>
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
