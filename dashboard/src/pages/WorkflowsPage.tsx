/**
 * @fileoverview Main workflows listing page with canvas visualization.
 *
 * Displays the active workflow's pipeline canvas at the top with
 * job queue and activity log in a split view below.
 */
import { useCallback } from 'react';
import { useLoaderData, useNavigate, useParams } from 'react-router-dom';
import { Copy } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import { ActivityLog } from '@/components/ActivityLog';
import { JobQueue } from '@/components/JobQueue';
import { ApprovalControls } from '@/components/ApprovalControls';
import { PendingWorkflowControls } from '@/components/PendingWorkflowControls';
import { PlanningIndicator } from '@/components/PlanningIndicator';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { success, error } from '@/components/Toast';
import { getActiveWorkflow } from '@/utils/workflow';
import { truncateWorkflowId } from '@/utils';
import { useElapsedTime, useAutoRevalidation } from '@/hooks';
import { useIsTablet } from '@/hooks/use-tablet';
import { buildPipelineFromEvents } from '@/utils/pipeline';
import type { workflowsLoader } from '@/loaders/workflows';

/**
 * Displays workflow canvas and job queue with activity log.
 *
 * Layout:
 * - Top: Workflow header and pipeline canvas (full width)
 * - Bottom: Job queue (1/3) and activity log (2/3) side by side
 *
 * The active workflow is determined by priority:
 * 1. Running workflow (status === 'in_progress')
 * 2. Most recently started completed workflow
 *
 * Selection is managed via URL:
 * - /workflows - shows active workflow
 * - /workflows/:id - shows specific workflow
 *
 * @returns React element for the workflows page with canvas visualization and job queue
 */
export default function WorkflowsPage() {
  const { workflows, detail, detailError } = useLoaderData<typeof workflowsLoader>();
  const navigate = useNavigate();
  const params = useParams<{ id?: string }>();
  const isTablet = useIsTablet();

  // Auto-revalidate when any workflow's status changes (approval events, completion, etc.)
  useAutoRevalidation();

  // Determine which workflow is displayed
  const activeWorkflow = getActiveWorkflow(workflows);
  const displayedId = params.id ?? activeWorkflow?.id ?? null;
  const elapsedTime = useElapsedTime(detail);

  // Handle workflow selection by navigating to URL
  const handleSelect = useCallback((id: string | null) => {
    if (id) {
      navigate(`/workflows/${id}`);
    } else {
      navigate('/workflows');
    }
  }, [navigate]);

  const handleCopy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      success('Issue ID copied to clipboard');
    } catch {
      error('Failed to copy to clipboard');
    }
  }, []);

  if (workflows.length === 0 && !detail) {
    return <WorkflowEmptyState variant="no-workflows" />;
  }

  // Build pipeline from events for canvas visualization (real-time updates)
  const pipeline = buildPipelineFromEvents(
    detail?.recent_events ?? [],
    { showDefaultPipeline: true }
  );

  return (
    <div className="flex flex-col h-full w-full overflow-y-auto">
      {/* Top: Header + Canvas (full width) */}
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>WORKFLOW</PageHeader.Label>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <PageHeader.Title title={detail?.issue_id}>
                {detail?.issue_id ? truncateWorkflowId(detail.issue_id) : 'SELECT JOB'}
              </PageHeader.Title>
              {detail?.issue_id && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="h-6 w-6 text-muted-foreground hover:text-foreground"
                      onClick={() => handleCopy(detail.issue_id)}
                      aria-label="Copy Issue ID"
                    >
                      <Copy className="size-3" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Copy Issue ID</TooltipContent>
                </Tooltip>
              )}
            </div>
            {detail?.worktree_path && (
              <PageHeader.Subtitle>{detail.worktree_path}</PageHeader.Subtitle>
            )}
          </div>
        </PageHeader.Left>
        <PageHeader.Center>
          <PageHeader.Label>ELAPSED</PageHeader.Label>
          <PageHeader.Value glow>{elapsedTime}</PageHeader.Value>
        </PageHeader.Center>
        {detail && (
          <PageHeader.Right>
            <StatusBadge status={detail.status} />
          </PageHeader.Right>
        )}
      </PageHeader>
      <Separator />
      <WorkflowCanvas pipeline={pipeline} className="h-48 lg:h-64" />

      {/* Plan Review - shown when workflow needs approval */}
      {detail?.status === 'blocked' && (
        <div className="px-4 pt-4">
          <ApprovalControls
            workflowId={detail.id}
            planSummary={detail.goal || 'Awaiting plan generation'}
            planMarkdown={detail.plan_markdown}
            status="pending"
          />
        </div>
      )}

      {/* Planning Indicator - shown when Architect is generating plan */}
      {detail?.status === 'planning' && (
        <div className="px-4 pt-4">
          <PlanningIndicator
            workflowId={detail.id}
            startedAt={detail.created_at}
          />
        </div>
      )}

      {/* Pending Workflow Controls - shown when workflow is queued (not planning) */}
      {detail?.status === 'pending' && (
        <div className="px-4 pt-4">
          <PendingWorkflowControls
            workflowId={detail.id}
            createdAt={detail.created_at}
            hasPlan={!!detail.plan_markdown}
            worktreeHasActiveWorkflow={workflows.some(
              (w) =>
                w.id !== detail.id &&
                w.worktree_path === detail.worktree_path &&
                w.status === 'in_progress'
            )}
          />
        </div>
      )}

      {/* Bottom: Queue + Activity (split) - ScrollArea provides overflow handling */}
      {/* Responsive: stacked on mobile/tablet (grid-cols-1), side-by-side on lg+ */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(280px,320px)_1fr] gap-4 p-4 overflow-hidden relative z-10 min-h-[300px]">
        <ScrollArea className="h-full lg:max-h-none overflow-hidden">
          <JobQueue
            workflows={workflows}
            selectedId={displayedId}
            onSelect={handleSelect}
            collapsible={isTablet}
            defaultCollapsed={true}
          />
        </ScrollArea>
        <ScrollArea className="h-full min-h-[200px] overflow-hidden">
          {detailError ? (
            <div className="p-4 text-destructive text-sm">
              Failed to load workflow details: {detailError}
            </div>
          ) : detail ? (
            <ActivityLog workflowId={detail.id} initialEvents={detail.recent_events} />
          ) : null}
        </ScrollArea>
      </div>
    </div>
  );
}
