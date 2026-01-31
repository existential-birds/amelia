/**
 * @fileoverview Workflow detail page with full status display.
 */
import { useCallback, useMemo } from 'react';
import { useLoaderData } from 'react-router-dom';
import { RotateCcw } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { ActivityLog } from '@/components/ActivityLog';
import { ApprovalControls } from '@/components/ApprovalControls';
import { UsageCard } from '@/components/UsageCard';
import { Button } from '@/components/ui/button';
import { useElapsedTime, useAutoRevalidation } from '@/hooks';
import { useWorkflowActions } from '@/hooks/useWorkflowActions';
import { truncateWorkflowId } from '@/utils';
import { workflowDetailLoader } from '@/loaders';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useWorkflowStore } from '@/store/workflowStore';
import type { WorkflowEvent } from '@/types';

/**
 * Displays comprehensive workflow details with progress and activity.
 *
 * Shows header with status, progress bar, approval controls (when blocked),
 * usage stats, and real-time activity log.
 *
 * @returns The workflow detail page UI
 */
export default function WorkflowDetailPage() {
  const { workflow } = useLoaderData<typeof workflowDetailLoader>();
  const elapsedTime = useElapsedTime(workflow);

  // Use targeted selector to only subscribe to this workflow's events
  const workflowId = workflow?.id ?? '';
  // Selector returns undefined when no events exist - fallback applied inside useMemo
  const storeEvents = useWorkflowStore(
    useCallback((state) => state.eventsByWorkflow[workflowId], [workflowId])
  );

  // Auto-revalidate when this workflow's status changes (approval events, completion, etc.)
  useAutoRevalidation(workflow?.id);

  // Merge loader events with real-time WebSocket events
  const allEvents = useMemo(() => {
    const loaderEvents = workflow?.recent_events ?? [];
    const realtime = storeEvents ?? [];

    // Deduplicate by event id using a Map
    const eventMap = new Map<string, WorkflowEvent>();
    for (const event of loaderEvents) {
      eventMap.set(event.id, event);
    }
    for (const event of realtime) {
      eventMap.set(event.id, event);
    }

    // Sort by sequence number for correct ordering
    return Array.from(eventMap.values()).sort((a, b) => a.sequence - b.sequence);
  }, [workflow?.recent_events, storeEvents]);

  // Determine if this failed workflow can be resumed from checkpoint
  const isRecoverable = useMemo(() => {
    if (workflow?.status !== 'failed') return false;
    const failedEvents = allEvents
      .filter((e: WorkflowEvent) => e.event_type === 'workflow_failed')
      .sort((a: WorkflowEvent, b: WorkflowEvent) => b.sequence - a.sequence);
    const latest = failedEvents[0];
    return latest !== undefined && latest.data?.recoverable === true;
  }, [workflow?.status, allEvents]);

  const { resumeWorkflow, isActionPending } = useWorkflowActions();

  const handleResume = useCallback(async () => {
    if (!workflow) return;
    await resumeWorkflow(workflow.id);
  }, [workflow, resumeWorkflow]);

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

  return (
    <div className="flex flex-col h-full w-full">
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>WORKFLOW</PageHeader.Label>
          <div className="flex items-center gap-3">
            <PageHeader.Title title={workflow.issue_id}>
              {truncateWorkflowId(workflow.issue_id)}
            </PageHeader.Title>
            <PageHeader.Subtitle>{workflow.worktree_path}</PageHeader.Subtitle>
          </div>
        </PageHeader.Left>

        <PageHeader.Center>
          <PageHeader.Label>ELAPSED</PageHeader.Label>
          <PageHeader.Value>{elapsedTime}</PageHeader.Value>
        </PageHeader.Center>

        <PageHeader.Right>
          <StatusBadge status={workflow.status} />
        </PageHeader.Right>
      </PageHeader>

      <div className="flex-1 overflow-hidden grid grid-cols-2 gap-4 p-6 min-h-0">
        {/* Left column: Plan Review (when blocked) or Pipeline Canvas */}
        <div className="flex flex-col gap-4 overflow-y-auto min-h-0">
          {/* Plan Review - shown when workflow needs approval */}
          {needsApproval && (
            <ApprovalControls
              workflowId={workflow.id}
              planSummary={goalSummary}
              planMarkdown={workflow.plan_markdown}
              status="pending"
              className="flex-1"
            />
          )}

          {/* Recovery controls - shown for recoverable failed workflows */}
          {isRecoverable && (
            <div className="p-4 border border-border rounded-lg bg-card">
              <h4 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-2">
                RECOVERY
              </h4>
              <p className="text-sm text-muted-foreground mb-3">
                This workflow can be resumed from its last checkpoint.
              </p>
              <Button
                onClick={handleResume}
                disabled={isActionPending(workflow.id)}
                variant="outline"
              >
                <RotateCcw className="w-4 h-4 mr-2" />
                Resume
              </Button>
            </div>
          )}

          {/* Goal display - shown when not blocked or as secondary info */}
          {workflow.goal && !needsApproval && (
            <div className="p-4 border border-border rounded-lg bg-card/50 border-l-2 border-l-accent">
              <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-2">
                GOAL
              </h3>
              <p className="text-sm text-foreground">{workflow.goal}</p>
            </div>
          )}

          {/* Usage card - shows token usage breakdown by agent */}
          <UsageCard tokenUsage={workflow.token_usage} className="border-l-2 border-l-primary" />
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
                initialEvents={allEvents}
              />
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
