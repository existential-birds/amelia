import type { WorkflowEvent } from '@/types';

/**
 * Agent stages in workflow execution order.
 */
export type AgentStage =
  | 'system'
  | 'architect'
  | 'plan_validator'
  | 'human_approval'
  | 'developer'
  | 'reviewer';

/**
 * Stage labels for display.
 */
export const STAGE_LABELS: Record<AgentStage, string> = {
  system: 'System',
  architect: 'Planning (Architect)',
  plan_validator: 'Plan Validation',
  human_approval: 'Human Approval',
  developer: 'Implementation (Developer)',
  reviewer: 'Review (Reviewer)',
};

/**
 * Stage order for sorting.
 */
export const STAGE_ORDER: AgentStage[] = [
  'system',
  'architect',
  'plan_validator',
  'human_approval',
  'developer',
  'reviewer',
];

/**
 * Grouped events by stage for hierarchical display.
 */
export interface StageGroup {
  /** Stage identifier. */
  stage: AgentStage;
  /** Display label for the stage. */
  label: string;
  /** Events belonging to this stage. */
  events: WorkflowEvent[];
  /** Whether this stage is currently active. */
  isActive: boolean;
  /** Whether this stage is completed. */
  isCompleted: boolean;
  /** Timestamp of first event (null if no events). */
  startedAt: string | null;
  /** Timestamp of last event (null if no events). */
  endedAt: string | null;
}

/**
 * Row types for virtualized list.
 */
export type VirtualRow =
  | { type: 'header'; group: StageGroup }
  | { type: 'event'; event: WorkflowEvent };
