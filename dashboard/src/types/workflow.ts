/**
 * Workflow domain types and their request/response shapes.
 * Mirrors the Python Pydantic models in `amelia/server/models/`.
 */

import type { TokenSummary } from './tokens';

/**
 * The current execution state of a workflow.
 *
 * - `pending`: Workflow has been created but not yet started
 * - `in_progress`: Workflow is actively executing
 * - `blocked`: Workflow is waiting for human approval or input
 * - `completed`: Workflow finished successfully
 * - `failed`: Workflow encountered an error and stopped
 * - `cancelled`: Workflow was manually cancelled by a user
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

  /** Pipeline type: "full", "review", "pr_auto_fix", or null for legacy workflows. */
  pipeline_type: string | null;

  /** PR number for PR Fix workflows, null otherwise. */
  pr_number: number | null;

  /** PR title for PR Fix workflows, null otherwise. */
  pr_title: string | null;

  /** Comment count for PR Fix workflows, null otherwise. */
  pr_comment_count: number | null;
}

/**
 * Complete detailed information about a workflow.
 * Extends WorkflowSummary with additional metadata and token usage.
 */
export interface WorkflowDetail extends WorkflowSummary {
  /** ISO 8601 timestamp when the workflow completed, or null if still running. */
  completed_at: string | null;

  /** Human-readable error message if the workflow failed, otherwise null. */
  failure_reason: string | null;

  /** Token usage summary with breakdown by agent, or null if not available. */
  token_usage: TokenSummary | null;

  // Agentic execution fields
  /** High-level goal or task description for the developer. */
  goal: string | null;

  /** Full plan markdown content from the Architect agent. */
  plan_markdown: string | null;

  /** Path to the markdown plan file, if generated. */
  plan_path: string | null;

  /** PR comments with resolution status, only present for pr_auto_fix workflows. */
  pr_comments: PRCommentData[] | null;

  /** Client-enriched flag derived from recent_events.workflow_failed.data.recoverable. */
  recoverable?: boolean;
}

/**
 * Minimal recent event shape returned with raw workflow detail API responses.
 */
export interface WorkflowDetailRecentEvent {
  /** Type of event that occurred. */
  event_type: string;

  /** Sequential event number within the workflow. */
  sequence: number;

  /** Optional additional structured data specific to this event type. */
  data?: Record<string, unknown>;
}

/**
 * Data for a single PR review comment with resolution status.
 * Used in the PR auto-fix workflow detail view.
 */
export interface PRCommentData {
  /** GitHub comment ID. */
  comment_id: number;

  /** File path the comment is attached to, or null for general comments. */
  file_path: string | null;

  /** Line number the comment is attached to, or null for general comments. */
  line: number | null;

  /** Comment body text (truncated to 200 chars). */
  body: string;

  /** GitHub username of the comment author. */
  author: string;

  /** Resolution status of the comment. */
  status: 'fixed' | 'failed' | 'skipped';

  /** Reason for the resolution status, or null if not applicable. */
  status_reason: string | null;

  /** GitHub URL for the comment. */
  html_url: string;
}

/**
 * Response payload for listing workflows with pagination support.
 * Used by GET /api/workflows endpoint.
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
 * Raw backend payload for retrieving a single workflow's details.
 * Used by GET /api/workflows/:id before client-side enrichment.
 */
export interface WorkflowDetailApiResponse extends Omit<WorkflowDetail, 'recoverable'> {
  /** Recent workflow events from the backend response. */
  recent_events: WorkflowDetailRecentEvent[];
}

/**
 * Client-enriched workflow detail returned by api.getWorkflow().
 * Keeps the existing response alias for dashboard consumers.
 */
export type WorkflowDetailResponse = WorkflowDetail;

/**
 * Request payload for creating a new workflow.
 * Used by POST /api/workflows endpoint.
 */
export interface CreateWorkflowRequest {
  /** Task identifier (maps to issue_id in API). */
  issue_id: string;

  /** Absolute filesystem path to the git worktree. */
  worktree_path: string;

  /** Optional profile name from settings.amelia.yaml. */
  profile?: string;

  /** Human-readable title for the task. Skips tracker fetch when provided. */
  task_title?: string;

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
  status: WorkflowStatus;

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

  /** Status after starting (usually 'started'). */
  status: string;
}

/**
 * Request payload for batch starting queued workflows.
 * Used by POST /api/workflows/start-batch endpoint.
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
  /** 'ready' when plan is valid, 'invalid' when validation fails. */
  status: 'ready' | 'invalid';

  /** Number of tasks in the plan. */
  total_tasks: number;

  /** Extracted goal from the plan. */
  goal: string;

  /** List of key files from the plan. */
  key_files: string[];

  /** Validation issues (present when status is 'invalid'). */
  validation_issues?: string[];
}

/**
 * Request payload for requesting an on-demand code review.
 * Used by POST /api/workflows/:id/review endpoint.
 */
export interface RequestReviewRequest {
  /** Review mode: review only or review and fix. */
  mode: 'review_only' | 'review_fix';
  /** Review types to run (e.g., 'general', 'security'). Defaults to ['general'] on the backend. */
  review_types: string[];
  /** Optional base commit SHA for the diff. */
  base_commit?: string;
}

/** Response from POST /api/descriptions/condense. */
export interface CondenseDescriptionResponse {
  condensed: string;
}
