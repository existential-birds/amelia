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

  /** Absolute filesystem path to the git worktree. */
  worktree_path: string;

  /** Profile name used for this workflow, or null if not set. */
  profile: string | null;

  /** Current execution state of the workflow. */
  status: WorkflowStatus;

  /** ISO 8601 timestamp when the workflow was created/queued. */
  created_at: string;

  /** ISO 8601 timestamp when the workflow started, or null if not yet started. */
  started_at: string | null;

  /** Total cost in USD for all token usage, or null if not available. */
  total_cost_usd: number | null;

  /** Total number of tokens used (input + output), or null if not available. */
  total_tokens: number | null;

  /** Total duration in milliseconds, or null if not available. */
  total_duration_ms: number | null;
}

/**
 * Complete detailed information about a workflow.
 * Extends WorkflowSummary with additional metadata, token usage, and event history.
 */
export interface WorkflowDetail extends WorkflowSummary {
  /** Absolute filesystem path to the git worktree. */
  worktree_path: string;

  /** ISO 8601 timestamp when the workflow completed, or null if still running. */
  completed_at: string | null;

  /** Human-readable error message if the workflow failed, otherwise null. */
  failure_reason: string | null;

  /** Token usage summary with breakdown by agent, or null if not available. */
  token_usage: TokenSummary | null;

  /** Recent workflow events for this workflow, ordered by sequence number. */
  recent_events: WorkflowEvent[];

  // Agentic execution fields
  /** High-level goal or task description for the developer. */
  goal: string | null;

  /** Full plan markdown content from the Architect agent. */
  plan_markdown: string | null;

  /** Path to the markdown plan file, if generated. */
  plan_path: string | null;
}

// ============================================================================
// Event Types
// ============================================================================

/**
 * Severity level for workflow events.
 * Used to filter and categorize events in the UI.
 *
 * - `info`: High-level workflow progress (lifecycle, stages, approvals)
 * - `debug`: Detailed operational information (file changes, agent messages)
 * - `trace`: Fine-grained execution details (tool calls, LLM thinking)
 */
export type EventLevel = 'info' | 'debug' | 'trace';

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
 * **Agent messages**: Task-level messages and status updates
 * - `agent_message`: A message from an agent during task execution
 * - `task_started`: A task has started execution
 * - `task_completed`: A task has completed successfully
 * - `task_failed`: A task has failed with an error
 *
 * **System events**: Errors and warnings
 * - `system_error`: An error occurred during execution
 * - `system_warning`: A warning was issued
 *
 * **Trace events**: Stream events for fine-grained execution details
 * - `claude_thinking`: LLM reasoning/thinking content
 * - `claude_tool_call`: Tool invocation by the LLM
 * - `claude_tool_result`: Result from a tool execution
 * - `agent_output`: Final output from an agent
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
  | 'oracle_consultation_failed';

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

// ============================================================================
// Token Usage Types
// ============================================================================

/**
 * Detailed token usage information for a single LLM request.
 * Tracks input, output, and cache tokens separately for cost analysis.
 */
export interface TokenUsage {
  /** Unique identifier for this token usage record. */
  id: string;

  /** ID of the workflow this usage belongs to. */
  workflow_id: string;

  /** Name of the agent that made this request. */
  agent: 'architect' | 'developer' | 'reviewer';

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

  /** Calculated cost in USD for this request. */
  cost_usd: number;

  /** Duration of the request in milliseconds. */
  duration_ms: number;

  /** Number of turns (conversation exchanges) in this request. */
  num_turns: number;

  /** ISO 8601 timestamp when this request was made. */
  timestamp: string;
}

/**
 * Aggregated token usage and cost for a workflow.
 * Provides a high-level summary with per-agent breakdown.
 */
export interface TokenSummary {
  /** Total number of input tokens across all requests. */
  total_input_tokens: number;

  /** Total number of output tokens across all requests. */
  total_output_tokens: number;

  /** Total number of cache read tokens across all requests. */
  total_cache_read_tokens: number;

  /** Total cost in USD for all token usage. */
  total_cost_usd: number;

