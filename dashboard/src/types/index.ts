/**
 * Shared TypeScript types for the Amelia Dashboard.
 * These types mirror the Python Pydantic models from the backend API.
 */

// ============================================================================
// Workflow Types
// ============================================================================

/**
 * The current execution state of a workflow.
 *
 * - `pending`: Workflow has been created but not yet started
 * - `in_progress`: Workflow is actively executing
 * - `blocked`: Workflow is waiting for human approval or input
 * - `completed`: Workflow finished successfully
 * - `failed`: Workflow encountered an error and stopped
 * - `cancelled`: Workflow was manually cancelled by a user
 *
 * @example
 * ```typescript
 * const status: WorkflowStatus = 'in_progress';
 * ```
 */
export type WorkflowStatus =
  | 'pending'
  | 'in_progress'
  | 'blocked'
  | 'completed'
  | 'failed'
  | 'cancelled';

/**
 * Summary information about a workflow, used in list views.
 * Contains the minimal data needed to display a workflow in a table or card.
 */
export interface WorkflowSummary {
  /** Unique identifier for the workflow. */
  id: string;

  /** The issue ID from the tracking system (e.g., JIRA-123, GitHub #45). */
  issue_id: string;

  /** Name of the git worktree where this workflow is executing. */
  worktree_name: string;

  /** Current execution state of the workflow. */
  status: WorkflowStatus;

  /** ISO 8601 timestamp when the workflow started, or null if not yet started. */
  started_at: string | null;

  /** Name of the current execution stage (e.g., 'architect', 'developer', 'reviewer'). */
  current_stage: string | null;
}

/**
 * Complete detailed information about a workflow.
 * Extends WorkflowSummary with additional metadata, execution plan, token usage, and event history.
 */
export interface WorkflowDetail extends WorkflowSummary {
  /** Absolute filesystem path to the git worktree. */
  worktree_path: string;

  /** ISO 8601 timestamp when the workflow completed, or null if still running. */
  completed_at: string | null;

  /** Human-readable error message if the workflow failed, otherwise null. */
  failure_reason: string | null;

  /** The execution plan (task DAG) created by the architect agent, or null if not yet planned. */
  plan: TaskDAG | null;

  /** Token usage statistics grouped by agent name. */
  token_usage: Record<string, TokenSummary>;

  /** Recent workflow events for this workflow, ordered by sequence number. */
  recent_events: WorkflowEvent[];
}

// ============================================================================
// Event Types
// ============================================================================

/**
 * Types of events that can occur during workflow execution.
 * Events are emitted by agents and the orchestrator to track workflow progress.
 *
 * **Lifecycle events**: Overall workflow state changes
 * - `workflow_started`: Workflow execution has begun
 * - `workflow_completed`: Workflow finished successfully
 * - `workflow_failed`: Workflow encountered a fatal error
 * - `workflow_cancelled`: Workflow was cancelled by a user
 *
 * **Stage events**: Agent execution state changes
 * - `stage_started`: An agent has started executing
 * - `stage_completed`: An agent has finished executing
 *
 * **Approval events**: Human-in-the-loop interactions
 * - `approval_required`: Workflow is blocked waiting for approval
 * - `approval_granted`: User approved the plan or changes
 * - `approval_rejected`: User rejected the plan or changes
 *
 * **Artifact events**: File system changes
 * - `file_created`: A new file was created
 * - `file_modified`: An existing file was modified
 * - `file_deleted`: A file was deleted
 *
 * **Review cycle events**: Developer-reviewer interaction
 * - `review_requested`: Developer requested code review
 * - `review_completed`: Reviewer approved the changes
 * - `revision_requested`: Reviewer requested changes
 *
 * **System events**: Errors and warnings
 * - `system_error`: An error occurred during execution
 * - `system_warning`: A warning was issued
 */
export type EventType =
  // Lifecycle
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
  // System
  | 'system_error'
  | 'system_warning';

/**
 * A single event emitted during workflow execution.
 * Events are streamed in real-time via WebSocket and stored for historical viewing.
 */
export interface WorkflowEvent {
  /** Unique identifier for this event. */
  id: string;

