import { useMemo } from 'react';
import type { WorkflowEvent } from '@/types';
import type { StageGroup, VirtualRow, AgentStage } from './types';
import { STAGE_ORDER, STAGE_LABELS } from './types';

/**
 * Hook to group workflow events by stage for hierarchical display.
 *
 * @param events - All workflow events (will filter to info+debug only)
 * @param collapsedStages - Set of stage names that are collapsed
 * @returns Groups and flattened rows for virtualization
 */
export function useActivityLogGroups(
  events: WorkflowEvent[],
  collapsedStages: Set<string>
): { groups: StageGroup[]; rows: VirtualRow[] } {
  return useMemo(() => {
    // Filter to info+debug only (exclude trace)
    const filteredEvents = events.filter((e) => e.level !== 'trace');

    // Group events by agent
    const byAgent = new Map<string, WorkflowEvent[]>();
    for (const event of filteredEvents) {
      const agent = event.agent.toLowerCase();
      // Map unknown agents to developer
      const targetStage = STAGE_ORDER.includes(agent as AgentStage)
        ? agent
        : 'developer';
      const existing = byAgent.get(targetStage) || [];
      existing.push(event);
      byAgent.set(targetStage, existing);
    }

    // Build stage groups in order
    const groups: StageGroup[] = STAGE_ORDER.filter((stage) =>
      byAgent.has(stage)
    ).map((stage) => {
      const stageEvents = byAgent.get(stage) || [];
      const sorted = [...stageEvents].sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      );

      const hasStarted = sorted.some((e) => e.event_type === 'stage_started');
      const hasCompleted = sorted.some(
        (e) => e.event_type === 'stage_completed'
      );

      return {
        stage: stage as AgentStage,
        label: STAGE_LABELS[stage as AgentStage],
        events: sorted,
        isActive: hasStarted && !hasCompleted,
        isCompleted: hasCompleted,
        startedAt: sorted[0]?.timestamp ?? null,
        endedAt: sorted[sorted.length - 1]?.timestamp ?? null,
      };
    });

    // Flatten for virtualization
    const rows: VirtualRow[] = [];
    for (const group of groups) {
      rows.push({ type: 'header', group });
      if (!collapsedStages.has(group.stage)) {
        for (const event of group.events) {
          rows.push({ type: 'event', event });
        }
      }
    }

    return { groups, rows };
  }, [events, collapsedStages]);
}
