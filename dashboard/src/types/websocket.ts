/**
 * WebSocket message types and connection state.
 */

import type { BrainstormEventType, WorkflowEvent } from './events';

/**
 * A brainstorm streaming event from the server.
 *
 * Uses a flat format (no nested payload) for direct frontend handling. This is
 * the wire shape; the stored chat-message shape lives in `./api` as
 * `BrainstormMessage`.
 */
export interface BrainstormStreamEvent {
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
  | BrainstormStreamEvent;

/**
 * Messages sent from the dashboard client to the server over WebSocket.
 * The dashboard sends these messages to control subscriptions and respond to pings.
 */
export type WebSocketClientMessage =
  | { type: 'subscribe'; workflow_id: string }
  | { type: 'unsubscribe'; workflow_id: string }
  | { type: 'subscribe_all' }
  | { type: 'pong' };

/**
 * WebSocket connection state for the dashboard.
 * Tracks the current connection status and any errors that occurred.
 */
export interface ConnectionState {
  /** Current WebSocket connection status. */
  status: 'connected' | 'disconnected' | 'connecting';

  /** Error message if connection failed, otherwise undefined. */
  error?: string;
}