  /** Total duration in milliseconds across all requests. */
  total_duration_ms: number;

  /** Total number of turns across all requests. */
  total_turns: number;

  /** Detailed breakdown of token usage by agent. */
  breakdown: TokenUsage[];
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
 * Request payload for creating a new workflow via Quick Shot.
 * Used by POST /api/workflows endpoint.
 *
 * @example
 * ```typescript
 * const request: CreateWorkflowRequest = {
 *   issue_id: 'TASK-001',
 *   worktree_path: '/Users/me/projects/repo',
 *   profile: 'noop-local',
 *   task_title: 'Add logout button',
 *   task_description: 'Add a logout button to the navbar...'
 * };
 * ```
 */
export interface CreateWorkflowRequest {
  /** Task identifier (maps to issue_id in API). */
  issue_id: string;

  /** Absolute filesystem path to the git worktree. */
  worktree_path: string;

  /** Optional profile name from settings.amelia.yaml. */
  profile?: string;

  /** Human-readable title for the task. */
  task_title: string;

  /** Detailed description of the task (defaults to title if empty). */
  task_description?: string;

  /** Whether to start the workflow immediately. Default: true. */
  start?: boolean;

  /** If not starting, run Architect first to generate a plan. Default: false. */
  plan_now?: boolean;

  /** Path to external plan file (relative to worktree or absolute). */
  plan_file?: string;

  /** Inline plan markdown content. */
  plan_content?: string;
}

/**
 * Response payload from creating a new workflow.
 * Returned by POST /api/workflows endpoint.
 */
export interface CreateWorkflowResponse {
  /** Unique identifier for the created workflow. */
  id: string;

  /** Initial workflow status (usually 'pending'). */
  status: string;

  /** Human-readable confirmation message. */
  message: string;
}

/**
 * Request payload for rejecting a plan or review.
 * Used by POST /api/workflows/:id/reject endpoint.
 */
export interface RejectRequest {
  /** Human feedback explaining why the plan or changes were rejected. */
  feedback: string;
}

/**
 * Response payload from starting a single pending workflow.
 * Returned by POST /api/workflows/:id/start endpoint.
 */
export interface StartWorkflowResponse {
  /** Unique identifier for the started workflow. */
  workflow_id: string;

  /** Status after starting (usually 'started' or 'in_progress'). */
  status: string;
}

/**
 * Request payload for batch starting queued workflows.
 * Used by POST /api/workflows/start-batch endpoint.
 *
 * @example
 * ```typescript
 * // Start specific workflows
 * const request: BatchStartRequest = {
 *   workflow_ids: ['wf-1', 'wf-2'],
 * };
 *
 * // Start all queued workflows for a worktree
 * const request: BatchStartRequest = {
 *   worktree_path: '/path/to/repo',
 * };
 * ```
 */
export interface BatchStartRequest {
  /** Optional list of specific workflow IDs to start. */
  workflow_ids?: string[];

  /** Optional worktree path to filter workflows. */
  worktree_path?: string;
}

/**
 * Response payload from batch starting workflows.
 * Returned by POST /api/workflows/start-batch endpoint.
 */
export interface BatchStartResponse {
  /** List of workflow IDs that were successfully started. */
  started: string[];

  /** Map of workflow IDs to error messages for workflows that failed to start. */
  errors: Record<string, string>;
}

/**
 * Request payload for setting or replacing the plan for a queued workflow.
 * Used by POST /api/workflows/:id/plan endpoint.
 *
 * Note: `plan_file` and `plan_content` are mutually exclusive - provide one or the other, not both.
 *
 * @example
 * ```typescript
 * // Set plan from file
 * const request: SetPlanRequest = {
 *   plan_file: 'docs/plans/feature-plan.md',
 * };
 *
 * // Set plan from inline content
 * const request: SetPlanRequest = {
 *   plan_content: '# Plan\n\n### Task 1: Do thing',
 *   force: true,
 * };
 * ```
 */
export interface SetPlanRequest {
  /** Path to external plan file (relative to worktree or absolute). */
  plan_file?: string;

  /** Inline plan markdown content. */
  plan_content?: string;

