import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useActivityLogGroups } from '../useActivityLogGroups';
import type { WorkflowEvent } from '@/types';

const makeEvent = (overrides: Partial<WorkflowEvent>): WorkflowEvent => ({
  id: 'evt-1',
  workflow_id: 'wf-1',
  sequence: 1,
  timestamp: '2025-01-01T00:00:00Z',
  agent: 'developer',
  event_type: 'task_started',
  level: 'debug',
  message: 'Test event',
  ...overrides,
});

describe('useActivityLogGroups', () => {
  it('groups events by agent/stage', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'architect', sequence: 1, event_type: 'stage_started' }),
      makeEvent({ id: '2', agent: 'architect', sequence: 2, event_type: 'stage_completed' }),
      makeEvent({ id: '3', agent: 'developer', sequence: 3, event_type: 'task_started' }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    expect(result.current.groups).toHaveLength(2);
    expect(result.current.groups[0]?.stage).toBe('architect');
    expect(result.current.groups[0]?.events).toHaveLength(2);
    expect(result.current.groups[1]?.stage).toBe('developer');
    expect(result.current.groups[1]?.events).toHaveLength(1);
  });

  it('filters out trace level events', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', level: 'info', event_type: 'stage_started' }),
      makeEvent({ id: '2', level: 'debug', event_type: 'task_started' }),
      makeEvent({ id: '3', level: 'trace', event_type: 'claude_tool_call' }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    const allEvents = result.current.groups.flatMap((g) => g.events);
    expect(allEvents).toHaveLength(2);
    expect(allEvents.find((e) => e.level === 'trace')).toBeUndefined();
  });

  it('collapses stages in collapsedStages set', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'architect', sequence: 1 }),
      makeEvent({ id: '2', agent: 'developer', sequence: 2 }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set(['architect']))
    );

    // Headers always present, but collapsed stage events excluded from rows
    const rows = result.current.rows;
    const architectEvents = rows.filter(
      (r) => r.type === 'event' && r.event.agent === 'architect'
    );
    expect(architectEvents).toHaveLength(0);
  });

  it('orders stages as system -> architect -> plan_validator -> human_approval -> developer -> reviewer', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'reviewer', sequence: 1 }),
      makeEvent({ id: '2', agent: 'architect', sequence: 2 }),
      makeEvent({ id: '3', agent: 'developer', sequence: 3 }),
      makeEvent({ id: '4', agent: 'system', sequence: 4 }),
      makeEvent({ id: '5', agent: 'human_approval', sequence: 5 }),
      makeEvent({ id: '6', agent: 'plan_validator', sequence: 6 }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    const stageOrder = result.current.groups.map((g) => g.stage);
    expect(stageOrder).toEqual([
      'system',
      'architect',
      'plan_validator',
      'human_approval',
      'developer',
      'reviewer',
    ]);
  });

  it('marks stage active if has stage_started but not stage_completed', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'architect', event_type: 'stage_started' }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    expect(result.current.groups[0]?.isActive).toBe(true);
    expect(result.current.groups[0]?.isCompleted).toBe(false);
  });

  it('maps unknown agents to developer stage', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'unknown_agent', sequence: 1 }),
      makeEvent({ id: '2', agent: 'some_other_agent', sequence: 2 }),
      makeEvent({ id: '3', agent: 'developer', sequence: 3 }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    // All events should be grouped under developer
    expect(result.current.groups).toHaveLength(1);
    expect(result.current.groups[0]?.stage).toBe('developer');
    expect(result.current.groups[0]?.events).toHaveLength(3);
  });
});
