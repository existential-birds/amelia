/**
 * @fileoverview Approval controls for workflow plan review.
 */
import { useFetcher } from 'react-router-dom';
import { useState } from 'react';
import Markdown from 'react-markdown';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ai-elements/loader';
import { Check, X, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Response shape from approve/reject actions.
 * @property success - Whether the action completed successfully
 * @property error - Error message if the action failed
 */
interface ActionResponse {
  success: boolean;
  error?: string;
}

/**
 * Possible states for the approval workflow.
 * pending: awaiting user decision, approved: plan accepted, rejected: plan needs revision.
 */
type ApprovalStatus = 'pending' | 'approved' | 'rejected';

/**
 * Props for the ApprovalControls component.
 * @property workflowId - Unique identifier for the workflow being approved
 * @property planSummary - Brief description of the plan to display
 * @property planMarkdown - Full plan markdown content (optional)
 * @property status - Current approval status (defaults to 'pending')
 * @property className - Optional additional CSS classes
 */
interface ApprovalControlsProps {
  workflowId: string;
  planSummary: string;
  planMarkdown?: string | null;
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
 *   planMarkdown="## Plan\n\n1. Add login form\n2. Create auth service"
 *   status="pending"
 * />
 * ```
 */
export function ApprovalControls({
  workflowId,
  planSummary,
  planMarkdown,
  status = 'pending',
  className,
}: ApprovalControlsProps) {
  const approveFetcher = useFetcher<ActionResponse>();
  const rejectFetcher = useFetcher<ActionResponse>();
  const isPending = approveFetcher.state !== 'idle' || rejectFetcher.state !== 'idle';
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectionFeedback, setRejectionFeedback] = useState('');
  const [showPlanDetails, setShowPlanDetails] = useState(true);

  return (
    <div
      data-slot="approval-controls"
      className={cn(
        'p-4 border border-border rounded-lg bg-card flex flex-col min-w-0 overflow-hidden',
        className
      )}
    >
      <h4 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-2">
        PLAN REVIEW
      </h4>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-heading text-lg font-semibold leading-tight">
          {planSummary}
        </h3>
        {planMarkdown && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowPlanDetails(!showPlanDetails)}
            className="text-muted-foreground hover:text-foreground"
          >
            {showPlanDetails ? (
              <>
                <ChevronUp className="w-4 h-4 mr-1" />
                Hide plan
              </>
            ) : (
              <>
                <ChevronDown className="w-4 h-4 mr-1" />
                Show plan
              </>
            )}
          </Button>
        )}
      </div>

      {planMarkdown && showPlanDetails && (
        <div className="min-h-48 max-h-[60vh] mb-4 border border-border rounded-md bg-muted/30 overflow-y-auto">
          <div className="p-4 text-sm text-foreground/90 leading-relaxed prose prose-sm prose-invert max-w-none prose-headings:font-heading prose-headings:text-foreground prose-p:text-foreground/90 prose-strong:text-foreground prose-code:text-accent prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-pre:overflow-x-auto prose-li:text-foreground/90 prose-blockquote:border-accent prose-blockquote:text-foreground/70 [&_pre]:max-w-full [&_pre]:whitespace-pre-wrap [&_code]:break-all">
            <Markdown>{planMarkdown}</Markdown>
          </div>
        </div>
      )}

      {!planMarkdown && (
        <p className="text-sm text-muted-foreground mb-4 italic">
          No plan available. Awaiting plan generation.
        </p>
      )}

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
                <div className="flex justify-between items-center">
                  <label htmlFor="feedback" className="text-sm font-medium">
                    Rejection feedback
                  </label>
                  <span
                    id="feedback-counter"
                    className={cn(
                      "text-xs text-muted-foreground",
                      rejectionFeedback.length >= 1000 && "text-destructive"
                    )}
                  >
                    {rejectionFeedback.length}/1000
                  </span>
                </div>
                <textarea
                  id="feedback"
                  name="feedback"
                  value={rejectionFeedback}
                  onChange={(e) => setRejectionFeedback(e.target.value)}
                  placeholder="Explain why this plan needs revision..."
                  rows={3}
                  required
                  autoFocus
                  maxLength={1000}
                  aria-describedby="feedback-counter"
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
