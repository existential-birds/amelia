/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Main workflows listing page with canvas visualization.
 *
 * Displays the active workflow's pipeline canvas at the top with
 * job queue and activity log in a split view below.
 */
import { useCallback, useEffect, useRef } from 'react';
import { useLoaderData, useFetcher } from 'react-router-dom';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import { ActivityLog } from '@/components/ActivityLog';
import { ActivityLogSkeleton } from '@/components/ActivityLogSkeleton';
import { JobQueue } from '@/components/JobQueue';
import { useWorkflowStore } from '@/store/workflowStore';
import { getActiveWorkflow, formatElapsedTime } from '@/utils/workflow';
import { buildPipeline } from '@/utils/pipeline';
import type { workflowsLoader, workflowDetailLoader } from '@/loaders/workflows';

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
 * @returns The workflows page UI
 */
export default function WorkflowsPage() {
  const { workflows, activeDetail } = useLoaderData<typeof workflowsLoader>();
  const selectedId = useWorkflowStore((state) => state.selectedWorkflowId);
  const selectWorkflow = useWorkflowStore((state) => state.selectWorkflow);
  const fetcher = useFetcher<typeof workflowDetailLoader>();
  const jobQueueRef = useRef<HTMLDivElement>(null);

  // Auto-select active workflow
  const activeWorkflow = getActiveWorkflow(workflows);
  const displayedId = selectedId ?? activeWorkflow?.id ?? null;

  // Determine which detail to show:
  // 1. If user selected a workflow and fetcher has data for THAT workflow, use fetcher data
  // 2. If displaying the active workflow, use pre-loaded activeDetail
  // 3. Otherwise show loading state
  const isLoadingDetail = fetcher.state !== 'idle';
  let detail = null;
  if (selectedId && fetcher.data?.workflow?.id === selectedId) {
    detail = fetcher.data.workflow;
  } else if (displayedId === activeWorkflow?.id) {
    detail = activeDetail;
  }

  // Fetch detail when user selects a different workflow
  // NOTE: Uses existing /workflows/:id route and workflowDetailLoader
  const handleSelect = useCallback((id: string | null) => {
    selectWorkflow(id);
    if (id && id !== activeWorkflow?.id) {
      fetcher.load(`/workflows/${id}`);
    }
  }, [selectWorkflow, activeWorkflow?.id, fetcher]);

  // Clear selection when clicking outside the job queue
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Element;
      // Check if click is outside job queue and not on sidebar
      const isInsideJobQueue = jobQueueRef.current?.contains(target);
      const isInsideSidebar = target.closest('[data-slot="sidebar"]');

      if (!isInsideJobQueue && !isInsideSidebar && selectedId) {
        selectWorkflow(null);
      }
    };

    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [selectedId, selectWorkflow]);

  if (workflows.length === 0) {
    return <WorkflowEmptyState variant="no-workflows" />;
  }

  // Build pipeline for canvas visualization
  const pipeline = detail ? buildPipeline(detail) : null;

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      {/* Top: Header + Canvas (full width) */}
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>WORKFLOW</PageHeader.Label>
          <div className="flex items-center gap-3">
            <PageHeader.Title>{detail?.issue_id ?? 'SELECT JOB'}</PageHeader.Title>
            {detail?.worktree_name && (
              <PageHeader.Subtitle>{detail.worktree_name}</PageHeader.Subtitle>
            )}
          </div>
        </PageHeader.Left>
        <PageHeader.Center>
          <PageHeader.Label>ELAPSED</PageHeader.Label>
          <PageHeader.Value glow>{formatElapsedTime(detail)}</PageHeader.Value>
        </PageHeader.Center>
        {detail && (
          <PageHeader.Right>
            <StatusBadge status={detail.status} />
          </PageHeader.Right>
        )}
      </PageHeader>
      <Separator />
      <WorkflowCanvas
        pipeline={pipeline ?? undefined}
        isLoading={isLoadingDetail && !!displayedId}
      />

      {/* Bottom: Queue + Activity (split) - ScrollArea provides overflow handling */}
      <div className="flex-1 grid grid-cols-[320px_1fr] grid-rows-[1fr] gap-4 p-4 overflow-hidden relative z-10 min-h-0">
        <ScrollArea className="h-full overflow-hidden">
          <div ref={jobQueueRef}>
            <JobQueue
              workflows={workflows}
              selectedId={displayedId}
              onSelect={handleSelect}
            />
          </div>
        </ScrollArea>
        <ScrollArea className="h-full overflow-hidden">
          {detail ? (
            <ActivityLog workflowId={detail.id} initialEvents={detail.recent_events} />
          ) : isLoadingDetail ? (
            <ActivityLogSkeleton />
          ) : null}
        </ScrollArea>
      </div>
    </div>
  );
}
