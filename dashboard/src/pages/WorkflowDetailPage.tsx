/**
 * @fileoverview Workflow detail page with full status display.
 */
import { useCallback, useMemo } from 'react';
import { useLoaderData } from 'react-router-dom';
import { RotateCcw } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { TypeBadge } from '@/components/TypeBadge';
import { RequestReviewDialog } from '@/components/RequestReviewDialog';
import { PRCommentSection } from '@/components/PRCommentSection';
import { ApprovalControls } from '@/components/ApprovalControls';
import { UsageCard } from '@/components/UsageCard';
import { Button } from '@/components/ui/button';
import { useElapsedTime, useAutoRevalidation } from '@/hooks';
import { useWorkflowActions } from '@/hooks/useWorkflowActions';
import { truncateWorkflowId } from '@/utils';
import { workflowDetailLoader } from '@/loaders';
import { useWorkflowStore } from '@/store/workflowStore';
import type { WorkflowEvent } from '@/types';

/**
 * Displays comprehensive workflow details with progress.
 *
 * Shows header with status, approval controls (when blocked),
 * recovery controls (when recoverable), and usage stats.
 *
 * @returns The workflow detail page UI
 */
export default function WorkflowDetailPage() {
  const { workflow } = useLoaderData<typeof workflowDetailLoader>();
  const elapsedTime = useElapsedTime(workflow);

  // Use targeted selector to only subscribe to this workflow's events (for recovery detection)
  const workflowId = workflow?.id ?? '';
  const storeEvents = useWorkflowStore(
    useCallback((state) => state.eventsByWorkflow[workflowId], [workflowId])
  );

  // Auto-revalidate when this workflow's status changes (approval events, completion, etc.)
  useAutoRevalidation(workflow?.id);

  // Determine if this failed workflow can be resumed from checkpoint.
  // Primary: workflow.recoverable (set by API client, survives refresh).
  // Fallback: real-time store events (only when API hasn't set recoverable yet).
  const isRecoverable = useMemo(() => {
    if (workflow?.status !== 'failed') return false;
    // If API has explicitly set recoverable, trust it (survives page refresh)
    if (workflow.recoverable !== undefined) return workflow.recoverable;
    // Fallback to real-time store events only when API hasn't determined recoverability
    const events = storeEvents ?? [];
    const failedEvents = events
      .filter((e: WorkflowEvent) => e.event_type === 'workflow_failed')
      .sort((a: WorkflowEvent, b: WorkflowEvent) => b.sequence - a.sequence);
    const latest = failedEvents[0];
    return latest !== undefined && latest.data?.recoverable === true;
  }, [workflow?.status, workflow?.recoverable, storeEvents]);

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
          <RequestReviewDialog workflowId={workflow.id} />
          <TypeBadge type={workflow.pipeline_type ?? null} />
          <StatusBadge status={workflow.status} />
        </PageHeader.Right>
      </PageHeader>

      <div className="flex-1 overflow-hidden p-6 min-h-0">
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

          {/* PR Comment Section - shown for pr_auto_fix workflows with comments */}
          {workflow.pipeline_type === 'pr_auto_fix' &&
            workflow.pr_comments &&
            workflow.pr_comments.length > 0 && (
              <PRCommentSection comments={workflow.pr_comments} />
            )}

          {/* Usage card - shows token usage breakdown by agent */}
          <UsageCard tokenUsage={workflow.token_usage} className="border-l-2 border-l-primary" />
        </div>
      </div>
    </div>
  );
}
