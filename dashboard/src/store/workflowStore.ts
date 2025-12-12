/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

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
 * Zustand store state for real-time WebSocket events and connection state.
 *
 * Note: Workflow data and UI state (including selection) come from React Router loaders and URL params.
 * This store only manages:
 * - Real-time events from WebSocket
 * - Connection state
 * - Pending actions for optimistic UI
 */
interface WorkflowState {
  /**
   * Real-time events from WebSocket, grouped by workflow ID.
   * Each workflow maintains a separate array of events, automatically
   * trimmed to MAX_EVENTS_PER_WORKFLOW entries.
   */
  eventsByWorkflow: Record<string, WorkflowEvent[]>;

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
   * Automatically trims the event list if it exceeds MAX_EVENTS_PER_WORKFLOW,
   * keeping only the most recent events. Updates lastEventId.
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
 * Zustand store hook for managing workflow real-time events and connection state.
 *
 * This store handles:
 * - Real-time WebSocket events (grouped by workflow, auto-trimmed)
 * - WebSocket connection status and errors
 * - Pending action tracking for optimistic UI updates
 *
 * State is persisted to sessionStorage, but only lastEventId is saved.
 * Real-time events are ephemeral and not persisted.
 *
 * @example
 * ```typescript
 * const { addEvent, isConnected } = useWorkflowStore();
 *
 * // Add a real-time event
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
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: [],

      addEvent: (event) =>
        set((state) => {
          const existing = state.eventsByWorkflow[event.workflow_id] ?? [];
          const updated = [...existing, event];

          // Trim oldest events if exceeding limit (keep most recent)
          const trimmed =
            updated.length > MAX_EVENTS_PER_WORKFLOW
              ? updated.slice(-MAX_EVENTS_PER_WORKFLOW)
              : updated;

          return {
            eventsByWorkflow: {
              ...state.eventsByWorkflow,
              [event.workflow_id]: trimmed,
            },
            lastEventId: event.id,
          };
        }),

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
