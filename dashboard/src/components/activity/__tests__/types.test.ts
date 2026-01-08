import { describe, it, expect } from 'vitest';
import type { StageGroup, VirtualRow, AgentStage } from '../types';

describe('Activity log types', () => {
  it('AgentStage type supports all agent values', () => {
    const stages: AgentStage[] = [
      'system',
      'architect',
      'plan_validator',
      'human_approval',
      'developer',
      'reviewer',
    ];
    expect(stages).toHaveLength(6);
  });

  it('StageGroup has required fields', () => {
    const group: StageGroup = {
      stage: 'architect',
      label: 'Planning (Architect)',
      events: [],
      isActive: false,
      isCompleted: true,
      startedAt: '2025-01-01T00:00:00Z',
      endedAt: '2025-01-01T00:05:00Z',
    };

    expect(group.stage).toBe('architect');
    expect(group.events).toEqual([]);
  });

  it('VirtualRow can be header or event', () => {
    const headerRow: VirtualRow = {
      type: 'header',
      group: {
        stage: 'developer',
        label: 'Implementation',
        events: [],
        isActive: true,
        isCompleted: false,
        startedAt: null,
        endedAt: null,
      },
    };

    const eventRow: VirtualRow = {
      type: 'event',
      event: {
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        timestamp: '2025-01-01T00:00:00Z',
        agent: 'developer',
        event_type: 'task_started',
        level: 'debug',
        message: 'Started task',
      },
    };

    expect(headerRow.type).toBe('header');
    expect(eventRow.type).toBe('event');
  });
});
