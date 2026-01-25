import { describe, it, expect } from 'vitest';
import type {
  EventLevel,
  WorkflowEvent,
  CreateWorkflowRequest,
  BatchStartRequest,
  BatchStartResponse,
  SetPlanRequest,
  SetPlanResponse,
} from '../index';

describe('WorkflowEvent types', () => {
  it('supports level field', () => {
    const event: WorkflowEvent = {
      id: 'evt-1',
      workflow_id: 'wf-1',
      sequence: 1,
      timestamp: '2025-01-01T00:00:00Z',
      agent: 'developer',
      event_type: 'claude_tool_call',
      level: 'trace',
      message: 'Tool call',
      tool_name: 'Edit',
      tool_input: { file: 'test.py' },
      is_error: false,
    };

    expect(event.level).toBe('trace');
    expect(event.tool_name).toBe('Edit');
  });

  it('level can be info, debug, or trace', () => {
    const levels: EventLevel[] = ['info', 'debug', 'trace'];
    expect(levels).toHaveLength(3);
  });

  it('supports distributed tracing fields', () => {
    const event: WorkflowEvent = {
      id: 'evt-1',
      workflow_id: 'wf-1',
      sequence: 1,
      timestamp: '2025-01-01T00:00:00Z',
      agent: 'developer',
      event_type: 'claude_tool_result',
      level: 'trace',
      message: 'Tool result',
      trace_id: 'trace-abc-123',
      parent_id: 'evt-parent',
    };

    expect(event.trace_id).toBe('trace-abc-123');
    expect(event.parent_id).toBe('evt-parent');
  });
});

describe('CreateWorkflowRequest', () => {
  it('should allow start and plan_now fields', () => {
    const request: CreateWorkflowRequest = {
      issue_id: 'ISSUE-123',
      worktree_path: '/path/to/repo',
      task_title: 'Test task',
      start: false,
      plan_now: true,
    };
    expect(request.start).toBe(false);
    expect(request.plan_now).toBe(true);
  });

  it('should have optional start defaulting to true semantically', () => {
    const request: CreateWorkflowRequest = {
      issue_id: 'ISSUE-123',
      worktree_path: '/path/to/repo',
      task_title: 'Test task',
    };
    // Fields are optional in TypeScript
    expect(request.start).toBeUndefined();
  });
});

describe('BatchStartRequest', () => {
  it('should allow empty request', () => {
    const request: BatchStartRequest = {};
    expect(request.workflow_ids).toBeUndefined();
    expect(request.worktree_path).toBeUndefined();
  });

  it('should allow workflow_ids list', () => {
    const request: BatchStartRequest = {
      workflow_ids: ['wf-1', 'wf-2'],
    };
    expect(request.workflow_ids).toHaveLength(2);
  });

  it('should allow worktree_path filter', () => {
    const request: BatchStartRequest = {
      worktree_path: '/path/to/repo',
    };
    expect(request.worktree_path).toBe('/path/to/repo');
  });
});

describe('BatchStartResponse', () => {
  it('should have started and errors fields', () => {
    const response: BatchStartResponse = {
      started: ['wf-1', 'wf-2'],
      errors: { 'wf-3': 'Worktree conflict' },
    };
    expect(response.started).toHaveLength(2);
    expect(response.errors['wf-3']).toBe('Worktree conflict');
  });
});

describe('SetPlanRequest', () => {
  it('should allow plan_file', () => {
    const request: SetPlanRequest = {
      plan_file: 'docs/plans/feature.md',
    };
    expect(request.plan_file).toBe('docs/plans/feature.md');
    expect(request.plan_content).toBeUndefined();
  });

  it('should allow plan_content', () => {
    const request: SetPlanRequest = {
      plan_content: '# Plan\n\n### Task 1: Do thing',
    };
    expect(request.plan_content).toContain('# Plan');
    expect(request.plan_file).toBeUndefined();
  });

  it('should allow force flag', () => {
    const request: SetPlanRequest = {
      plan_file: 'plan.md',
      force: true,
    };
    expect(request.force).toBe(true);
  });
});

describe('SetPlanResponse', () => {
  it('should have goal, key_files, and total_tasks', () => {
    const response: SetPlanResponse = {
      goal: 'Implement feature X',
      key_files: ['src/feature.ts', 'tests/feature.test.ts'],
      total_tasks: 5,
    };
    expect(response.goal).toBe('Implement feature X');
    expect(response.key_files).toHaveLength(2);
    expect(response.total_tasks).toBe(5);
  });
});