  /** ID of the workflow this event belongs to. */
  workflow_id: string;

  /** Sequential event number within the workflow (monotonically increasing). */
  sequence: number;

  /** ISO 8601 timestamp when the event was emitted. */
  timestamp: string;

  /** Name of the agent that emitted this event (e.g., 'architect', 'developer'). */
  agent: string;

  /** Type of event that occurred. */
  event_type: EventType;

  /** Human-readable message describing the event. */
  message: string;

  /** Optional additional structured data specific to this event type. */
  data?: Record<string, unknown>;

  /** Optional correlation ID for grouping related events. */
  correlation_id?: string;
}

// ============================================================================
// Plan Types (TaskDAG)
// ============================================================================

/**
 * A single task node in the execution plan.
 * Represents one unit of work to be performed by an agent.
 */
export interface TaskNode {
  /** Unique identifier for this task. */
  id: string;

  /** Human-readable description of what this task should accomplish. */
  description: string;

  /** The agent responsible for executing this task. */
  agent: 'architect' | 'developer' | 'reviewer';

  /** List of task IDs that must complete before this task can start. */
  dependencies: string[];

  /** Current execution state of this task. */
  status: 'pending' | 'in_progress' | 'completed' | 'failed';

  /** Output or result from executing this task (populated after completion). */
  result?: string;

  /** Error message if the task failed (populated on failure). */
  error?: string;
}

/**
 * Directed Acyclic Graph (DAG) representing the execution plan.
 * Created by the architect agent and used to coordinate workflow execution.
 *
 * @example
 * ```typescript
 * const plan: TaskDAG = {
 *   tasks: [
 *     { id: 'task1', description: 'Setup', agent: 'developer', dependencies: [], status: 'completed' },
 *     { id: 'task2', description: 'Implement', agent: 'developer', dependencies: ['task1'], status: 'in_progress' }
 *   ],
 *   execution_order: ['task1', 'task2']
 * };
 * ```
 */
export interface TaskDAG {
  /** All tasks in the plan, including their dependencies and status. */
  tasks: TaskNode[];

  /** Topologically sorted list of task IDs representing valid execution order. */
  execution_order: string[];
}

// ============================================================================
// Token Usage Types
// ============================================================================

/**
 * Aggregated token usage and cost for an agent or workflow.
 * Provides a high-level summary without per-request details.
 */
export interface TokenSummary {
  /** Total number of tokens used (input + output + cache). */
  total_tokens: number;

  /** Total cost in USD for all token usage. */
  total_cost_usd: number;
}

/**
 * Detailed token usage information for a single LLM request.
 * Tracks input, output, and cache tokens separately for cost analysis.
 */
export interface TokenUsage {
  /** ID of the workflow this usage belongs to. */
  workflow_id: string;

  /** Name of the agent that made this request (e.g., 'architect', 'developer'). */
  agent: string;

  /** Name of the LLM model used (e.g., 'claude-sonnet-4-5', 'gpt-4'). */
  model: string;

  /** Number of input tokens sent to the model. */
  input_tokens: number;

  /** Number of output tokens generated by the model. */
  output_tokens: number;

  /** Number of tokens read from the prompt cache (not billed at full rate). */
  cache_read_tokens: number;

  /** Number of tokens written to the prompt cache. */
  cache_creation_tokens: number;

  /** Calculated cost in USD for this request, or null if pricing unavailable. */
  cost_usd: number | null;

  /** ISO 8601 timestamp when this request was made. */
  timestamp: string;
}

// ============================================================================
// API Response Types
// ============================================================================

/**
 * Response payload for listing workflows with pagination support.
 * Used by GET /api/workflows endpoint.
 *
 * @example
 * ```typescript
 * const response: WorkflowListResponse = {
 *   workflows: [{ id: 'wf1', issue_id: 'ISSUE-1', ... }],
 *   total: 42,
 *   cursor: 'eyJsYXN0X2lkIjogIndmMSJ9',
 *   has_more: true
 * };
 * ```
 */
export interface WorkflowListResponse {
  /** Array of workflow summaries for the current page. */
  workflows: WorkflowSummary[];

