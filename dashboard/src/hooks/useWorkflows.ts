import { useLoaderData, useRevalidator } from 'react-router-dom';
import { useWorkflowStore } from '../store/workflowStore';
import { useEffect } from 'react';
import type { WorkflowsLoaderData } from '../types/api';

/**
 * Hook that combines loader data with real-time updates.
 *
 * Data Flow:
 * - Initial data comes from route loader (via useLoaderData)
 * - Real-time updates come from WebSocket via Zustand store
 * - Revalidation is triggered for status-changing events
 */
export function useWorkflows() {
  const { workflows } = useLoaderData() as WorkflowsLoaderData;
  const { eventsByWorkflow, isConnected } = useWorkflowStore();
  const revalidator = useRevalidator();

  // Revalidate when we receive status-changing events
  useEffect(() => {
    const statusEvents = ['workflow_completed', 'workflow_failed', 'workflow_started'];
    const recentEvents = Object.values(eventsByWorkflow).flat();
    const hasStatusChange = recentEvents.some(
      (e) =>
        statusEvents.includes(e.event_type) &&
        Date.now() - new Date(e.timestamp).getTime() < 5000 // Within last 5 seconds
    );

    if (hasStatusChange && revalidator.state === 'idle') {
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
