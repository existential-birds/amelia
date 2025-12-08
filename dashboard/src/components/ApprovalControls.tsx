/**
 * @fileoverview Approval controls for workflow plan review.
 */
import { useFetcher } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ai-elements/loader';
import { Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Possible states for the approval workflow. */
type ApprovalStatus = 'pending' | 'approved' | 'rejected';

/**
 * Props for the ApprovalControls component.
 * @property workflowId - Unique identifier for the workflow being approved
 * @property planSummary - Brief description of the plan to display
 * @property status - Current approval status (defaults to 'pending')
 * @property className - Optional additional CSS classes
 */
interface ApprovalControlsProps {
  workflowId: string;
  planSummary: string;
  status?: ApprovalStatus;
  className?: string;
}

/**
 * Displays approve/reject buttons for workflow plan review.
 *
 * Shows pending controls when awaiting decision, or a status message
 * once approved/rejected. Uses React Router fetchers for form submissions.
 *
 * @param props - Component props
 * @returns The approval controls UI
 *
 * @example
 * ```tsx
 * <ApprovalControls
 *   workflowId="wf-123"
 *   planSummary="Implement user authentication"
 *   status="pending"
 * />
 * ```
 */
export function ApprovalControls({
  workflowId,
  planSummary,
  status = 'pending',
  className,
}: ApprovalControlsProps) {
  const approveFetcher = useFetcher();
  const rejectFetcher = useFetcher();
  const isPending = approveFetcher.state !== 'idle' || rejectFetcher.state !== 'idle';

  return (
    <div
      data-slot="approval-controls"
      className={cn(
        'p-4 border border-border rounded-lg bg-card',
        className
      )}
    >
      <h3 className="font-heading text-lg font-semibold mb-2">
        {planSummary}
      </h3>

      <p className="text-sm text-muted-foreground mb-4">
        Review and approve this plan to proceed with implementation.
      </p>

      {status === 'pending' && (
        <div className="flex flex-col gap-3">
          <div className="flex gap-3">
            <approveFetcher.Form method="post" action={`/workflows/${workflowId}/approve`}>
              <Button
                type="submit"
                disabled={isPending}
                className="bg-status-completed hover:bg-status-completed/90 focus-visible:ring-status-completed/50"
              >
                {isPending ? (
                  <Loader className="w-4 h-4 mr-2" />
                ) : (
                  <Check className="w-4 h-4 mr-2" />
                )}
                Approve
              </Button>
            </approveFetcher.Form>

            <rejectFetcher.Form method="post" action={`/workflows/${workflowId}/reject`}>
              <input type="hidden" name="feedback" value="Rejected by user" />
              <Button
                type="submit"
                variant="outline"
                disabled={isPending}
                className="border-destructive text-destructive hover:bg-destructive hover:text-foreground focus-visible:ring-destructive/50"
              >
                {isPending ? (
                  <Loader className="w-4 h-4 mr-2" />
                ) : (
                  <X className="w-4 h-4 mr-2" />
                )}
                Reject
              </Button>
            </rejectFetcher.Form>
          </div>

          {approveFetcher.data?.error && (
            <p className="text-sm text-destructive mt-2">{approveFetcher.data.error}</p>
          )}

          {rejectFetcher.data?.error && (
            <p className="text-sm text-destructive mt-2">{rejectFetcher.data.error}</p>
          )}
        </div>
      )}

      {status === 'approved' && (
        <div className="flex items-center gap-2 text-status-completed font-semibold">
          <Check className="w-4 h-4" />
          Plan approved. Implementation starting...
        </div>
      )}

      {status === 'rejected' && (
        <div className="flex items-center gap-2 text-destructive font-semibold">
          <X className="w-4 h-4" />
          Plan rejected. Awaiting revision...
        </div>
      )}
    </div>
  );
}
