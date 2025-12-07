/**
 * Shared TypeScript types for the Amelia Dashboard.
 * These types mirror the Python Pydantic models from the backend API.
 */

// ============================================================================
// Workflow Types
// ============================================================================

export type WorkflowStatus =
  | 'pending'
  | 'in_progress'
  | 'blocked'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface WorkflowSummary {
  id: string;
  issue_id: string;
  worktree_name: string;
  status: WorkflowStatus;
  started_at: string | null;
  current_stage: string | null;
}

export interface WorkflowDetail extends WorkflowSummary {
  failure_reason: string | null;
  plan: TaskDAG | null;
  token_usage: Record<string, TokenSummary>;
  recent_events: WorkflowEvent[];
}

// ============================================================================
// Event Types
// ============================================================================

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

export interface WorkflowEvent {
  id: string;
  workflow_id: string;
  sequence: number;
  timestamp: string;
  agent: string;
  event_type: EventType;
  message: string;
  data?: Record<string, unknown>;
  correlation_id?: string;
}

// ============================================================================
// Plan Types (TaskDAG)
// ============================================================================

export interface TaskNode {
  id: string;
  description: string;
  agent: 'architect' | 'developer' | 'reviewer';
  dependencies: string[];
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  result?: string;
  error?: string;
}

export interface TaskDAG {
  tasks: TaskNode[];
  execution_order: string[];
}

// ============================================================================
// Token Usage Types
// ============================================================================

export interface TokenSummary {
  total_tokens: number;
  total_cost_usd: number;
}

export interface TokenUsage {
  workflow_id: string;
  agent: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cost_usd: number | null;
  timestamp: string;
}

// ============================================================================
// API Response Types
// ============================================================================

export interface WorkflowListResponse {
  workflows: WorkflowSummary[];
  total: number;
  cursor: string | null;
  has_more: boolean;
}

export interface ErrorResponse {
  error: string;
  code: string;
  details?: Record<string, unknown>;
}

export interface StartWorkflowRequest {
  issue_id: string;
  profile?: string;
  worktree_path?: string;
}

export interface RejectRequest {
  feedback: string;
}

// ============================================================================
// WebSocket Message Types
// ============================================================================

// Server → Client messages (messages received by the dashboard)
export type WebSocketMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' }
  | { type: 'ping' }
  | { type: 'event'; data: WorkflowEvent }
  | { type: 'backfill_complete'; count: number }
  | { type: 'backfill_expired'; message: string };

// Client → Server messages (messages sent by the dashboard)
export type WebSocketClientMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' };

// ============================================================================
// UI State Types
// ============================================================================

export interface ConnectionState {
  status: 'connected' | 'disconnected' | 'connecting';
  error?: string;
}
