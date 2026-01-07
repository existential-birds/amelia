import type { WorkflowEvent } from '@/types';

/**
 * Agent stages in workflow execution order.
 */
export type AgentStage = 'architect' | 'developer' | 'reviewer';

/**
 * Stage labels for display.
 */
export const STAGE_LABELS: Record<AgentStage, string> = {
  architect: 'Planning (Architect)',
  developer: 'Implementation (Developer)',
  reviewer: 'Review (Reviewer)',
};

/**
 * Stage order for sorting.
 */
export const STAGE_ORDER: AgentStage[] = ['architect', 'developer', 'reviewer'];

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
  | { type: 'event'; event: WorkflowEvent; stageIndex: number };
