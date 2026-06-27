/**
 * Workflow and brainstorm event types.
 *
 * These mirror two backend StrEnums in `amelia/server/models/events.py`, 1:1:
 *
 * - `EventType` ↔ backend `EventType`: workflow events, sent wrapped as
 *   `{ type: 'event', payload }`.
 * - `BrainstormEventType` ↔ backend `BrainstormEventType`: brainstorm events,
 *   sent flat as `{ type: 'brainstorm', event_type, ... }`.
 *
 * Brainstorm is its own domain with its own enum, so the names are unprefixed on
 * both ends — no wire transform. Parity with the backend is enforced by
 * `tests/unit/test_event_type_parity.py`.
 */

/**
 * Severity level for workflow events.
 * Used to filter and categorize events in the UI.
 *
 * - `info`: High-level workflow progress (lifecycle, stages, approvals)
 * - `warning`: System warnings and non-critical issues
 * - `error`: Error events
 * - `debug`: Detailed operational information (file changes, agent messages)
 */
export type EventLevel = 'info' | 'warning' | 'error' | 'debug';

/**
 * Types of events that can occur during workflow execution.
 * Events are emitted by agents and the orchestrator to track workflow progress.
 *
 * Mirrors the non-brainstorm members of the backend `EventType` enum. Brainstorm
 * events use {@link BrainstormEventType} instead.
 */
export type EventType =
  // Lifecycle
  | 'workflow_created'
  | 'workflow_started'
  | 'workflow_completed'
  | 'workflow_failed'
  | 'workflow_cancelled'
  // Stages
  | 'stage_started'
  | 'stage_completed'
  // Approval
  | 'approval_required'
  | 'approval_granted'
  | 'approval_rejected'
  // Artifacts
  | 'file_created'
  | 'file_modified'
  | 'file_deleted'
  // Review cycle
  | 'review_requested'
  | 'review_completed'
  | 'revision_requested'
  // Agent messages (replaces in-state message accumulation)
  | 'agent_message'
  | 'task_started'
  | 'task_completed'
  | 'task_failed'
  // System
  | 'system_error'
  | 'system_warning'
  | 'tool_policy_decision'
  // Streaming (ephemeral, not persisted)
  | 'stream'
  // Trace (stream events)
  | 'claude_thinking'
  | 'claude_tool_call'
  | 'claude_tool_result'
  | 'agent_output'
  // Oracle consultation
  | 'oracle_consultation_started'
  | 'oracle_consultation_thinking'
  | 'oracle_tool_call'
  | 'oracle_tool_result'
  | 'oracle_consultation_completed'
  | 'oracle_consultation_failed'
  // Knowledge ingestion
  | 'document_ingestion_started'
  | 'document_ingestion_progress'
  | 'document_ingestion_completed'
  | 'document_ingestion_failed'
  // Plan validation
  | 'plan_validated'
  | 'plan_validation_failed'
  // PR auto-fix lifecycle
  | 'pr_comments_detected'
  | 'pr_auto_fix_started'
  | 'pr_auto_fix_completed'
  | 'pr_auto_fix_failed'
  | 'pr_comments_resolved'
  | 'pr_poll_error'
  // PR auto-fix orchestration
  | 'pr_fix_queued'
  | 'pr_fix_diverged'
  | 'pr_fix_cooldown_started'
  | 'pr_fix_cooldown_reset'
  | 'pr_fix_retries_exhausted'
  | 'pr_poll_rate_limited';

/**
 * Event types for brainstorm streaming messages.
 *
 * These are the backend `brainstorm_*` enum members with the `brainstorm_`
 * prefix stripped during WebSocket serialization.
 */
export type BrainstormEventType =
  | 'session_created'
  | 'reasoning'
  | 'tool_call'
  | 'tool_result'
  | 'text'
  | 'ask_user'
  | 'message_complete'
  | 'artifact_created'
  | 'session_completed'
  | 'message_failed';

/**
 * Domain of event origin.
 */
export type EventDomain = 'workflow' | 'brainstorm' | 'oracle' | 'knowledge';

/**
 * A single event emitted during workflow execution.
 * Events are streamed in real-time via WebSocket and stored for historical viewing.
 */
export interface WorkflowEvent {
  /** Unique identifier for this event. */
  id: string;

  /** Event domain (workflow, brainstorm, oracle, or knowledge). */
  domain?: EventDomain;

  /** ID of the workflow this event belongs to. */
  workflow_id: string;

  /** Sequential event number within the workflow (monotonically increasing). */
  sequence: number;

  /** ISO 8601 timestamp when the event was emitted. */
  timestamp: string;

  /**
   * Name of the agent that emitted this event (e.g., 'architect', 'developer').
   *
   * Open string to match the backend: events originate from many agents
   * (`classifier`, `oracle`, `brainstormer`, `system`, ...), not just the core
   * architect/developer/reviewer trio.
   */
  agent: string;

  /** Type of event that occurred. */
  event_type: EventType;

  /** Severity level for filtering and categorization. */
  level: EventLevel;

  /** Human-readable message describing the event. */
  message: string;

  /** Optional additional structured data specific to this event type. */
  data?: Record<string, unknown>;

  /** Optional correlation ID for grouping related events. */
  correlation_id?: string;

  /** Name of the tool being called (for claude_tool_call/claude_tool_result events). */
  tool_name?: string;

  /** Input parameters for the tool call (for claude_tool_call events). */
  tool_input?: Record<string, unknown>;

  /** Whether this event represents an error (for tool results). */
  is_error?: boolean;

  /** Trace ID for distributed tracing correlation. */
  trace_id?: string;

  /** Parent event ID for hierarchical event relationships. */
  parent_id?: string;

  /** LLM model used for this event (for trace events). */
  model?: string;

  /** Per-consultation session ID (independent from workflow_id, used by Oracle events). */
  session_id?: string;
}
