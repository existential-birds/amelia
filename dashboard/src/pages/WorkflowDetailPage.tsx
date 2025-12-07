/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { useLoaderData } from 'react-router-dom';
import { WorkflowHeader } from '@/components/WorkflowHeader';
import { WorkflowProgress } from '@/components/WorkflowProgress';
import { ActivityLog } from '@/components/ActivityLog';
import { ApprovalControls } from '@/components/ApprovalControls';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import type { WorkflowDetail } from '@/types';

interface LoaderData {
  workflow: WorkflowDetail;
}

export default function WorkflowDetailPage() {
  const { workflow } = useLoaderData() as LoaderData;

  // Calculate progress from plan tasks
  const completedTasks = workflow.plan?.tasks.filter(t => t.status === 'completed').length || 0;
  const totalTasks = workflow.plan?.tasks.length || 0;

  // Check if workflow needs approval (blocked status)
  const needsApproval = workflow.status === 'blocked';

  // Generate plan summary for approval controls
  const planSummary = workflow.plan
    ? `Plan with ${workflow.plan.tasks.length} tasks`
    : 'No plan available';

  // Convert plan to pipeline format for WorkflowCanvas (if plan exists)
  const pipeline = workflow.plan
    ? {
        nodes: workflow.plan.tasks.map((task) => ({
          id: task.id,
          label: task.agent,
          subtitle: task.description,
          status: task.status === 'completed'
            ? 'completed' as const
            : task.status === 'in_progress'
            ? 'active' as const
            : task.status === 'failed'
            ? 'blocked' as const
            : 'pending' as const,
        })),
        edges: workflow.plan.tasks
          .flatMap((task) =>
            task.dependencies.map((depId) => ({
              from: depId,
              to: task.id,
              label: '',
              status: 'completed' as const,
            }))
          ),
      }
    : null;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <WorkflowHeader workflow={workflow} />

      {/* Main content area */}
      <div className="flex-1 overflow-hidden grid grid-cols-2 gap-4 p-6">
        {/* Left column: Progress, Canvas, and Approval Controls */}
        <div className="flex flex-col gap-4 overflow-y-auto">
          {/* Progress */}
          <div className="p-4 border border-border rounded-lg bg-card/50">
            <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-3">
              PROGRESS
            </h3>
            <WorkflowProgress completed={completedTasks} total={totalTasks} />
          </div>

          {/* Workflow Canvas (visual pipeline) */}
          {pipeline && (
            <div className="p-4 border border-border rounded-lg bg-card/50">
              <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-3">
                PIPELINE
              </h3>
              <WorkflowCanvas pipeline={pipeline} />
            </div>
          )}

          {/* Approval Controls (only shown when blocked) */}
          {needsApproval && (
            <ApprovalControls
              workflowId={workflow.id}
              planSummary={planSummary}
              status="pending"
            />
          )}
        </div>

        {/* Right column: Activity Log */}
        <div className="border border-border rounded-lg bg-card/50 overflow-hidden">
          <ActivityLog
            workflowId={workflow.id}
            initialEvents={workflow.recent_events}
          />
        </div>
      </div>
    </div>
  );
}

// Loader function will be added in Plan 09
// export async function loader({ params }) { ... }
