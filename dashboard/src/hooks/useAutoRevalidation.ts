/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { useEffect, useRef } from 'react';
import { useRevalidator } from 'react-router-dom';
import { useWorkflowStore } from '../store/workflowStore';

/**
 * Event types that indicate a workflow status change requiring UI refresh.
 */
const STATUS_EVENTS = [
  'workflow_completed',
  'workflow_failed',
  'workflow_started',
  'approval_required',
  'approval_granted',
  'approval_rejected',
] as const;

/**
 * Hook that automatically revalidates React Router loader data when
 * status-changing workflow events are received via WebSocket.
 *
 * Watches the Zustand store for events and triggers revalidation when:
 * - workflow_started, workflow_completed, workflow_failed
 * - approval_required, approval_granted, approval_rejected
 *
 * Only processes events from the last 5 seconds to avoid revalidating
 * on old events during initial page load.
 *
 * @param workflowId - Optional workflow ID to filter events. If provided,
 *   only events for that specific workflow trigger revalidation.
 *   If omitted, events from any workflow trigger revalidation.
 *
 * @example
 * ```tsx
 * // In a workflow list page - revalidate on any workflow change
 * function WorkflowsPage() {
 *   useAutoRevalidation();
 *   const { workflows } = useLoaderData();
 *   // ...
 * }
 *
 * // In a workflow detail page - revalidate only for this workflow
 * function WorkflowDetailPage() {
 *   const { workflow } = useLoaderData();
 *   useAutoRevalidation(workflow.id);
 *   // ...
 * }
 * ```
 */
export function useAutoRevalidation(workflowId?: string) {
  const { eventsByWorkflow } = useWorkflowStore();
  const revalidator = useRevalidator();
  const lastProcessedTimestampRef = useRef<number>(0);

  useEffect(() => {
    // Get events for specific workflow or all workflows
    const events = workflowId
      ? eventsByWorkflow[workflowId] ?? []
      : Object.values(eventsByWorkflow).flat();

    // Find the latest status-changing event within the 5-second window
    const latestStatusEvent = events
      .filter((e) => STATUS_EVENTS.includes(e.event_type as (typeof STATUS_EVENTS)[number]))
      .map((e) => new Date(e.timestamp).getTime())
      .filter((timestamp) => Date.now() - timestamp < 5000)
      .sort((a, b) => b - a)[0];

    // Only revalidate if we have a new event we haven't processed yet
    if (
      latestStatusEvent &&
      latestStatusEvent > lastProcessedTimestampRef.current &&
      revalidator.state === 'idle'
    ) {
      lastProcessedTimestampRef.current = latestStatusEvent;
      revalidator.revalidate();
    }
  }, [eventsByWorkflow, revalidator, workflowId]);
}
