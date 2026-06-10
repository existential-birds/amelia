import { useCallback, useEffect, useRef } from 'react';
import { z } from 'zod';
import { useWorkflowStore } from '../store/workflowStore';
import { useBrainstormStore } from '../store/brainstormStore';
import type { WebSocketMessage, WorkflowEvent, BrainstormStreamEvent } from '../types';
import type { AskUserQuestionItem, BrainstormArtifact, ToolCall, MessageUsage, SessionUsageSummary } from '../types/api';
import * as Toast from '../components/Toast';
import { logger } from '../lib/logger';

/**
 * Zod schemas intentionally duplicate TypeScript types for runtime validation.
 * WebSocket data is untrusted - TypeScript only provides compile-time checks,
 * but we need runtime validation to safely parse incoming messages.
 */

/** Zod schema for AskUserOption validation (mirrors AskUserOption type). */
const askUserOptionSchema = z.object({
  label: z.string(),
  description: z.string().optional(),
});

/** Zod schema for AskUserQuestionItem validation (mirrors AskUserQuestionItem type). */
const askUserQuestionItemSchema = z.object({
  question: z.string(),
  header: z.string().optional(),
  options: z.array(askUserOptionSchema),
  multi_select: z.boolean(),
}) satisfies z.ZodType<AskUserQuestionItem>;

/** Zod schema for validating an array of AskUserQuestionItem. */
const askUserQuestionsSchema = z.array(askUserQuestionItemSchema);

/** Zod schema for validating optional text field. */
const optionalTextSchema = z.string().optional();

/** Zod schema for MessageUsage validation (mirrors MessageUsage type). */
const messageUsageSchema = z.object({
  input_tokens: z.number(),
  output_tokens: z.number(),
  cost_usd: z.number(),
}) satisfies z.ZodType<MessageUsage>;

/** Zod schema for SessionUsageSummary validation (mirrors SessionUsageSummary type). */
const sessionUsageSummarySchema = z.object({
  total_input_tokens: z.number(),
  total_output_tokens: z.number(),
  total_cost_usd: z.number(),
  message_count: z.number(),
}) satisfies z.ZodType<SessionUsageSummary>;

/** Zod schema for BrainstormArtifact validation (mirrors BrainstormArtifact type). */
const brainstormArtifactSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  type: z.string(),
  path: z.string(),
  title: z.string().nullable(),
  created_at: z.string(),
}) satisfies z.ZodType<BrainstormArtifact>;

/** Zod schema for ToolCall validation (mirrors ToolCall type). */
const toolCallSchema = z.object({
  tool_call_id: z.string(),
  tool_name: z.string(),
  input: z.unknown().optional(),
});

/**
 * Validates that a value is a string, returning undefined if invalid.
 */
function validateText(data: unknown): string | undefined {
  const result = optionalTextSchema.safeParse(data);
  if (!result.success) {
    logger.warn('Text validation failed', { error: result.error.format(), data });
  }
  return result.success ? result.data : undefined;
}

/**
 * Validates that a value is a MessageUsage object, returning undefined if invalid.
 */
function validateMessageUsage(data: unknown): MessageUsage | undefined {
  const result = messageUsageSchema.safeParse(data);
  if (!result.success) {
    logger.warn('MessageUsage validation failed', { error: result.error.format(), data });
  }
  return result.success ? result.data : undefined;
}

/**
 * Validates that a value is a SessionUsageSummary object, returning undefined if invalid.
 */
function validateSessionUsageSummary(data: unknown): SessionUsageSummary | undefined {
  const result = sessionUsageSummarySchema.safeParse(data);
  if (!result.success) {
    logger.warn('SessionUsageSummary validation failed', { error: result.error.format(), data });
  }
  return result.success ? result.data : undefined;
}

/**
 * Validates that a value is a BrainstormArtifact object, returning undefined if invalid.
 */
function validateBrainstormArtifact(data: unknown): BrainstormArtifact | undefined {
  const result = brainstormArtifactSchema.safeParse(data);
  if (!result.success) {
    logger.warn('BrainstormArtifact validation failed', { error: result.error.format(), data });
  }
  return result.success ? result.data : undefined;
}

/**
 * Validates that a value is a ToolCall object with required fields, returning undefined if invalid.
 */
function validateToolCall(data: unknown): Pick<ToolCall, 'tool_call_id' | 'tool_name' | 'input'> | undefined {
  const result = toolCallSchema.safeParse(data);
  if (!result.success) {
    logger.warn('ToolCall validation failed', { error: result.error.format(), data });
  }
  return result.success ? result.data : undefined;
}

/**
 * Module-level timestamp for deduplicating pr_poll_error toast notifications.
 * Only show toast if more than 30 seconds since the last one.
 */
let lastPollErrorToastMs = 0;

/** Minimum interval between pr_poll_error toasts (30 seconds). */
const POLL_ERROR_TOAST_INTERVAL_MS = 30_000;

/**
 * Derive WebSocket URL from window.location.
 * Converts HTTP protocol to WS, HTTPS to WSS. Uses current host with /ws/events path.
 * Falls back to localhost:8420 in SSR/test environments where window is undefined.
 *
 * @returns WebSocket URL (ws://host/ws/events or wss://host/ws/events)
 */