  /** If true, overwrite existing plan. */
  force?: boolean;
}

/**
 * Response payload from setting a workflow's plan.
 * Returned by POST /api/workflows/:id/plan endpoint.
 */
export interface SetPlanResponse {
  /** Extracted goal from the plan. */
  goal: string;

  /** List of key files from the plan. */
  key_files: string[];

  /** Number of tasks in the plan. */
  total_tasks: number;
}

// ============================================================================
// WebSocket Message Types
// ============================================================================

/**
 * Event types for brainstorm streaming messages.
 */
export type BrainstormEventType =
  | 'text'
  | 'reasoning'
  | 'tool_call'
  | 'tool_result'
  | 'message_complete'
  | 'artifact_created'
  | 'session_created'
  | 'session_completed';

/**
 * Brainstorm streaming message from the server.
 * Uses a flat format (no nested payload) for direct handling.
 */
export interface BrainstormMessage {
  type: 'brainstorm';
  event_type: BrainstormEventType;
  session_id: string;
  message_id?: string;
  data: Record<string, unknown>;
  timestamp: string;
}

/**
 * Messages sent from the server to the dashboard client over WebSocket.
 */
export type WebSocketMessage =
  | { type: 'ping' }
  | { type: 'event'; payload: WorkflowEvent }
  | { type: 'backfill_complete'; count: number }
  | { type: 'backfill_expired'; message: string }
  | BrainstormMessage;

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

// ============================================================================
// Prompt Types
// ============================================================================

/**
 * Summary of a prompt for list views.
 */
export interface PromptSummary {
  /** Unique identifier for the prompt. */
  id: string;
  /** Agent type this prompt belongs to (e.g., "architect", "developer"). */
  agent: string;
  /** Human-readable name of the prompt. */
  name: string;
  /** Optional description explaining the prompt's purpose. */
  description: string | null;
  /** ID of the currently active version, or null if using default. */
  current_version_id: string | null;
  /** Version number of the current version, or null if using default. */
  current_version_number: number | null;
}

/**
 * Summary of a prompt version.
 */
export interface VersionSummary {
  /** Unique identifier for this version. */
  id: string;
  /** Sequential version number (1, 2, 3, etc.). */
  version_number: number;
  /** ISO 8601 timestamp when this version was created. */
  created_at: string;
  /** Optional note describing changes in this version. */
  change_note: string | null;
}

/**
 * Detailed prompt with version history.
 */
export interface PromptDetail {
  /** Unique identifier for the prompt. */
  id: string;
  /** Agent type this prompt belongs to (e.g., "architect", "developer"). */
  agent: string;
  /** Human-readable name of the prompt. */
  name: string;
  /** Optional description explaining the prompt's purpose. */
  description: string | null;
  /** ID of the currently active version, or null if using default. */
  current_version_id: string | null;
  /** List of all versions for this prompt, ordered by version number. */
  versions: VersionSummary[];
}

/**
 * Full version details including content.
 */
export interface VersionDetail {
  /** Unique identifier for this version. */
  id: string;
  /** ID of the parent prompt this version belongs to. */
  prompt_id: string;
  /** Sequential version number (1, 2, 3, etc.). */
  version_number: number;
  /** Full prompt content text. */
  content: string;
  /** ISO 8601 timestamp when this version was created. */
  created_at: string;
  /** Optional note describing changes in this version. */
  change_note: string | null;
}

/**
 * Default content for a prompt.
 */
export interface DefaultContent {
  /** ID of the prompt this default belongs to. */
  prompt_id: string;
  /** Default prompt content text (built-in, not customized). */
  content: string;
  /** Human-readable name of the prompt. */
  name: string;
  /** Description explaining the prompt's purpose. */
  description: string;
}

// ============================================================================
// Config API Types
// ============================================================================

/**
 * Profile information for display in UI.
 * Contains driver and model configuration.
 */
export interface ConfigProfileInfo {
  /** Profile name. */
  name: string;

  /** Driver type ('api' or 'cli'). */
  driver: string;

