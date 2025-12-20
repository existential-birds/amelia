/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Workflow detail page with full status display.
 */
import { useState, useCallback } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { WorkflowProgress } from '@/components/WorkflowProgress';
import { ActivityLog } from '@/components/ActivityLog';
import { ApprovalControls } from '@/components/ApprovalControls';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import { AgentProgressBar, type AgentStage } from '@/components/AgentProgressBar';
import { BatchStepCanvas } from '@/components/BatchStepCanvas';
import { BlockerResolutionDialog } from '@/components/BlockerResolutionDialog';
import { CancelStepDialog } from '@/components/CancelStepDialog';
import { buildPipeline } from '@/utils/pipeline';
import { useElapsedTime, useAutoRevalidation } from '@/hooks';
import { workflowDetailLoader } from '@/loaders';
import { ScrollArea } from '@/components/ui/scroll-area';
import { api } from '@/api/client';
import type { ExecutionPlan, BatchResult, BatchApproval, BlockerReport } from '@/types';

/**
 * Determines completed stages based on current stage.
 * Stages progress: pm -> architect -> developer -> reviewer
 */
function getCompletedStages(currentStage: string | null): AgentStage[] {
  const stageOrder: AgentStage[] = ['pm', 'architect', 'developer', 'reviewer'];
  if (!currentStage) return [];
  const currentIndex = stageOrder.indexOf(currentStage as AgentStage);
  if (currentIndex === -1) return [];
  return stageOrder.slice(0, currentIndex);
}

/**
 * Displays comprehensive workflow details with progress, pipeline, and activity.
 *
 * Shows header with status, progress bar, visual pipeline canvas,
 * approval controls (when blocked), and real-time activity log.
 * Converts plan tasks to pipeline nodes for visualization.
 * Supports batch execution visualization with BatchStepCanvas.
 *
 * @returns The workflow detail page UI
 */
