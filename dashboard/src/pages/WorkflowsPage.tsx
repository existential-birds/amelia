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
import { useCallback } from 'react';
import { useLoaderData, useNavigate, useParams } from 'react-router-dom';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import { ActivityLog } from '@/components/ActivityLog';
import { JobQueue } from '@/components/JobQueue';
import { ApprovalControls } from '@/components/ApprovalControls';
import { getActiveWorkflow } from '@/utils/workflow';
import { useElapsedTime, useAutoRevalidation } from '@/hooks';
import { buildPipeline } from '@/utils/pipeline';
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
 * @returns The workflows page UI
 */
export default function WorkflowsPage() {
  const { workflows, detail } = useLoaderData<typeof workflowsLoader>();
  const navigate = useNavigate();
  const params = useParams<{ id?: string }>();

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

  if (workflows.length === 0 && !detail) {
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
          <PageHeader.Value glow>{elapsedTime}</PageHeader.Value>
        </PageHeader.Center>
        {detail && (
          <PageHeader.Right>
            {detail.status === 'blocked' && (
              <ApprovalControls
                workflowId={detail.id}
                planSummary={detail.plan ? `Plan with ${detail.plan.tasks.length} tasks` : 'No plan generated'}
                status="pending"
              />
            )}
            <StatusBadge status={detail.status} />
          </PageHeader.Right>
        )}
      </PageHeader>
      <Separator />
      <WorkflowCanvas pipeline={pipeline ?? undefined} />

      {/* Bottom: Queue + Activity (split) - ScrollArea provides overflow handling */}
      <div className="flex-1 grid grid-cols-[320px_1fr] grid-rows-[1fr] gap-4 p-4 overflow-hidden relative z-10 min-h-0">
        <ScrollArea className="h-full overflow-hidden">
          <JobQueue
            workflows={workflows}
            selectedId={displayedId}
            onSelect={handleSelect}
          />
        </ScrollArea>
        <ScrollArea className="h-full overflow-hidden">
          {detail ? (
            <ActivityLog workflowId={detail.id} initialEvents={detail.recent_events} />
          ) : null}
        </ScrollArea>
      </div>
    </div>
  );
}