  /** Model name. */
  model: string;
}

/**
 * Response from GET /api/config endpoint.
 * Provides server configuration for dashboard.
 */
export interface ConfigResponse {
  /** Working directory for file access. */
  working_dir: string;

  /** Maximum concurrent workflows. */
  max_concurrent: number;

  /** Active profile name from settings.amelia.yaml. */
  active_profile: string;

  /** Full profile info for the active profile. */
  active_profile_info: ConfigProfileInfo | null;
}

// ============================================================================
// Files API Types
// ============================================================================

/**
 * Request payload for reading a file.
 * Used by POST /api/files/read endpoint.
 */
export interface FileReadRequest {
  /** Absolute path to the file to read. */
  path: string;
}

/**
 * Response from POST /api/files/read endpoint.
 * Returns file content for design document import.
 */
export interface FileReadResponse {
  /** File content as text. */
  content: string;

  /** Filename without path. */
  filename: string;
}

// ============================================================================
// Path Validation API Types
// ============================================================================

/**
 * Request payload for validating a worktree path.
 * Used by POST /api/paths/validate endpoint.
 */
export interface PathValidationRequest {
  /** Absolute path to validate. */
  path: string;
}

/**
 * Response from POST /api/paths/validate endpoint.
 * Provides detailed information about a filesystem path.
 */
export interface PathValidationResponse {
  /** Whether the path exists on disk. */
  exists: boolean;

  /** Whether the path is a git repository. */
  is_git_repo: boolean;

  /** Current branch name if git repo. */
  branch?: string;

  /** Repository name (directory name). */
  repo_name?: string;

  /** Whether there are uncommitted changes. */
  has_changes?: boolean;

  /** Human-readable status message. */
  message: string;
}

// ============================================================================
// Usage API Types
// ============================================================================

/**
 * Summary statistics for the usage endpoint.
 */
export interface UsageSummary {
  /** Total cost in USD for the period. */
  total_cost_usd: number;
  /** Total number of workflows in the period. */
  total_workflows: number;
  /** Total tokens (input + output) in the period. */
  total_tokens: number;
  /** Total duration in milliseconds. */
  total_duration_ms: number;
  /** Cache hit rate (0-1), optional for efficiency metrics. */
  cache_hit_rate?: number;
  /** Savings from caching in USD, optional for efficiency metrics. */
  cache_savings_usd?: number;
  /** Cost from previous period for comparison, null if no prior data. */
  previous_period_cost_usd?: number | null;
  /** Number of workflows that completed successfully. */
  successful_workflows?: number | null;
  /** Success rate (0-1), successful_workflows / total_workflows. */
  success_rate?: number | null;
}

/**
 * Daily trend data point.
 */
export interface UsageTrendPoint {
  /** ISO date string (YYYY-MM-DD). */
  date: string;
  /** Cost in USD for this date. */
  cost_usd: number;
  /** Number of workflows on this date. */
  workflows: number;
  /** Per-model cost breakdown (model name -> cost in USD). */
  by_model?: Record<string, number>;
}

/**
 * Usage breakdown by model.
 */
export interface UsageByModel {
  /** Model name (e.g., "claude-sonnet-4"). */
  model: string;
  /** Number of workflows using this model. */
  workflows: number;
  /** Total tokens for this model. */
  tokens: number;
  /** Total cost in USD for this model. */
  cost_usd: number;
  /** Cache hit rate (0-1), optional for efficiency metrics. */
  cache_hit_rate?: number;
  /** Savings from caching in USD, optional for efficiency metrics. */
  cache_savings_usd?: number;
  /** Daily cost array for sparkline visualization. */
  trend?: number[];
  /** Number of workflows that completed successfully. */
  successful_workflows?: number | null;
  /** Success rate (0-1), successful_workflows / workflows. */
  success_rate?: number | null;
}

/**
 * Response from GET /api/usage endpoint.
 */
export interface UsageResponse {
  /** Aggregated summary statistics. */
  summary: UsageSummary;
  /** Daily trend data points. */
  trend: UsageTrendPoint[];
  /** Breakdown by model. */
  by_model: UsageByModel[];
}
