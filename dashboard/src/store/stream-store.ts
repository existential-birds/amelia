/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { create } from 'zustand';
import type { StreamEvent } from '../types';

/**
 * Maximum number of stream events to retain in the store.
 *
 * Stream events are high-frequency (thinking tokens, tool calls, etc.)
 * and can quickly accumulate. This buffer limit prevents excessive memory usage
 * by keeping only the most recent events. Older events are automatically trimmed.
 */
const MAX_STREAM_EVENTS = 1000;

/**
 * Zustand store state for Claude streaming events.
 *
 * This store manages real-time stream events from Claude LLM execution,
 * including thinking tokens, tool calls, and agent outputs. Events are
 * buffered with automatic trimming to prevent memory issues.
 *
 * @property events - Array of stream events in chronological order
 * @property liveMode - Whether live streaming mode is enabled
 * @property maxEvents - Maximum number of events to retain in buffer
 * @property addEvent - Adds a new stream event to the store
 * @property setLiveMode - Toggles live streaming mode
 * @property clearEvents - Clears all events from the store
 */
interface StreamState {
  /**
   * Array of stream events in chronological order.
   * Automatically trimmed to maxEvents entries (oldest events are dropped).
   */
  events: StreamEvent[];

  /**
   * Whether live streaming mode is enabled.
   * When true, the UI should auto-scroll and display events in real-time.
   */
  liveMode: boolean;

  /**
   * Maximum number of events to retain in the buffer.
   * When exceeded, oldest events are automatically trimmed.
   */
  maxEvents: number;

  /**
   * Adds a new stream event to the store.
   *
   * Events are appended to the end of the array. If the array exceeds
   * maxEvents, the oldest events are automatically trimmed to maintain
   * the buffer size limit.
   *
   * @param event - The stream event to add.
   */
  addEvent: (event: StreamEvent) => void;

  /**
   * Toggles live streaming mode.
   *
   * When enabled, the UI should auto-scroll to show the latest events
   * and provide real-time feedback during agent execution.
   *
   * @param enabled - Whether to enable or disable live mode.
   */
  setLiveMode: (enabled: boolean) => void;

  /**
   * Clears all events from the store.
   *
   * Useful when switching between workflows or resetting the stream view.
   */
  clearEvents: () => void;
}

/**
 * Zustand store hook for managing Claude stream events.
 *
 * This store handles high-frequency stream events emitted during Claude LLM
 * execution, including thinking tokens, tool calls, tool results, and agent
 * outputs. Events are buffered with automatic trimming to prevent memory issues.
 *
 * Unlike WorkflowEvents (which track lifecycle and stage changes), StreamEvents
 * provide real-time insight into agent reasoning and tool usage.
 *
 * @example
 * ```typescript
 * const { addEvent, events, liveMode, setLiveMode } = useStreamStore();
 *
 * // Add a thinking event
 * addEvent({
 *   subtype: 'claude_thinking',
 *   content: 'I need to analyze the requirements...',
 *   timestamp: '2025-12-13T10:30:00Z',
 *   agent: 'architect',
 *   workflow_id: 'wf-123',
 *   tool_name: null,
 *   tool_input: null
 * });
 *
 * // Enable live mode for real-time display
 * setLiveMode(true);
 *
 * // Filter events by workflow
 * const workflowEvents = events.filter(e => e.workflow_id === 'wf-123');
 *
 * // Filter events by agent
 * const architectEvents = events.filter(e => e.agent === 'architect');
 * ```
 */
export const useStreamStore = create<StreamState>((set) => ({
  events: [],
  liveMode: false,
  maxEvents: MAX_STREAM_EVENTS,

  addEvent: (event) =>
    set((state) => {
      const updated = [...state.events, event];

      // Trim oldest events if exceeding limit (keep most recent)
      const trimmed =
        updated.length > state.maxEvents
          ? updated.slice(-state.maxEvents)
          : updated;

      return { events: trimmed };
    }),

  setLiveMode: (enabled) => set({ liveMode: enabled }),

  clearEvents: () => set({ events: [] }),
}));
