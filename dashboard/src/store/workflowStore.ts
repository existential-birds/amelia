import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { WorkflowEvent } from '../types';

/**
 * Maximum number of events to retain per workflow in the store.
 *
 * When this limit is exceeded, the oldest events are trimmed to maintain
 * performance and prevent excessive memory usage. The most recent events
 * are always kept.
 */
const MAX_EVENTS_PER_WORKFLOW = 500;

/**
 * Batch configuration for event processing.
 *
 * Events are batched to reduce React re-renders and GC pressure when
 * processing high-volume event streams from WebSocket.
 */
const BATCH_FLUSH_INTERVAL_MS = 100;
const BATCH_SIZE_LIMIT = 50;

/**
 * Pending events waiting to be flushed to state.
 * This is kept outside the store to avoid triggering re-renders
 * when events are added to the pending queue.
 */
let pendingEvents: WorkflowEvent[] = [];
let flushTimeoutId: ReturnType<typeof setTimeout> | null = null;

/**
 * Zustand store state for real-time WebSocket events and connection state.
 *
 * Note: Workflow data and UI state (including selection) come from React Router loaders and URL params.
 * This store only manages real-time events from WebSocket, connection state, and pending actions for optimistic UI.
 *
 * @property eventsByWorkflow - Real-time events grouped by workflow ID, auto-trimmed
 * @property eventIdsByWorkflow - Event ID sets per workflow for O(1) duplicate detection
 * @property lastEventId - Last received event ID for reconnection backfill
 * @property isConnected - Whether WebSocket connection is active
 * @property connectionError - Error message from last connection failure, or null
 * @property pendingActions - Action IDs currently being executed (in-flight requests)
 * @property addEvent - Adds a new event to the store for a workflow
 * @property setLastEventId - Updates the last seen event ID
 * @property setConnected - Updates WebSocket connection state
 * @property addPendingAction - Marks an action as pending (in-flight)
 * @property removePendingAction - Removes an action from pending list
 */
interface WorkflowState {
  /**
   * Real-time events from WebSocket, grouped by workflow ID.
   * Each workflow maintains a separate array of events, automatically
   * trimmed to MAX_EVENTS_PER_WORKFLOW entries.
   */
  eventsByWorkflow: Record<string, WorkflowEvent[]>;

  /**
   * Set of event IDs per workflow for O(1) duplicate detection.
   * Kept in sync with eventsByWorkflow - rebuilt when trimming occurs.
   */
  eventIdsByWorkflow: Record<string, Set<string>>;

  /**
   * ID of the last received event, used for reconnection backfill.
   * When reconnecting, this ID is sent to the server to retrieve
   * any missed events.
   */
  lastEventId: string | null;

  /**
   * Whether the WebSocket connection is currently active.
   */
  isConnected: boolean;

  /**
   * Error message from the last connection failure, or null if connected.
   */
  connectionError: string | null;

  /**
   * Action IDs currently being executed (in-flight requests).
   * Used for optimistic UI updates and loading states.
   */
  pendingActions: string[];

  /**
   * Adds a new event to the store for the specified workflow.
   *
   * Events are batched and flushed every BATCH_FLUSH_INTERVAL_MS (100ms)
   * or when BATCH_SIZE_LIMIT (50) events accumulate, whichever comes first.
   * This reduces React re-renders and GC pressure when processing
   * high-volume event streams.
   *
   * @param event - The workflow event to add.
   */
  addEvent: (event: WorkflowEvent) => void;

  /**
   * Updates the last seen event ID for reconnection tracking.
   *
   * @param id - The event ID, or null to clear.
   */
  setLastEventId: (id: string | null) => void;

  /**
   * Updates the WebSocket connection state.
   *
   * @param connected - Whether the connection is active.
   * @param error - Optional error message if connection failed.
   */
  setConnected: (connected: boolean, error?: string) => void;

  /**
   * Marks an action as pending (in-flight).
   *
   * Prevents duplicate entries - if the action ID already exists,
   * the state remains unchanged.
   *
   * @param actionId - The unique ID of the action being executed.
   */
  addPendingAction: (actionId: string) => void;

  /**
   * Removes an action from the pending list.
   *
   * Call this when an action completes (success or failure).
   *
   * @param actionId - The unique ID of the completed action.
   */
  removePendingAction: (actionId: string) => void;
}

/**
 * Apply a batch of events to the current state.
 *
 * This is the core logic extracted for batching. It processes multiple
 * events in a single pass, deduplicating by event ID and trimming
 * to MAX_EVENTS_PER_WORKFLOW if needed.
 *
 * @param state - Current store state
 * @param events - Array of events to apply
 * @returns Partial state update with new event data
 */
