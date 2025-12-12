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
import { WorkflowProgress } from '@/components/WorkflowProgress';
import { ActivityLog } from '@/components/ActivityLog';
import { ApprovalControls } from '@/components/ApprovalControls';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import { buildPipeline } from '@/utils/pipeline';
import { useElapsedTime } from '@/hooks';
import { workflowDetailLoader } from '@/loaders';
import { ScrollArea } from '@/components/ui/scroll-area';

/**
 * Displays comprehensive workflow details with progress, pipeline, and activity.
 *
 * Shows header with status, progress bar, visual pipeline canvas,
 * approval controls (when blocked), and real-time activity log.
 * Converts plan tasks to pipeline nodes for visualization.
 *
 * @returns The workflow detail page UI
 */
export default function WorkflowDetailPage() {
  const { workflow } = useLoaderData<typeof workflowDetailLoader>();
  const elapsedTime = useElapsedTime(workflow);

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

  const completedTasks = workflow.plan?.tasks.filter(t => t.status === 'completed').length || 0;
  const totalTasks = workflow.plan?.tasks.length || 0;

  const needsApproval = workflow.status === 'blocked';
  const planSummary = workflow.plan
    ? `Plan with ${workflow.plan.tasks.length} tasks`
    : 'No plan generated';

  // Build pipeline for visualization
  const pipeline = buildPipeline(workflow);

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

          {/* Workflow Canvas (visual pipeline) */}
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
