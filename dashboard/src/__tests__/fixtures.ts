/**
 * Test fixture factory functions for the Amelia Dashboard.
 * Provides factory functions for creating mock data with sensible defaults.
 */

import {
  type WorkflowSummary,
  type WorkflowDetail,
  type WorkflowEvent,
  type TokenSummary,
  type TokenUsage,
} from '../types';

// ============================================================================
// Factory Functions
// ============================================================================

/**
 * Creates a mock WorkflowSummary with sensible defaults.
 * @param overrides - Optional partial object to override default values
 */
export function createMockWorkflowSummary(
  overrides?: Partial<WorkflowSummary>
): WorkflowSummary {
  return {
    id: 'wf-test-123',
    issue_id: 'ISSUE-123',
    worktree_path: '/tmp/test-worktree',
    profile: null,
    status: 'in_progress',
    created_at: '2025-12-06T09:55:00Z',
    started_at: '2025-12-06T10:00:00Z',
    current_stage: 'architect',
    total_cost_usd: null,
    total_tokens: null,
    total_duration_ms: null,
    ...overrides,
  };
}

/**
 * Creates a mock TokenUsage entry for a specific agent.
 * @param overrides - Optional partial object to override default values
 */
export function createMockTokenUsage(
  overrides?: Partial<TokenUsage>
): TokenUsage {
  return {
    id: 'tu-test-123',
    workflow_id: 'wf-test-123',
    agent: 'architect',
    model: 'claude-sonnet-4-20250514',
    input_tokens: 2100,
    output_tokens: 500,
    cache_read_tokens: 1800,
    cache_creation_tokens: 0,
    cost_usd: 0.08,
    duration_ms: 15000,
    num_turns: 3,
    timestamp: '2025-12-06T10:00:00Z',
    ...overrides,
  };
}

/**
 * Creates a mock TokenSummary with sensible defaults.
 * @param overrides - Optional partial object to override default values
 */
export function createMockTokenSummary(
  overrides?: Partial<TokenSummary>
): TokenSummary {
  return {
    total_input_tokens: 13700,
    total_output_tokens: 3000,
    total_cache_read_tokens: 10900,
    total_cost_usd: 0.42,
    total_duration_ms: 154000,
    total_turns: 12,
    breakdown: [
      createMockTokenUsage({
        agent: 'architect',
        input_tokens: 2100,
        output_tokens: 500,
        cache_read_tokens: 1800,
        cost_usd: 0.08,
        duration_ms: 15000,
        num_turns: 3,
      }),
      createMockTokenUsage({
        id: 'tu-test-456',
        agent: 'developer',
        input_tokens: 8400,
        output_tokens: 2100,
        cache_read_tokens: 6200,
        cost_usd: 0.28,
        duration_ms: 97000,
        num_turns: 6,
      }),
      createMockTokenUsage({
        id: 'tu-test-789',
        agent: 'reviewer',
        input_tokens: 3200,
        output_tokens: 400,
        cache_read_tokens: 2900,
        cost_usd: 0.06,
        duration_ms: 42000,
        num_turns: 3,
      }),
    ],
    ...overrides,
  };
}

/**
 * Creates a mock WorkflowDetail with sensible defaults.
 * @param overrides - Optional partial object to override default values
 */
export function createMockWorkflowDetail(
  overrides?: Partial<WorkflowDetail>
): WorkflowDetail {
  return {
    id: 'wf-test-123',
    issue_id: 'ISSUE-123',
    worktree_path: '/tmp/test-worktree',
    profile: null,
    status: 'in_progress',
    created_at: '2025-12-06T09:55:00Z',
    started_at: '2025-12-06T10:00:00Z',
    current_stage: 'architect',
    completed_at: null,
    failure_reason: null,
    total_cost_usd: null,
    total_tokens: null,
    total_duration_ms: null,
    token_usage: null,
    recent_events: [],
    // Agentic execution fields
    goal: 'Test goal for implementation',
    plan_markdown: null,
    plan_path: null,
    ...overrides,
  };
}

/**
 * Creates a mock WorkflowEvent with sensible defaults.
 * @param overrides - Optional partial object to override default values
 */
export function createMockEvent(
  overrides?: Partial<WorkflowEvent>
): WorkflowEvent {
  return {
    id: 'evt-test-1',
    workflow_id: 'wf-test-123',
    sequence: 1,
    timestamp: '2025-12-06T10:00:00Z',
    agent: 'architect',
    event_type: 'workflow_started',
    level: 'info',
    message: 'Test event',
    ...overrides,
  };
}