export default function WorkflowDetailPage() {
  const { workflow } = useLoaderData<typeof workflowDetailLoader>();
  const elapsedTime = useElapsedTime(workflow);
  const revalidator = useRevalidator();

  // Dialog states
  const [blockerDialogOpen, setBlockerDialogOpen] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [cancelStepId, setCancelStepId] = useState<string | null>(null);
  const [cancelStepDescription, setCancelStepDescription] = useState('');
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [blockerError, setBlockerError] = useState<string | null>(null);

  // Auto-revalidate when this workflow's status changes (approval events, completion, etc.)
  useAutoRevalidation(workflow?.id);

  // Handle step cancellation
  const handleCancelStep = useCallback((stepId: string) => {
    // Find step description from execution plan
    const step = workflow?.execution_plan?.batches
      .flatMap(b => b.steps)
      .find(s => s.id === stepId);
    setCancelStepId(stepId);
    setCancelStepDescription(step?.description || stepId);
    setCancelDialogOpen(true);
  }, [workflow?.execution_plan]);

  const confirmCancelStep = useCallback(async () => {
    if (!workflow || !cancelStepId) return;
    setCancelError(null);
    try {
      await api.cancelStep(workflow.id, cancelStepId);
      revalidator.revalidate();
      setCancelDialogOpen(false);
      setCancelStepId(null);
    } catch (error) {
      setCancelError(error instanceof Error ? error.message : 'Failed to cancel step');
    }
  }, [workflow, cancelStepId, revalidator]);

  // Handle blocker resolution
  const handleRetry = useCallback(async () => {
    if (!workflow) return;
    setBlockerError(null);
    try {
      await api.resolveBlocker(workflow.id, 'retry');
      setBlockerDialogOpen(false);
      revalidator.revalidate();
    } catch (error) {
      setBlockerError(error instanceof Error ? error.message : 'Failed to retry');
    }
  }, [workflow, revalidator]);

  const handleSkip = useCallback(async () => {
    if (!workflow) return;
    setBlockerError(null);
    try {
      await api.resolveBlocker(workflow.id, 'skip');
      setBlockerDialogOpen(false);
      revalidator.revalidate();
    } catch (error) {
      setBlockerError(error instanceof Error ? error.message : 'Failed to skip');
    }
  }, [workflow, revalidator]);

  const handleFixInstruction = useCallback(async (instruction: string) => {
    if (!workflow) return;
    setBlockerError(null);
    try {
      await api.resolveBlocker(workflow.id, 'fix', instruction);
      setBlockerDialogOpen(false);
      revalidator.revalidate();
    } catch (error) {
      setBlockerError(error instanceof Error ? error.message : 'Failed to apply fix');
    }
  }, [workflow, revalidator]);

  const handleAbort = useCallback(async (revert: boolean) => {
    if (!workflow) return;
    setBlockerError(null);
    try {
      await api.resolveBlocker(workflow.id, revert ? 'abort_revert' : 'abort');
      setBlockerDialogOpen(false);
      revalidator.revalidate();
    } catch (error) {
      setBlockerError(error instanceof Error ? error.message : 'Failed to abort');
    }
  }, [workflow, revalidator]);

  if (!workflow) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
        <div className="text-destructive font-semibold">
          Workflow not found
        </div>
        <p className="text-muted-foreground">
          The requested workflow could not be loaded.
        </p>
      </div>
    );
  }

  // Calculate task counts from execution_plan batches
  const totalTasks = workflow.execution_plan?.batches.reduce(
    (sum, batch) => sum + batch.steps.length, 0
  ) || 0;
  const completedBatches = workflow.current_batch_index;
  const completedTasks = workflow.execution_plan?.batches
    .slice(0, completedBatches)
    .reduce((sum, batch) => sum + batch.steps.length, 0) || 0;

  const needsApproval = workflow.status === 'blocked';
  const planSummary = workflow.execution_plan
    ? `Plan with ${totalTasks} steps in ${workflow.execution_plan.batches.length} batches`
    : 'No plan generated';

  // Build pipeline for visualization
  const pipeline = buildPipeline(workflow);

  // Batch execution data
  const executionPlan = workflow.execution_plan as ExecutionPlan | null;
  const batchResults = workflow.batch_results as BatchResult[];
  const batchApprovals = workflow.batch_approvals as BatchApproval[];
  const currentBlocker = workflow.current_blocker as BlockerReport | null;
  const hasBatchExecution = executionPlan !== null;

  // Determine agent progress
  const currentStage = workflow.current_stage as AgentStage | null;
  const completedStages = getCompletedStages(workflow.current_stage);

  // Show blocker dialog when user clicks the blocker indicator
  const shouldShowBlockerDialog = currentBlocker !== null && blockerDialogOpen;

  return (
    <div className="flex flex-col h-full w-full">
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>WORKFLOW</PageHeader.Label>
          <div className="flex items-center gap-3">
            <PageHeader.Title>{workflow.issue_id}</PageHeader.Title>
            <PageHeader.Subtitle>{workflow.worktree_name}</PageHeader.Subtitle>
          </div>
        </PageHeader.Left>

        <PageHeader.Center>
          <PageHeader.Label>ELAPSED</PageHeader.Label>
          <PageHeader.Value glow>{elapsedTime}</PageHeader.Value>
        </PageHeader.Center>

        <PageHeader.Right>
          {needsApproval && (
            <ApprovalControls
              workflowId={workflow.id}
              planSummary={planSummary}
              status="pending"
            />
          )}
          <StatusBadge status={workflow.status} />
        </PageHeader.Right>
      </PageHeader>

      {/* Agent Progress Bar - shows workflow stage progress */}
      {workflow.status === 'in_progress' && currentStage && (
        <div className="px-6 py-3 border-b border-border bg-muted/10">
          <AgentProgressBar
            currentStage={currentStage}
            completedStages={completedStages}
          />
        </div>
      )}

      <div className="flex-1 overflow-hidden grid grid-cols-2 gap-4 p-6">
        {/* Left column: Progress, Canvas */}
        <div className="flex flex-col gap-4 overflow-y-auto">
          {/* Progress */}
          {workflow.status === 'in_progress' && (
            <div className="p-4 border border-border rounded-lg bg-card/50">
              <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-3">
                PROGRESS
              </h3>
              <WorkflowProgress completed={completedTasks} total={totalTasks} />
            </div>
          )}

          {/* Batch Execution Canvas (when execution plan is available) */}
          {hasBatchExecution ? (
            <div className="border border-border rounded-lg bg-card/50 overflow-hidden">
              <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground p-4 border-b border-border bg-muted/20">
                BATCH EXECUTION
              </h3>
              <BatchStepCanvas
                executionPlan={executionPlan}
                batchResults={batchResults}
                currentBatchIndex={workflow.current_batch_index}
                batchApprovals={batchApprovals}
                onCancelStep={handleCancelStep}
              />
            </div>
          ) : (
            /* Workflow Canvas (legacy pipeline visualization) */
            <div className="p-4 border border-border rounded-lg bg-card/50">
              <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-3">
                PIPELINE
              </h3>
              <WorkflowCanvas pipeline={pipeline || undefined} />
            </div>
          )}

          {/* Blocker indicator - opens dialog on click */}
          {currentBlocker && (
            <button
              type="button"
              onClick={() => setBlockerDialogOpen(true)}
              className="p-4 border border-destructive/50 rounded-lg bg-destructive/10 text-left hover:bg-destructive/20 transition-colors"
            >
              <h3 className="font-heading text-xs font-semibold tracking-widest text-destructive mb-2">
                EXECUTION BLOCKED
              </h3>
              <p className="text-sm text-destructive/90">
                Step {currentBlocker.step_id} encountered a {currentBlocker.blocker_type} error.
                Click to resolve.
              </p>
            </button>
          )}
        </div>

        {/* Right column: Activity Log */}
        <div className="border border-border rounded-lg bg-card/50 overflow-hidden flex flex-col">
          <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground p-4 border-b border-border bg-muted/20">
            ACTIVITY LOG
          </h3>
          <ScrollArea className="flex-1">
            <div className="p-4">
              <ActivityLog
                workflowId={workflow.id}
                initialEvents={workflow.recent_events}
              />
            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Blocker Resolution Dialog */}
      {currentBlocker && (
        <BlockerResolutionDialog
          blocker={currentBlocker}
          isOpen={shouldShowBlockerDialog}
          onClose={() => {
            setBlockerDialogOpen(false);
            setBlockerError(null);
          }}
          onRetry={handleRetry}
          onSkip={handleSkip}
          onFixInstruction={handleFixInstruction}
          onAbort={handleAbort}
          error={blockerError}
        />
      )}

      {/* Cancel Step Dialog */}
      <CancelStepDialog
        stepDescription={cancelStepDescription}
        isOpen={cancelDialogOpen}
        onConfirm={confirmCancelStep}
        onCancel={() => {
          setCancelDialogOpen(false);
          setCancelError(null);
        }}
        error={cancelError}
      />
    </div>
  );
}
