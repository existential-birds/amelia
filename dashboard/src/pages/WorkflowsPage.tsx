/**
 * @fileoverview Main workflows listing page.
 *
 * Displays the active workflow's header with job queue below.
 */
import { useCallback, useMemo, useState } from 'react';
import { useLoaderData, useNavigate, useParams } from 'react-router-dom';
import { Copy } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { TypeBadge } from '@/components/TypeBadge';
import { JobQueue } from '@/components/JobQueue';
import { ApprovalControls } from '@/components/ApprovalControls';
import { PendingWorkflowControls } from '@/components/PendingWorkflowControls';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { success, error } from '@/components/Toast';
import { getActiveWorkflow } from '@/utils/workflow';
import { truncateWorkflowId } from '@/utils';
import { useElapsedTime, useAutoRevalidation } from '@/hooks';
import { useIsTablet } from '@/hooks/use-tablet';
import type { WorkflowSummary } from '@/types';
import type { workflowsLoader } from '@/loaders/workflows';

/**
 * Displays job queue for active workflows.
 *
 * Layout:
 * - Top: Workflow header (full width)
 * - Bottom: Job queue
 *
 * The active workflow is determined by priority:
 * 1. Running workflow (status === 'in_progress')
 * 2. Most recently started completed workflow
 *
 * Selection is managed via URL:
 * - /workflows - shows active workflow
 * - /workflows/:id - shows specific workflow
 */
export default function WorkflowsPage() {
  const { workflows, detail, detailError } = useLoaderData<typeof workflowsLoader>();
  const navigate = useNavigate();
  const params = useParams<{ id?: string }>();
  const isTablet = useIsTablet();
  const [activeTab, setActiveTab] = useState('all');

  // Auto-revalidate when any workflow's status changes (approval events, completion, etc.)
  useAutoRevalidation();

  // Filter workflows by pipeline type tab
  const filteredWorkflows = useMemo(() => {
    if (activeTab === 'all') return workflows;
    return workflows.filter((w: WorkflowSummary) => {
      const type = w.pipeline_type ?? 'full';
      return type === activeTab;
    });
  }, [workflows, activeTab]);

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
          <PageHeader.Value>{elapsedTime}</PageHeader.Value>
        </PageHeader.Center>
        {detail && (
          <PageHeader.Right>
            <TypeBadge type={detail.pipeline_type ?? null} />
            <StatusBadge status={detail.status} />
          </PageHeader.Right>
        )}
      </PageHeader>
      <Separator />

      {/* Tab filtering by pipeline type */}
      <div className="px-4 pt-3">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="full">Implementation</TabsTrigger>
            <TabsTrigger value="review">Review</TabsTrigger>
            <TabsTrigger value="pr_auto_fix">PR Fix</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

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

      {/* Pending Workflow Controls - shown when workflow is queued */}
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
            worktreePath={detail.worktree_path}
          />
        </div>
      )}

      {/* Bottom: Job queue */}
      <div className="flex-1 p-4 overflow-hidden relative z-10 min-h-[300px]">
        <ScrollArea className="h-full overflow-hidden">
          {detailError && (
            <div className="p-4 text-destructive text-sm">
              Failed to load workflow details: {detailError}
            </div>
          )}
          <JobQueue
            workflows={filteredWorkflows}
            selectedId={displayedId}
            onSelect={handleSelect}
            collapsible={isTablet}
            defaultCollapsed={true}
          />
        </ScrollArea>
      </div>
    </div>
  );
}
