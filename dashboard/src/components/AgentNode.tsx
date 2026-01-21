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

/** Theme configuration for each agent type. */
interface AgentTheme {
  /** Icon component for the agent. */
  icon: LucideIcon;
  /** Active state container classes (border, background, shadow). */
  activeClasses: string;
  /** Completed state container classes (muted version). */
  completedClasses: string;
  /** Active state icon classes. */
  activeIconClasses: string;
  /** Completed state icon classes. */
  completedIconClasses: string;
}

/** Consolidated theme configuration for all agent types. */
const AGENT_THEME_CONFIG: Record<string, AgentTheme> = {
  architect: {
    icon: Compass,
    activeClasses: 'border-agent-architect bg-agent-architect/10 shadow-lg shadow-agent-architect/20',
    completedClasses: 'border-agent-architect/40 bg-agent-architect/5',
    activeIconClasses: 'text-agent-architect animate-pulse',
    completedIconClasses: 'text-agent-architect/70',
  },
  developer: {
    icon: Code,
    activeClasses: 'border-agent-developer bg-agent-developer/10 shadow-lg shadow-agent-developer/20',
    completedClasses: 'border-agent-developer/40 bg-agent-developer/5',
    activeIconClasses: 'text-agent-developer animate-pulse',
    completedIconClasses: 'text-agent-developer/70',
  },
  reviewer: {
    icon: Eye,
    activeClasses: 'border-agent-reviewer bg-agent-reviewer/10 shadow-lg shadow-agent-reviewer/20',
    completedClasses: 'border-agent-reviewer/40 bg-agent-reviewer/5',
    activeIconClasses: 'text-agent-reviewer animate-pulse',
    completedIconClasses: 'text-agent-reviewer/70',
  },
  plan_validator: {
    icon: ClipboardCheck,
    activeClasses: 'border-agent-pm bg-agent-pm/10 shadow-lg shadow-agent-pm/20',
    completedClasses: 'border-agent-pm/40 bg-agent-pm/5',
    activeIconClasses: 'text-agent-pm animate-pulse',
    completedIconClasses: 'text-agent-pm/70',
  },
  human_approval: {
    icon: Hand,
    activeClasses: 'border-destructive bg-destructive/10 shadow-lg shadow-destructive/20',
    completedClasses: 'border-destructive/40 bg-destructive/5',
    activeIconClasses: 'text-destructive animate-pulse',
    completedIconClasses: 'text-destructive/70',
  },
};

/** Default theme for unknown agent types. */
const DEFAULT_THEME: AgentTheme = {
  icon: CircleDot,
  activeClasses: 'border-primary bg-primary/10 shadow-lg shadow-primary/20',
  completedClasses: 'border-primary/40 bg-primary/5',
  activeIconClasses: 'text-primary animate-pulse',
  completedIconClasses: 'text-primary/70',
};

/** Get the theme configuration for an agent type. */
function getAgentTheme(agentType: string): AgentTheme {
  return AGENT_THEME_CONFIG[agentType] ?? DEFAULT_THEME;
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
    return getAgentTheme(agentType).activeClasses;
  }
  if (status === 'completed') {
    return getAgentTheme(agentType).completedClasses;
  }
  return baseStatusClasses[status];
}

/** Get icon classes for a node, with agent-specific styling. */
function getIconClasses(status: AgentNodeData['status'], agentType: string): string {
  if (status === 'active') {
    return getAgentTheme(agentType).activeIconClasses;
  }
  if (status === 'completed') {
    return getAgentTheme(agentType).completedIconClasses;
  }
  return baseIconClasses[status];
}

export const AgentNode = memo(function AgentNode({ data }: NodeProps<AgentNodeType>) {
  const { agentType, status, iterations, isExpanded } = data;
  const Icon = getAgentTheme(agentType).icon;

  return (
    <div
      data-status={status}
      className={cn(
        'w-[100px] lg:w-[120px] rounded-lg border p-2 lg:p-3 transition-all',
        getStatusClasses(status, agentType)
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-border" />

      <div className="flex flex-col items-center gap-1 lg:gap-1.5 text-center">
        <Icon className={cn('h-5 w-5 lg:h-6 lg:w-6', getIconClasses(status, agentType))} />
        <span className="text-sm lg:text-base font-medium">{getNodeDisplayName(agentType)}</span>
        <p className="text-xs lg:text-sm text-muted-foreground">
          {status === 'active' && 'In progress...'}
          {status === 'completed' && 'Completed'}
          {status === 'pending' && 'Pending'}
          {status === 'blocked' && 'Blocked'}
        </p>
        {iterations.length > 1 && (
          <Badge variant="secondary" className="text-[10px] lg:text-xs">
            {iterations.length} runs
          </Badge>
        )}
      </div>

      {isExpanded && iterations.length > 0 && (
        <div className="mt-2 space-y-1 text-xs text-center">
          {iterations.map((iter, idx) => (
            <div key={iter.id} className="flex flex-col">
              <span className="text-muted-foreground">Run {idx + 1}</span>
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
