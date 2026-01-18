import { useCallback, useEffect, useRef } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import { useBrainstormStore } from '../store/brainstormStore';
import type { WebSocketMessage, WorkflowEvent, BrainstormMessage } from '../types';
import type { BrainstormArtifact } from '../types/api';

/**
 * Derive WebSocket URL from window.location.
 * Converts HTTP protocol to WS, HTTPS to WSS. Uses current host with /ws/events path.
 * Falls back to localhost:8420 in SSR/test environments where window is undefined.
 *
 * @returns WebSocket URL (ws://host/ws/events or wss://host/ws/events)
 */
function deriveWebSocketUrl(): string {
  // Handle SSR/tests where window might not exist
  if (typeof window === 'undefined') {
    return 'ws://localhost:8420/ws/events';
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}/ws/events`;
}

/**
 * Base URL for the WebSocket connection.
 * Priority: VITE_WS_BASE_URL env var, then derived from window.location, then fallback.
 */
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || deriveWebSocketUrl();

/**
 * Maximum delay between reconnection attempts in milliseconds (30 seconds).
 */
const MAX_RECONNECT_DELAY = 30000; // 30 seconds

/**
 * Initial delay for the first reconnection attempt in milliseconds (1 second).
 */
const INITIAL_RECONNECT_DELAY = 1000; // 1 second

/**
 * Handle incoming brainstorm streaming events.
 * Routes events to the brainstormStore based on event_type.
 *
 * @param msg - The brainstorm message from the WebSocket
 */
export function handleBrainstormMessage(msg: BrainstormMessage): void {
  const state = useBrainstormStore.getState();

  // Ignore events for different sessions
  if (msg.session_id !== state.activeSessionId) return;

  switch (msg.event_type) {
    case 'text':
      if (msg.message_id) {
        state.updateMessage(msg.message_id, (m) => ({
          ...m,
          content: m.content + ((msg.data.text as string) ?? ''),
        }));
      }
      break;

    case 'reasoning':
      if (msg.message_id) {
        state.updateMessage(msg.message_id, (m) => ({
          ...m,
          reasoning: (m.reasoning ?? '') + ((msg.data.text as string) ?? ''),
        }));
      }
      break;

    case 'message_complete': {
      const error = msg.data.error as string | undefined;
      if (msg.message_id) {
        state.updateMessage(msg.message_id, (m) => ({
          ...m,
          status: error ? 'error' : undefined,
          errorMessage: error,
        }));
      }
      state.setStreaming(false, null);
      break;
    }

    case 'artifact_created': {
      const artifact = msg.data.artifact as BrainstormArtifact | undefined;
      if (artifact) {
        state.addArtifact(artifact);
        state.updateSession(msg.session_id, { status: 'ready_for_handoff' });
      }
      break;
    }

    // tool_call, tool_result, session_created, session_completed can be
    // handled later as needed
    default:
      break;
  }
}

/**
 * WebSocket hook for real-time workflow events.
 *
 * Manages WebSocket connection lifecycle with automatic reconnection and event handling:
 * - Auto-connects on mount and subscribes to all workflows
 * - Handles reconnection with exponential backoff (1s, 2s, 4s, ..., max 30s)
 * - Detects sequence gaps in events and logs warnings
 * - Updates Zustand store with incoming workflow events
 * - Dispatches custom 'workflow-event' DOM events for revalidation hints
 * - Supports event backfill using the ?since= query parameter
 *
 * @returns An object containing a manual reconnect function.
 *
 * @example
 * ```tsx
 * function App() {
 *   const { reconnect } = useWebSocket();
 *
 *   return (
 *     <div>
 *       <button onClick={reconnect}>Reconnect</button>
 *     </div>
 *   );
 * }
 * ```
 */
export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const lastSequenceRef = useRef<Map<string, number>>(new Map());
  // Store connect function in a ref to allow scheduleReconnect to call it
  // without creating a circular dependency
  const connectRef = useRef<() => void>(() => {});

  const addEvent = useWorkflowStore((state) => state.addEvent);
  const setConnected = useWorkflowStore((state) => state.setConnected);
  const setLastEventId = useWorkflowStore((state) => state.setLastEventId);

  /**
   * Handle incoming workflow events.
   * - Check for sequence gaps
   * - Update last sequence tracker
   * - Add event to store
   * - Dispatch custom event for revalidation hints
   */
  const handleEvent = useCallback(
    (event: WorkflowEvent) => {
      const workflowId = event.workflow_id;
      const lastSequence = lastSequenceRef.current.get(workflowId);

      // Detect sequence gaps
      if (lastSequence !== undefined && event.sequence !== lastSequence + 1) {
        console.warn('Sequence gap detected', {
          workflow_id: workflowId,
          expected: lastSequence + 1,
          received: event.sequence,
        });
      }

      // Update sequence tracker
      lastSequenceRef.current.set(workflowId, event.sequence);

      // Add to store
      addEvent(event);

      // Dispatch custom event for revalidation hints
      window.dispatchEvent(
        new CustomEvent('workflow-event', {
          detail: event,
        })
      );
    },
    [addEvent]
  );

  /**
   * Schedule reconnection with exponential backoff.
   * Uses connectRef to avoid circular dependency with connect.
   */
  const scheduleReconnect = useCallback(() => {
    // Clear any existing timeout
    if (reconnectTimeoutRef.current !== null) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    // Calculate delay with exponential backoff (1s, 2s, 4s, 8s, ..., max 30s)
    const delay = Math.min(
      INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttemptRef.current),
      MAX_RECONNECT_DELAY
    );

    reconnectAttemptRef.current += 1;

    reconnectTimeoutRef.current = window.setTimeout(() => {
      connectRef.current();
    }, delay);
  }, []);

  /**
   * Connect to WebSocket server.
   */
  const connect = useCallback(() => {
    // Build URL with optional ?since= parameter for backfill
    let url = WS_BASE_URL;
    const currentLastEventId = useWorkflowStore.getState().lastEventId;
    if (currentLastEventId) {
      url += `?since=${encodeURIComponent(currentLastEventId)}`;
    }

    // Create WebSocket
    const ws = new WebSocket(url);
    wsRef.current = ws;

    // Connection opened
    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
      reconnectAttemptRef.current = 0; // Reset reconnect counter

      // Subscribe to all workflows
      ws.send(JSON.stringify({ type: 'subscribe_all' }));
    };

    // Message received
    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);

        switch (message.type) {
          case 'event':
            handleEvent(message.payload);
            break;

          case 'ping':
            ws.send(JSON.stringify({ type: 'pong' }));
            break;

          case 'backfill_complete':
            console.log('Backfill complete', message.count);
            break;

          case 'backfill_expired':
            console.warn('Backfill expired:', message.message);
            setLastEventId(null);
            break;

          case 'brainstorm':
            handleBrainstormMessage(message);
            break;

          default:
            console.warn('Unknown WebSocket message type:', message);
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    // Connection closed
    ws.onclose = (event) => {
      console.log('WebSocket disconnected', event.code, event.reason);
      setConnected(false);
      wsRef.current = null;

      // Reconnect unless it was a normal closure
      if (event.code !== 1000) {
        scheduleReconnect();
      }
    };

    // Error occurred
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false, 'WebSocket error');
    };
  }, [handleEvent, scheduleReconnect, setConnected, setLastEventId]);

  // Keep connectRef in sync with connect
  connectRef.current = connect;

  /**
   * Manual reconnect function (for external use if needed).
   */
  const reconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    reconnectAttemptRef.current = 0;
    connect();
  }, [connect]);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();

    return () => {
      // Clear reconnect timeout
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
      }

      // Close WebSocket
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { reconnect };
}
