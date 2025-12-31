import { useState, useEffect } from 'react';
import { formatElapsedTime } from '@/utils/workflow';
import type { WorkflowDetail } from '@/types';

/**
 * Custom hook that returns the formatted elapsed time for a workflow.
 *
 * For workflows with status 'in_progress', the elapsed time is updated
 * every 60 seconds to show live progress. For other statuses (completed,
 * blocked, failed, etc.), the elapsed time is computed once.
 *
 * @param workflow - The workflow detail to compute elapsed time for, or null
 * @returns Formatted elapsed time string (e.g., "2h 34m") or "--:--" if no workflow
 *
 * @example
 * ```tsx
 * function WorkflowTimer({ workflow }: { workflow: WorkflowDetail | null }) {
 *   const elapsed = useElapsedTime(workflow);
 *   return <div>Elapsed: {elapsed}</div>;
 * }
 * ```
 */
export function useElapsedTime(workflow: WorkflowDetail | null): string {
  const [elapsed, setElapsed] = useState(() => formatElapsedTime(workflow));

  useEffect(() => {
    // Re-compute immediately when workflow changes
    setElapsed(formatElapsedTime(workflow));

    // Only set up interval for in_progress workflows
    if (!workflow || workflow.status !== 'in_progress') return;

    const interval = setInterval(() => {
      setElapsed(formatElapsedTime(workflow));
    }, 60_000); // Update every 60 seconds

    return () => clearInterval(interval);
  }, [workflow]);

  return elapsed;
}
