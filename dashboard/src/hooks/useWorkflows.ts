/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { useLoaderData, useRevalidator } from 'react-router-dom';
import { useWorkflowStore } from '../store/workflowStore';
import { useEffect, useRef } from 'react';
import type { WorkflowsLoaderData } from '../types/api';

/**
 * Hook that combines route loader data with real-time WebSocket updates.
 *
 * Provides a unified interface for accessing workflow data with automatic revalidation:
 * - Initial data comes from React Router's route loader (server-side)
 * - Real-time updates come from WebSocket events stored in Zustand
 * - Automatically revalidates loader data when status-changing events occur
 * - Tracks connection status and revalidation state
 *
 * Status-changing events that trigger revalidation:
 * - workflow_started
 * - workflow_completed
 * - workflow_failed
 *
 * @returns An object containing workflow data, connection status, and revalidation controls.
 * @returns workflows - Array of workflow objects from the route loader.
 * @returns isConnected - Boolean indicating WebSocket connection status.
 * @returns isRevalidating - Boolean indicating if loader data is currently being revalidated.
 * @returns revalidate - Function to manually trigger loader revalidation.
 *
 * @example
 * ```tsx
 * function WorkflowList() {
 *   const { workflows, isConnected, isRevalidating, revalidate } = useWorkflows();
 *
 *   return (
 *     <div>
 *       <div>Status: {isConnected ? 'Connected' : 'Disconnected'}</div>
 *       {isRevalidating && <div>Refreshing...</div>}
 *       <button onClick={revalidate}>Refresh</button>
 *       {workflows.map(workflow => (
 *         <div key={workflow.id}>{workflow.name}</div>
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useWorkflows() {
  const { workflows } = useLoaderData() as WorkflowsLoaderData;
  const { eventsByWorkflow, isConnected } = useWorkflowStore();
  const revalidator = useRevalidator();
  const lastProcessedTimestampRef = useRef<number>(0);

  // Revalidate when we receive status-changing events
  useEffect(() => {
    const statusEvents = [
      'workflow_completed',
      'workflow_failed',
      'workflow_started',
      'approval_required',
      'approval_granted',
      'approval_rejected',
    ];
    const recentEvents = Object.values(eventsByWorkflow).flat();

    // Find the latest status-changing event within the 5-second window
    const latestStatusEvent = recentEvents
      .filter((e) => statusEvents.includes(e.event_type))
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
  }, [eventsByWorkflow, revalidator]);

  return {
    workflows,
    isConnected,
    isRevalidating: revalidator.state === 'loading',
    revalidate: () => revalidator.revalidate(),
  };
}