function deriveWebSocketUrl(): string {
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
const MAX_RECONNECT_DELAY = 30000;

/**
 * Initial delay for the first reconnection attempt in milliseconds (1 second).
 */
const INITIAL_RECONNECT_DELAY = 1000;

/**
 * Handle incoming brainstorm streaming events.
 * Routes events to the brainstormStore based on event_type.
 *
 * @param msg - The brainstorm message from the WebSocket
 */
export function handleBrainstormMessage(msg: BrainstormStreamEvent): void {
  const state = useBrainstormStore.getState();

  if (msg.session_id !== state.activeSessionId) return;

  switch (msg.event_type) {
    case 'text':
      if (msg.message_id) {
        const text = validateText(msg.data.text);
        state.updateMessage(msg.message_id, (m) => ({
          ...m,
          content: m.content + (text ?? ''),
        }));
      }
      break;

    case 'reasoning':
      if (msg.message_id) {
        const text = validateText(msg.data.text);
        state.updateMessage(msg.message_id, (m) => ({
          ...m,
          reasoning: (m.reasoning ?? '') + (text ?? ''),
        }));
      }
      break;

    case 'message_complete': {
      const error = validateText(msg.data.error);
      const usage = validateMessageUsage(msg.data.usage);
      const sessionUsage = validateSessionUsageSummary(msg.data.session_usage);
      if (msg.message_id) {
        state.updateMessage(msg.message_id, (m) => ({
          ...m,
          status: error ? 'error' : undefined,
          errorMessage: error || undefined,
          usage,
          // Mark all running tool calls as completed since the SDK doesn't
          // stream explicit tool results - it handles execution internally
          toolCalls: m.toolCalls?.map((tc) =>
            tc.state === 'input-available'
              ? { ...tc, state: 'output-available' as const }
              : tc
          ),
        }));
      }
      if (sessionUsage) {
        state.setSessionUsage(sessionUsage);
      }
      state.setStreaming(false, null);
      break;
    }

    case 'artifact_created': {
      const artifact = validateBrainstormArtifact(msg.data);
      if (artifact) {
        state.addArtifact(artifact);
        state.updateSession(msg.session_id, { status: 'ready_for_handoff' });
      }
      break;
    }

    case 'tool_call': {
      if (msg.message_id) {
        const toolCallData = validateToolCall(msg.data);
        if (toolCallData) {
          const toolCall: ToolCall = {
            ...toolCallData,
            state: 'input-available',
          };
          state.updateMessage(msg.message_id, (m) => ({
            ...m,
            toolCalls: [...(m.toolCalls ?? []), toolCall],
          }));
        }
      }
      break;
    }

    case 'tool_result': {
      if (msg.message_id) {
        const toolCallId = validateText(msg.data.tool_call_id);
        const output = msg.data.output;
        const errorText = validateText(msg.data.error);
        // validateText returns undefined on validation failure, so check for defined
        if (toolCallId !== undefined) {
          state.updateMessage(msg.message_id, (m) => ({
            ...m,
            toolCalls: m.toolCalls?.map((tc) =>
              tc.tool_call_id === toolCallId
                ? {
                    ...tc,
                    output,
                    errorText: errorText || undefined,
                    state: errorText ? 'output-error' : 'output-available',
                  }
                : tc
            ),
          }));
        } else {
          logger.warn('tool_result dropped: tool_call_id validation failed', { data: msg.data });
        }
      }
      break;
    }

    case 'ask_user': {
      if (msg.message_id) {
        const result = askUserQuestionsSchema.safeParse(msg.data.questions);
        const questions = result.success ? result.data : undefined;
        const text = validateText(msg.data.text);
        if (!result.success && msg.data.questions !== undefined) {
          logger.error('AskUserQuestions validation failed', result.error, { data: msg.data.questions });
          Toast.error('Invalid question format received from server');
          break;
        }
        state.updateMessage(msg.message_id, (m) => ({
          ...m,
          content: m.content + (text ?? ''),
          ...(questions ? { askUserQuestions: { questions } } : {}),
        }));
      }
      break;
    }

    // session_created, session_completed can be handled later as needed
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

      if (lastSequence !== undefined && event.sequence !== lastSequence + 1) {
        logger.warn('Sequence gap detected', {
          workflow_id: workflowId,
          expected: lastSequence + 1,
          received: event.sequence,
        });
      }

      lastSequenceRef.current.set(workflowId, event.sequence);

      addEvent(event);

      if (event.event_type === 'pr_poll_error') {
        const now = Date.now();
        if (now - lastPollErrorToastMs > POLL_ERROR_TOAST_INTERVAL_MS) {
          lastPollErrorToastMs = now;
          Toast.error(event.message || 'PR polling error');
        }
      }

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
    if (reconnectTimeoutRef.current !== null) {
      clearTimeout(reconnectTimeoutRef.current);
    }

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
    let url = WS_BASE_URL;
    const currentLastEventId = useWorkflowStore.getState().lastEventId;
    if (currentLastEventId) {
      url += `?since=${encodeURIComponent(currentLastEventId)}`;
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      logger.info('WebSocket connected');
      setConnected(true);
      reconnectAttemptRef.current = 0;

      ws.send(JSON.stringify({ type: 'subscribe_all' }));
    };

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
            logger.info('Backfill complete', { count: message.count });
            break;

          case 'backfill_expired':
            logger.warn('Backfill expired', { message: message.message });
            setLastEventId(null);
            break;

          case 'brainstorm':
            handleBrainstormMessage(message);
            break;

          default:
            logger.warn('Unknown WebSocket message type', { message });
        }
      } catch (error) {
        logger.error('Error parsing WebSocket message', error);
      }
    };

    ws.onclose = (event) => {
      logger.info('WebSocket disconnected', { code: event.code, reason: event.reason });
      setConnected(false);
      wsRef.current = null;

      useBrainstormStore.getState().handleWebSocketDisconnect();

      // Reconnect unless it was a normal closure
      if (event.code !== 1000) {
        scheduleReconnect();
      }
    };

    ws.onerror = (error) => {
      logger.error('WebSocket error', error);
      setConnected(false, 'WebSocket error');
    };
  }, [handleEvent, scheduleReconnect, setConnected, setLastEventId]);

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

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
      }

      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { reconnect };
}
