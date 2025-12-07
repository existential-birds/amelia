import { useEffect, useRef } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import type { WebSocketMessage, WorkflowEvent } from '../types';

/**
 * Base URL for the WebSocket connection.
 * Defaults to ws://localhost:8420/ws/events if VITE_WS_BASE_URL is not set.
 */
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8420/ws/events';

/**
 * Maximum delay between reconnection attempts in milliseconds (30 seconds).
 */
const MAX_RECONNECT_DELAY = 30000; // 30 seconds

/**
 * Initial delay for the first reconnection attempt in milliseconds (1 second).
 */
const INITIAL_RECONNECT_DELAY = 1000; // 1 second

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
  const handleEvent = (event: WorkflowEvent) => {
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
  };

  /**
   * Schedule reconnection with exponential backoff.
   */
  const scheduleReconnect = () => {
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
      connect();
    }, delay);
  };

  /**
   * Connect to WebSocket server.
   */
  const connect = () => {
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
  };

  /**
   * Manual reconnect function (for external use if needed).
   */
  const reconnect = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    reconnectAttemptRef.current = 0;
    connect();
  };

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { reconnect };
}
