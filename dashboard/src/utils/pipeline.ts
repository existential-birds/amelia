/**
 * @fileoverview Pipeline conversion utilities for workflow visualization.
 */
import type { WorkflowDetail, PlanStep, ExecutionBatch } from '@/types';

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
 * Truncates text to a maximum length, adding ellipsis if needed.
 * @param text - Text to truncate
 * @param maxLength - Maximum length before truncation (default 20)
 * @returns Truncated text with ellipsis, or original text if within limit
 */
function truncateText(text: string, maxLength = 20): string {
  if (text.length <= maxLength) {
    return text;
  }
  return text.slice(0, maxLength - 1) + '…';
}

/**
 * Generates a label for a step node from the step description.
 * Truncates long descriptions to fit within node constraints.
 * @param step - The plan step
 * @returns Truncated step description suitable for display
 */
function getStepLabel(step: PlanStep): string {
  return truncateText(step.description);
}

/**
 * Determines the status of a batch based on current execution position.
 * Past batches are completed, current batch matches workflow status, future batches are pending.
 * @param batchIndex - Index of this batch
 * @param currentBatchIndex - Index of the currently executing batch
 * @param workflowStatus - Current workflow status
 * @returns Status for visualization (completed, active, blocked, or pending)
 */
function getBatchStatus(
  batchIndex: number,
  currentBatchIndex: number,
  workflowStatus: WorkflowDetail['status']
): 'completed' | 'active' | 'blocked' | 'pending' {
  if (batchIndex < currentBatchIndex) {
    return 'completed';
  }
  if (batchIndex === currentBatchIndex) {
    if (workflowStatus === 'blocked') {
      return 'blocked';
    }
    return 'active';
  }
  return 'pending';
}

/**
 * Converts a workflow detail into a pipeline visualization format.
 * Uses the ExecutionPlan batches for visualization.
 *
 * @param workflow - The workflow detail containing the execution plan
 * @returns Pipeline data or null if no execution plan exists
 */
export function buildPipeline(workflow: WorkflowDetail): Pipeline | null {
  if (!workflow.execution_plan) {
    return null;
  }

  const nodes: PipelineNode[] = [];
  const edges: PipelineEdge[] = [];
  let previousBatchNodeId: string | null = null;

  workflow.execution_plan.batches.forEach((batch: ExecutionBatch, batchIndex: number) => {
    const batchStatus = getBatchStatus(batchIndex, workflow.current_batch_index, workflow.status);

    // Create a node for each step in the batch
    batch.steps.forEach((step: PlanStep, stepIndex: number) => {
      const nodeId = `batch-${batch.batch_number}-step-${step.id}`;

      nodes.push({
        id: nodeId,
        label: getStepLabel(step),
        subtitle: batch.description || `Batch ${batch.batch_number}`,
        status: batchStatus,
      });

      // Add edge from previous step in this batch
      if (stepIndex > 0) {
        const prevStep = batch.steps[stepIndex - 1];
        if (prevStep) {
          const prevNodeId = `batch-${batch.batch_number}-step-${prevStep.id}`;
          edges.push({
            from: prevNodeId,
            to: nodeId,
            label: '',
            status: batchStatus === 'completed' ? 'completed' : batchStatus === 'active' ? 'active' : 'pending',
          });
        }
      }
    });

    // Add edge from last node of previous batch to first node of this batch
    const firstStep = batch.steps[0];
    if (previousBatchNodeId && firstStep) {
      const firstNodeId = `batch-${batch.batch_number}-step-${firstStep.id}`;
      edges.push({
        from: previousBatchNodeId,
        to: firstNodeId,
        label: `Batch ${batch.batch_number}`,
        status: batchStatus === 'completed' ? 'completed' : batchStatus === 'active' ? 'active' : 'pending',
      });
    }

    // Track last node of this batch for next iteration
    const lastStep = batch.steps[batch.steps.length - 1];
    if (lastStep) {
      previousBatchNodeId = `batch-${batch.batch_number}-step-${lastStep.id}`;
    }
  });

  return { nodes, edges };
}
