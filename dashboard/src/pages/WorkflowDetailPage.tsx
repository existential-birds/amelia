/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Workflow detail page with full status display.
 */
import { useLoaderData } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { ActivityLog } from '@/components/ActivityLog';
import { ApprovalControls } from '@/components/ApprovalControls';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import { AgentProgressBar, type AgentStage } from '@/components/AgentProgressBar';
import { buildPipeline } from '@/utils/pipeline';
import { useElapsedTime, useAutoRevalidation } from '@/hooks';
import { workflowDetailLoader } from '@/loaders';
import { ScrollArea } from '@/components/ui/scroll-area';

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
 *
 * @returns The workflow detail page UI
 */
export default function WorkflowDetailPage() {
  const { workflow } = useLoaderData<typeof workflowDetailLoader>();
  const elapsedTime = useElapsedTime(workflow);

  // Auto-revalidate when this workflow's status changes (approval events, completion, etc.)
  useAutoRevalidation(workflow?.id);

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

  // Show approval controls when blocked (awaiting human approval)
  const needsApproval = workflow.status === 'blocked';
  const goalSummary = workflow.goal || 'Awaiting plan generation';

  // Build pipeline for visualization
  const pipeline = buildPipeline(workflow);

  // Determine agent progress
  const currentStage = workflow.current_stage as AgentStage | null;
  const completedStages = getCompletedStages(workflow.current_stage);

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
              planSummary={goalSummary}
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
        {/* Left column: Pipeline Canvas */}
        <div className="flex flex-col gap-4 overflow-y-auto">
          {/* Goal display */}
          {workflow.goal && (
            <div className="p-4 border border-border rounded-lg bg-card/50">
              <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-2">
                GOAL
              </h3>
              <p className="text-sm text-foreground">{workflow.goal}</p>
            </div>
          )}

          {/* Workflow Canvas (pipeline visualization) */}
          <div className="p-4 border border-border rounded-lg bg-card/50">
            <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-3">
              PIPELINE
            </h3>
            <WorkflowCanvas pipeline={pipeline || undefined} />
          </div>
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
    </div>
  );
}
