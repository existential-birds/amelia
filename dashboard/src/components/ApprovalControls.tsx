/**
 * @fileoverview Approval controls for workflow plan review.
 */
import { useFetcher } from 'react-router-dom';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ai-elements/loader';
import { Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Response shape from approve/reject actions. */
interface ActionResponse {
  success: boolean;
  error?: string;
}

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
  const approveFetcher = useFetcher<ActionResponse>();
  const rejectFetcher = useFetcher<ActionResponse>();
  const isPending = approveFetcher.state !== 'idle' || rejectFetcher.state !== 'idle';
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectionFeedback, setRejectionFeedback] = useState('');

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

            {!showRejectForm ? (
              <Button
                type="button"
                variant="outline"
                disabled={isPending}
                onClick={() => setShowRejectForm(true)}
                className="border-destructive text-destructive hover:bg-destructive hover:text-foreground focus-visible:ring-destructive/50"
              >
                <X className="w-4 h-4 mr-2" />
                Reject
              </Button>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowRejectForm(false);
                  setRejectionFeedback('');
                }}
                className="text-muted-foreground"
              >
                Cancel
              </Button>
            )}
          </div>

          {showRejectForm && (
            <rejectFetcher.Form
              method="post"
              action={`/workflows/${workflowId}/reject`}
              className="flex flex-col gap-3"
            >
              <div className="flex flex-col gap-2">
                <label htmlFor="feedback" className="text-sm font-medium">
                  Rejection feedback
                </label>
                <textarea
                  id="feedback"
                  name="feedback"
                  value={rejectionFeedback}
                  onChange={(e) => setRejectionFeedback(e.target.value)}
                  placeholder="Explain why this plan needs revision..."
                  rows={3}
                  required
                  disabled={isPending}
                  className={cn(
                    "placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-input/30 border-input w-full min-w-0 rounded-md border bg-transparent px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm resize-none",
                    "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                    "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive"
                  )}
                />
              </div>
              <Button
                type="submit"
                variant="outline"
                disabled={isPending || !rejectionFeedback.trim()}
                className="w-fit border-destructive text-destructive hover:bg-destructive hover:text-foreground focus-visible:ring-destructive/50"
              >
                {isPending ? (
                  <Loader className="w-4 h-4 mr-2" />
                ) : (
                  <X className="w-4 h-4 mr-2" />
                )}
                Submit Rejection
              </Button>
            </rejectFetcher.Form>
          )}

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
