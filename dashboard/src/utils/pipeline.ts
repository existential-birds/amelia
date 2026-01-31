/**
 * @fileoverview Pipeline conversion utilities for workflow visualization.
 *
 * Builds event-driven pipeline visualization from workflow events, enabling
 * real-time updates as events arrive via WebSocket.
 */
import type { Node, Edge } from '@xyflow/react';
import type { WorkflowEvent } from '@/types';

/** A single execution iteration of an agent (agents can run multiple times). */
export interface AgentIteration {
  /** Unique identifier for this iteration. */
  id: string;
  /** ISO 8601 timestamp when this iteration started. */
  startedAt: string;
  /** ISO 8601 timestamp when this iteration completed (undefined if still running). */
  completedAt?: string;
  /** Current status of this iteration. */
  status: 'running' | 'completed' | 'failed';
  /** Optional message (e.g., "Requested changes" or "Approved"). */
  message?: string;
}

/** Data for an agent node in the workflow canvas. */
export interface AgentNodeData extends Record<string, unknown> {
  /** Type of agent (e.g., 'architect', 'developer', 'reviewer'). */
  agentType: string;
  /** Current visual status of the node. */
  status: 'pending' | 'active' | 'completed' | 'blocked';
  /** All iterations this agent has executed. */
  iterations: AgentIteration[];
  /** Whether the iteration history is expanded. */
  isExpanded: boolean;
}

/** Options for buildPipelineFromEvents. */
export interface BuildPipelineOptions {
  /** Show default 3-node pipeline even with no events. Default: false. */
  showDefaultPipeline?: boolean;
}

/** Pipeline structure with nodes and edges for React Flow. */
export interface EventDrivenPipeline {
  nodes: Node<AgentNodeData>[];
  edges: Edge<{ status: 'completed' | 'active' | 'pending' }>[];
}

const DEFAULT_AGENTS = ['architect', 'developer', 'reviewer'];

/**
 * Extract the agent name from a stage event.
 *
 * Stage events have `agent: "system"` but the actual stage name is in `data.stage`.
 * This function extracts the agent name from the stage, stripping the `_node` suffix.
 *
 * @param event - The workflow event to extract agent name from
 * @returns The agent name (e.g., 'architect', 'developer', 'reviewer') or the event's agent field as fallback
 *
 * @example
 * // Event with data.stage = "architect_node" returns "architect"
 * // Event with data.stage = "developer_node" returns "developer"
 * // Event without data.stage returns event.agent
 */
function extractAgentFromStageEvent(event: WorkflowEvent): string {
  // For stage events, the agent name is in data.stage (e.g., "architect_node")
  if (event.data?.stage && typeof event.data.stage === 'string') {
    const stage = event.data.stage;
    // Strip "_node" suffix if present (e.g., "architect_node" -> "architect")
    return stage.endsWith('_node') ? stage.slice(0, -5) : stage;
  }
  // Fallback to event.agent for non-stage events or missing data
  return event.agent;
}

/**
 * Build pipeline visualization from workflow events.
 *
 * This function derives node status directly from events rather than
 * relying on stale cached state, enabling real-time updates.
 */
export function buildPipelineFromEvents(
  events: WorkflowEvent[],
  options: BuildPipelineOptions = {}
): EventDrivenPipeline {
  const { showDefaultPipeline = false } = options;

  // Track agents and their iterations
  const agentMap = new Map<string, AgentIteration[]>();
  const agentOrder: string[] = [];
  let workflowFailed = false;

  // Process events in sequence order
  const sortedEvents = [...events].sort((a, b) => a.sequence - b.sequence);

  for (const event of sortedEvents) {
    const { event_type, timestamp, id } = event;

    if (event_type === 'stage_started') {
      // Extract agent from data.stage (e.g., "architect_node" -> "architect")
      const agent = extractAgentFromStageEvent(event);
      if (!agentMap.has(agent)) {
        agentMap.set(agent, []);
        agentOrder.push(agent);
      }
      const iterations = agentMap.get(agent);
      if (iterations) {
        // Mark any previous running iterations as superseded (retry scenario)
        for (const iter of iterations) {
          if (iter.status === 'running') {
            iter.status = 'completed';
          }
        }
        iterations.push({
          id: `${agent}-${id}`,
          startedAt: timestamp,
          status: 'running',
        });
      }
    } else if (event_type === 'stage_completed') {
      // Extract agent from data.stage (e.g., "architect_node" -> "architect")
      const agent = extractAgentFromStageEvent(event);
      const iterations = agentMap.get(agent);
      if (iterations && iterations.length > 0) {
        const lastIteration = iterations[iterations.length - 1];
        if (lastIteration && lastIteration.status === 'running') {
          lastIteration.completedAt = timestamp;
          lastIteration.status = 'completed';
        }
      }
    } else if (event_type === 'workflow_failed') {
      workflowFailed = true;
      // Mark any running iterations as failed
      for (const iterations of agentMap.values()) {
        for (const iter of iterations) {
          if (iter.status === 'running') {
            iter.status = 'failed';
          }
        }
      }
    }
  }

  // If no events and showDefaultPipeline, create pending nodes
  if (agentOrder.length === 0 && showDefaultPipeline) {
    for (const agent of DEFAULT_AGENTS) {
      agentMap.set(agent, []);
      agentOrder.push(agent);
    }
  }

  // Build nodes
  const nodes: Node<AgentNodeData>[] = agentOrder.map((agentType, index) => {
    const iterations = agentMap.get(agentType) || [];
    const hasRunningIteration = iterations.some(i => i.status === 'running');
    const hasFailedIteration = iterations.some(i => i.status === 'failed');
    const allCompleted = iterations.length > 0 && iterations.every(i => i.status === 'completed');

    let status: AgentNodeData['status'];
    if (hasFailedIteration || (workflowFailed && hasRunningIteration)) {
      status = 'blocked';
    } else if (hasRunningIteration) {
      status = 'active';
    } else if (allCompleted) {
      status = 'completed';
    } else {
      status = 'pending';
    }

    return {
      id: agentType,
      type: 'agent',
      position: { x: index * 250, y: 0 },  // Fallback horizontal layout; layout function overrides
      data: {
        agentType,
        status,
        iterations,
        isExpanded: false,
      },
    };
  });

  // Build edges between adjacent nodes
  const edges: Edge<{ status: 'completed' | 'active' | 'pending' }>[] = [];
  for (let i = 0; i < agentOrder.length - 1; i++) {
    const sourceAgent = agentOrder[i];
    const targetAgent = agentOrder[i + 1];
    // Skip if agents are undefined (shouldn't happen due to loop bounds)
    if (!sourceAgent || !targetAgent) continue;

    const sourceNode = nodes.find(n => n.id === sourceAgent);
    const targetNode = nodes.find(n => n.id === targetAgent);

    let edgeStatus: 'completed' | 'active' | 'pending';
    if (sourceNode?.data.status === 'completed') {
      edgeStatus = targetNode?.data.status === 'active' ? 'active' : 'completed';
    } else if (sourceNode?.data.status === 'active') {
      edgeStatus = 'active';
    } else {
      edgeStatus = 'pending';
    }

    edges.push({
      id: `${sourceAgent}-${targetAgent}`,
      source: sourceAgent,
      target: targetAgent,
      data: { status: edgeStatus },
    });
  }

  return { nodes, edges };
}
