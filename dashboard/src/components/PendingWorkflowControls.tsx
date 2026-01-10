/**
 * @fileoverview Controls for pending (queued) workflows.
 *
 * Displays Start/Cancel buttons and queue status for workflows
 * that are waiting to be executed.
 */
import { useState, useCallback } from 'react';
import { useRevalidator } from 'react-router-dom';
import { Play, X, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader } from '@/components/ai-elements/loader';
import { success, error as toastError } from '@/components/Toast';
import { formatRelativeTime } from '@/utils/workflow';
import { api } from '@/api/client';
import { cn } from '@/lib/utils';

/**
 * Props for the PendingWorkflowControls component.
 * @property workflowId - Unique identifier for the pending workflow
 * @property createdAt - Optional ISO timestamp when the workflow was queued
 * @property hasPlan - Whether the workflow has a plan ready
 * @property className - Optional additional CSS classes
 */
interface PendingWorkflowControlsProps {
  workflowId: string;
  createdAt?: string | null;
  hasPlan?: boolean;
  className?: string;
}

/**
 * Displays start/cancel controls for pending workflows.
 *
 * Shows:
 * - "Queued X ago" timestamp
 * - Plan status indicator (Plan ready / No plan)
 * - Start button to begin workflow execution
 * - Cancel button to remove the workflow from queue
 *
 * @param props - Component props
 * @returns The pending workflow controls UI
 *
 * @example
 * ```tsx
 * <PendingWorkflowControls
 *   workflowId="wf-123"
 *   createdAt="2025-01-01T10:00:00Z"
 *   hasPlan={true}
 * />
 * ```
 */
export function PendingWorkflowControls({
  workflowId,
  createdAt,
  hasPlan = false,
  className,
}: PendingWorkflowControlsProps) {
  const revalidator = useRevalidator();
  const [isStarting, setIsStarting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const isPending = isStarting || isCancelling;

  const handleStart = useCallback(async () => {
    setIsStarting(true);
    try {
      await api.startWorkflow(workflowId);
      success('Workflow started');
      revalidator.revalidate();
    } catch (err) {
      toastError('Failed to start workflow');
      console.error('Failed to start workflow:', err);
    } finally {
      setIsStarting(false);
    }
  }, [workflowId, revalidator]);

  const handleCancel = useCallback(async () => {
    setIsCancelling(true);
    try {
      await api.cancelWorkflow(workflowId);
      success('Workflow cancelled');
      revalidator.revalidate();
    } catch (err) {
      toastError('Failed to cancel workflow');
      console.error('Failed to cancel workflow:', err);
    } finally {
      setIsCancelling(false);
    }
  }, [workflowId, revalidator]);

  return (
    <div
      data-slot="pending-workflow-controls"
      className={cn(
        'p-4 border border-border rounded-lg bg-card flex flex-col gap-3',
        className
      )}
    >
      <h4 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground">
        QUEUED WORKFLOW
      </h4>

      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          queued{createdAt ? ` ${formatRelativeTime(createdAt)}` : ''}
        </span>
        {hasPlan ? (
          <Badge variant="outline" className="gap-1">
            <FileText className="w-3 h-3" />
            Plan ready
          </Badge>
        ) : (
          <Badge variant="secondary" className="gap-1">
            No plan
          </Badge>
        )}
      </div>

      <p className="text-sm text-muted-foreground">
        This workflow is queued and waiting to be started.
      </p>

      <div className="flex gap-3">
        <Button
          type="button"
          onClick={handleStart}
          disabled={isPending}
          className="bg-status-completed hover:bg-status-completed/90 focus-visible:ring-status-completed/50"
        >
          {isStarting ? (
            <Loader className="w-4 h-4 mr-2" />
          ) : (
            <Play className="w-4 h-4 mr-2" />
          )}
          Start
        </Button>

        <Button
          type="button"
          variant="outline"
          onClick={handleCancel}
          disabled={isPending}
          className="border-destructive text-destructive hover:bg-destructive hover:text-foreground focus-visible:ring-destructive/50"
        >
          {isCancelling ? (
            <Loader className="w-4 h-4 mr-2" />
          ) : (
            <X className="w-4 h-4 mr-2" />
          )}
          Cancel
        </Button>
      </div>
    </div>
  );
}