  /** Total number of workflows across all pages. */
  total: number;

  /** Opaque cursor token for fetching the next page, or null if no more pages. */
  cursor: string | null;

  /** Whether there are more workflows beyond this page. */
  has_more: boolean;
}

/**
 * Response payload for retrieving a single workflow's details.
 * Used by GET /api/workflows/:id endpoint.
 */
export type WorkflowDetailResponse = WorkflowDetail;

/**
 * Standard error response format for all API endpoints.
 * Returned with appropriate HTTP error status codes (4xx, 5xx).
 *
 * @example
 * ```typescript
 * const error: ErrorResponse = {
 *   error: 'Workflow not found',
 *   code: 'WORKFLOW_NOT_FOUND',
 *   details: { workflow_id: 'wf123' }
 * };
 * ```
 */
export interface ErrorResponse {
  /** Human-readable error message. */
  error: string;

  /** Machine-readable error code for programmatic handling. */
  code: string;

  /** Optional additional context about the error. */
  details?: Record<string, unknown>;
}

/**
 * Request payload for starting a new workflow.
 * Used by POST /api/workflows endpoint.
 *
 * @example
 * ```typescript
 * const request: StartWorkflowRequest = {
 *   issue_id: 'JIRA-123',
 *   profile: 'work',
 *   worktree_path: '/tmp/worktrees/jira-123'
 * };
 * ```
 */
export interface StartWorkflowRequest {
  /** Issue ID from the tracking system to work on. */
  issue_id: string;

  /** Optional profile name from settings.amelia.yaml (defaults to active profile). */
  profile?: string;

  /** Optional custom path for the git worktree (auto-generated if not provided). */
  worktree_path?: string;
}

/**
 * Request payload for rejecting a plan or review.
 * Used by POST /api/workflows/:id/reject endpoint.
 */
export interface RejectRequest {
  /** Human feedback explaining why the plan or changes were rejected. */
  feedback: string;
}

// ============================================================================
// WebSocket Message Types
// ============================================================================

/**
 * Messages sent from the server to the dashboard client over WebSocket.
 * The dashboard receives these messages to update the UI in real-time.
 *
 * @example
 * ```typescript
 * // Ping message (keepalive)
 * const ping: WebSocketMessage = { type: 'ping' };
 *
 * // Event message
 * const event: WebSocketMessage = {
 *   type: 'event',
 *   payload: { id: 'evt1', workflow_id: 'wf1', ... }
 * };
 *
 * // Backfill complete
 * const backfill: WebSocketMessage = { type: 'backfill_complete', count: 10 };
 * ```
 */
export type WebSocketMessage =
  | { type: 'ping' }
  | { type: 'event'; payload: WorkflowEvent }
  | { type: 'backfill_complete'; count: number }
  | { type: 'backfill_expired'; message: string };

/**
 * Messages sent from the dashboard client to the server over WebSocket.
 * The dashboard sends these messages to control subscriptions and respond to pings.
 *
 * @example
 * ```typescript
 * // Subscribe to a specific workflow
 * const subscribe: WebSocketClientMessage = {
 *   type: 'subscribe',
 *   workflow_id: 'wf123'
 * };
 *
 * // Subscribe to all workflows
 * const subscribeAll: WebSocketClientMessage = { type: 'subscribe_all' };
 *
 * // Respond to ping
 * const pong: WebSocketClientMessage = { type: 'pong' };
 * ```
 */
export type WebSocketClientMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' };

// ============================================================================
// UI State Types
// ============================================================================

/**
 * WebSocket connection state for the dashboard.
 * Tracks the current connection status and any errors that occurred.
 *
 * @example
 * ```typescript
 * // Successfully connected
 * const state: ConnectionState = { status: 'connected' };
 *
 * // Connection failed
 * const failedState: ConnectionState = {
 *   status: 'disconnected',
 *   error: 'Failed to connect to server'
 * };
 * ```
 */
export interface ConnectionState {
  /** Current WebSocket connection status. */
  status: 'connected' | 'disconnected' | 'connecting';

  /** Error message if connection failed, otherwise undefined. */
  error?: string;
}