function applyEventBatch(
  state: WorkflowState,
  events: WorkflowEvent[]
): Partial<WorkflowState> {
  if (events.length === 0) return {};

  const newEventsByWorkflow = { ...state.eventsByWorkflow };
  const newEventIdsByWorkflow = { ...state.eventIdsByWorkflow };
  let lastEventId = state.lastEventId;

  for (const event of events) {
    const workflowId = event.workflow_id;
    const existingIds = newEventIdsByWorkflow[workflowId] ?? new Set<string>();

    // O(1) duplicate check - prevents duplicates from StrictMode
    // double-effect invocation, reconnection backfill, or server retries.
    if (existingIds.has(event.id)) {
      continue;
    }

    const existing = newEventsByWorkflow[workflowId] ?? [];
    const updated = [...existing, event];

    // Trim oldest events if exceeding limit (keep most recent)
    const needsTrim = updated.length > MAX_EVENTS_PER_WORKFLOW;
    const trimmed = needsTrim
      ? updated.slice(-MAX_EVENTS_PER_WORKFLOW)
      : updated;

    // Rebuild Set if trimmed (to remove old IDs), otherwise clone and add
    const newIds = needsTrim
      ? new Set(trimmed.map((e) => e.id))
      : new Set(existingIds).add(event.id);

    newEventsByWorkflow[workflowId] = trimmed;
    newEventIdsByWorkflow[workflowId] = newIds;
    lastEventId = event.id;
  }

  return {
    eventsByWorkflow: newEventsByWorkflow,
    eventIdsByWorkflow: newEventIdsByWorkflow,
    lastEventId,
  };
}

/**
 * Flush pending events to state.
 *
 * This is called either when the flush timer fires or when the
 * batch size limit is reached. It applies all pending events
 * in a single state update to minimize re-renders.
 */
function flushPendingEvents(): void {
  if (pendingEvents.length === 0) return;

  const eventsToFlush = pendingEvents;
  pendingEvents = [];

  if (flushTimeoutId !== null) {
    clearTimeout(flushTimeoutId);
    flushTimeoutId = null;
  }

  useWorkflowStore.setState((state) => applyEventBatch(state, eventsToFlush));
}

/**
 * Schedule a flush if not already scheduled.
 *
 * This ensures events are flushed within BATCH_FLUSH_INTERVAL_MS
 * even if the batch size limit is not reached.
 */
function scheduleFlush(): void {
  if (flushTimeoutId === null) {
    flushTimeoutId = setTimeout(flushPendingEvents, BATCH_FLUSH_INTERVAL_MS);
  }
}

/**
 * Reset batch state for test isolation.
 * Call this in test setup to ensure clean state between tests.
 * @internal Exported for testing only.
 */
export function resetBatchState(): void {
  pendingEvents = [];
  if (flushTimeoutId !== null) {
    clearTimeout(flushTimeoutId);
    flushTimeoutId = null;
  }
}

/**
 * Zustand store hook for managing workflow real-time events and connection state.
 *
 * This store handles:
 * - Real-time WebSocket events (grouped by workflow, auto-trimmed)
 * - WebSocket connection status and errors
 * - Pending action tracking for optimistic UI updates
 *
 * Events are batched and flushed every 100ms or when 50 events accumulate,
 * whichever comes first. This reduces React re-renders and GC pressure
 * when processing high-volume event streams.
 *
 * State is persisted to sessionStorage, but only lastEventId is saved.
 * Real-time events are ephemeral and not persisted.
 *
 * @returns The WorkflowState object containing events, connection status, and action methods.
 *
 * @example
 * ```typescript
 * const { addEvent, isConnected } = useWorkflowStore();
 *
 * // Add a real-time event (batched)
 * addEvent({
 *   id: 'evt-1',
 *   workflow_id: 'workflow-123',
 *   type: 'task.started',
 *   timestamp: '2025-12-06T10:00:00Z',
 *   data: { task_id: 'task-1' }
 * });
 *
 * // Check connection status
 * if (isConnected) {
 *   console.log('WebSocket connected');
 * }
 * ```
 */
export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set) => ({
      eventsByWorkflow: {},
      eventIdsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: [],

      addEvent: (event) => {
        pendingEvents.push(event);

        // Flush immediately if batch is full
        if (pendingEvents.length >= BATCH_SIZE_LIMIT) {
          flushPendingEvents();
        } else {
          scheduleFlush();
        }
      },

      setLastEventId: (id) => set({ lastEventId: id }),

      setConnected: (connected, error) =>
        set({
          isConnected: connected,
          connectionError: connected ? null : (error ?? null),
        }),

      addPendingAction: (actionId) =>
        set((state) => {
          // Don't add duplicates
          if (state.pendingActions.includes(actionId)) {
            return state;
          }
          return {
            pendingActions: [...state.pendingActions, actionId],
          };
        }),

      removePendingAction: (actionId) =>
        set((state) => ({
          pendingActions: state.pendingActions.filter((id) => id !== actionId),
        })),
    }),
    {
      name: 'amelia-workflow-state',
      storage: {
        getItem: (name) => {
          const value = sessionStorage.getItem(name);
          return value ? JSON.parse(value) : null;
        },
        setItem: (name, value) => {
          sessionStorage.setItem(name, JSON.stringify(value));
        },
        removeItem: (name) => {
          sessionStorage.removeItem(name);
        },
      },
      // Only persist lastEventId - events are ephemeral
      partialize: (state) => ({
        lastEventId: state.lastEventId,
      }) as unknown as WorkflowState,
    }
  )
);
