/**
 * Additional TypeScript types for React Router loaders and actions.
 * Re-exports base types from Plan 08.
 * Keep in sync with amelia/server/models/*.py
 */

// Re-export all types from Plan 08 Task 8
export * from './index';

import type { WorkflowSummary, WorkflowDetail } from './index';

// ============================================================================
// React Router Loader Data Types
// ============================================================================

/**
 * Data returned by the workflows list route loader.
 * Used by the workflows index page to display all workflows.
 *
 * @example
 * ```typescript
 * export const loader = async (): Promise<WorkflowsLoaderData> => {
 *   const workflows = await fetchWorkflows();
 *   return { workflows };
 * };
 * ```
 */
export interface WorkflowsLoaderData {
  /** Array of workflow summaries to display in the list. */
  workflows: WorkflowSummary[];
  /** Pre-loaded detail for the selected or active workflow, or null if none/failed to load. */
  detail: WorkflowDetail | null;
  /** Error message if detail failed to load, null otherwise. */
  detailError?: string | null;
}

/**
 * Data returned by the workflow detail route loader.
 * Used by the workflow detail page to display a single workflow's information.
 *
 * @example
 * ```typescript
 * export const loader = async ({ params }): Promise<WorkflowDetailLoaderData> => {
 *   const workflow = await fetchWorkflow(params.id);
 *   return { workflow };
 * };
 * ```
 */
export interface WorkflowDetailLoaderData {
  /** Complete workflow details including events, plan, and token usage. */
  workflow: WorkflowDetail;
}

// ============================================================================
// React Router Action Result Types
// ============================================================================

/**
 * Result object returned by React Router actions (approve, reject, cancel).
 * Indicates whether the action succeeded and which action was performed.
 *
 * @property success - Whether the action was successfully executed
 * @property action - Which action was performed (approved, rejected, or cancelled)
 * @property error - Error message if the action failed, otherwise undefined
 *
 * @example
 * ```typescript
 * // Success case
 * const result: ActionResult = {
 *   success: true,
 *   action: 'approved'
 * };
 *
 * // Error case
 * const errorResult: ActionResult = {
 *   success: false,
 *   action: 'rejected',
 *   error: 'Server error: 500'
 * };
 * ```
 */
export interface ActionResult {
  /** Whether the action was successfully executed. */
  success: boolean;

  /** Which action was performed. */
  action: 'approved' | 'rejected' | 'cancelled' | 'resumed' | 'replanning';

  /** Error message if the action failed, otherwise undefined. */
  error?: string;
}

// ============================================================================
// Brainstorming Types
// ============================================================================

/** Token usage for a single message. */
export interface MessageUsage {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

/** Aggregated token usage for an entire session. */
export interface SessionUsageSummary {
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  message_count: number;
}

/** Status of a brainstorming session. */
export type SessionStatus = "active" | "ready_for_handoff" | "completed" | "failed";

/** A brainstorming session for exploring ideas before workflow execution. */
export interface BrainstormingSession {
  id: string;
  profile_id: string;
  driver_session_id: string | null;
  status: SessionStatus;
  topic: string | null;
  created_at: string;
  updated_at: string;
  usage_summary?: SessionUsageSummary;
}

/** A part of a brainstorm message (text, reasoning, tool call, or tool result). */
export interface MessagePart {
  type: "text" | "reasoning" | "tool-call" | "tool-result";
  text?: string;
  tool_name?: string;
  tool_call_id?: string;
  args?: Record<string, unknown>;
  result?: unknown;
}

/** State of a tool call for UI display. Matches ToolUIPart["state"] from Vercel AI SDK. */
export type ToolCallState = "input-available" | "output-available" | "output-error";

/** A tool call with its input and result for display in the chat UI. */
export interface ToolCall {
  /** Unique identifier for this tool call from the backend. */
  tool_call_id: string;
  /** Name of the tool being called. */
  tool_name: string;
  /** Input parameters passed to the tool. */
  input: unknown;
  /** Output result from the tool (populated when complete). */
  output?: unknown;
  /** Error text if the tool call failed. */
  errorText?: string;
  /** Current state of the tool call. */
  state: ToolCallState;
}

/** A message in a brainstorming session. */
export interface BrainstormMessage {
  id: string;
  session_id: string;
  sequence: number;
  role: "user" | "assistant";
  /** Whether this is a system-generated message (e.g., session welcome, handoff summary). */
  is_system?: boolean;
  content: string;
  reasoning?: string;
  parts: MessagePart[] | null;
  created_at: string;
  /** Streaming status: undefined = complete, 'streaming' = in progress, 'error' = failed */
  status?: "streaming" | "error";
  /** Human-readable error message when status is 'error' */
  errorMessage?: string;
  /** Tool calls made during this message (for UI display). */
  toolCalls?: ToolCall[];
  /** Token usage for this message. */
  usage?: MessageUsage;
}

/** An artifact generated during a brainstorming session. */
export interface BrainstormArtifact {
  id: string;
  session_id: string;
  type: string;
  path: string;
  title: string | null;
  created_at: string;
}

/** Profile information for display in UI. */
export interface ProfileInfo {
  name: string;
  driver: string;
  model: string;
}

/** Response from creating a new brainstorming session. */
export interface CreateSessionResponse {
  session: BrainstormingSession;
  profile?: ProfileInfo;
}

/** A complete brainstorming session with its message history and artifacts. */
export interface SessionWithHistory {
  session: BrainstormingSession;
  messages: BrainstormMessage[];
  artifacts: BrainstormArtifact[];
  profile?: ProfileInfo;
}
