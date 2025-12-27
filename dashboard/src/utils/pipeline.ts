/**
 * @fileoverview Pipeline conversion utilities for workflow visualization.
 *
 * In the agentic execution model, the pipeline shows agent stages rather
 * than individual batch/steps.
 */
import type { WorkflowDetail } from '@/types';

/**
 * Node in the pipeline visualization.
 * @property id - Unique identifier for the node
 * @property label - Primary label displayed in the node
 * @property subtitle - Optional secondary text displayed below the label
 * @property status - Current execution status of the node
 * @property tokens - Optional token count to display
 */
export interface PipelineNode {
  id: string;
  label: string;
  subtitle?: string;
  status: 'completed' | 'active' | 'blocked' | 'pending';
  tokens?: string;
}

/**
 * Edge connecting pipeline nodes.
 * @property from - Source node ID
 * @property to - Target node ID
 * @property label - Label displayed on the edge
 * @property status - Status determining the edge's visual style
 */
export interface PipelineEdge {
  from: string;
  to: string;
  label: string;
  status: 'completed' | 'active' | 'pending';
}

/**
 * Pipeline data structure for WorkflowCanvas.
 * @property nodes - Array of pipeline nodes to render
 * @property edges - Array of edges connecting the nodes
 */
export interface Pipeline {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

/**
 * Agent stages in the workflow.
 */
const AGENT_STAGES = ['architect', 'developer', 'reviewer'] as const;

/**
 * Maps current_stage to a stage index for comparison.
 */
function getStageIndex(stage: string | null): number {
  if (!stage) return -1;
  // Map node names to stage names
  const stageMap: Record<string, string> = {
    'architect_node': 'architect',
    'developer_node': 'developer',
    'reviewer_node': 'reviewer',
    'human_approval_node': 'architect', // Approval happens after architect
  };
  const mappedStage = stageMap[stage] || stage;
  return AGENT_STAGES.indexOf(mappedStage as typeof AGENT_STAGES[number]);
}

/**
 * Determines the status of a stage based on current execution position.
 */
function getStageStatus(
  stageIndex: number,
  currentStageIndex: number,
  workflowStatus: WorkflowDetail['status']
): 'completed' | 'active' | 'blocked' | 'pending' {
  if (stageIndex < currentStageIndex) {
    return 'completed';
  }
  if (stageIndex === currentStageIndex) {
    if (workflowStatus === 'blocked') {
      return 'blocked';
    }
    if (workflowStatus === 'completed' || workflowStatus === 'failed') {
      return 'completed';
    }
    return 'active';
  }
  return 'pending';
}

/**
 * Converts a workflow detail into a pipeline visualization format.
 * Shows agent stages for agentic execution.
 *
 * @param workflow - The workflow detail
 * @returns Pipeline data with agent stage nodes
 */
export function buildPipeline(workflow: WorkflowDetail): Pipeline | null {
  const nodes: PipelineNode[] = [];
  const edges: PipelineEdge[] = [];

  const currentStageIndex = getStageIndex(workflow.current_stage);

  // Create nodes for each agent stage
  AGENT_STAGES.forEach((stage, index) => {
    const status = getStageStatus(index, currentStageIndex, workflow.status);

    nodes.push({
      id: stage,
      label: stage.charAt(0).toUpperCase() + stage.slice(1),
      subtitle: status === 'active' ? 'In progress...' : undefined,
      status,
    });

    // Add edge from previous stage
    // Edge status is based on the source node (previous stage), not the target
    if (index > 0) {
      const prevStage = AGENT_STAGES[index - 1];
      const prevStatus = getStageStatus(index - 1, currentStageIndex, workflow.status);
      edges.push({
        from: prevStage,
        to: stage,
        label: '',
        status: prevStatus === 'completed' ? 'completed' : prevStatus === 'active' ? 'active' : 'pending',
      });
    }
  });

  return { nodes, edges };
}
