/**
 * @fileoverview Collapsible PR comment section for workflow detail view.
 *
 * Shows a summary bar with fixed/failed/skipped counts and collapsible
 * comment rows with status icons, file:line, body snippet, and external link.
 */
import { CheckCircle2, XCircle, MinusCircle, ExternalLink } from 'lucide-react';
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import type { PRCommentData } from '@/types';

/** Status icon component based on resolution status. */
function StatusIcon({ status }: { status: PRCommentData['status'] }) {
  switch (status) {
    case 'fixed':
      return <CheckCircle2 className="size-4 text-green-500 shrink-0" />;
    case 'failed':
      return <XCircle className="size-4 text-red-500 shrink-0" />;
    case 'skipped':
      return <MinusCircle className="size-4 text-muted-foreground shrink-0" />;
  }
}

/** Format file_path:line or "General" for null paths. */
function formatLocation(filePath: string | null, line: number | null): string {
  if (!filePath) return 'General';
  return line != null ? `${filePath}:${line}` : filePath;
}

interface PRCommentSectionProps {
  comments: PRCommentData[];
}

/**
 * Collapsible PR comment section with summary bar and status icons.
 *
 * Displays a summary of fixed/failed/skipped comments and individual
 * comment rows with file location, body snippet, and external link.
 */
export function PRCommentSection({ comments }: PRCommentSectionProps) {
  const fixed = comments.filter((c) => c.status === 'fixed').length;
  const failed = comments.filter((c) => c.status === 'failed').length;
  const skipped = comments.filter((c) => c.status === 'skipped').length;

  return (
    <div className="p-4 border border-border rounded-lg bg-card/50">
      <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-3">
        REVIEW COMMENTS
      </h3>

      {/* Summary bar */}
      <div className="flex items-center gap-3 mb-3 text-sm font-mono">
        <span className="text-green-500">{fixed} fixed</span>
        <span className="text-muted-foreground/40">&bull;</span>
        <span className="text-red-500">{failed} failed</span>
        <span className="text-muted-foreground/40">&bull;</span>
        <span className="text-muted-foreground">{skipped} skipped</span>
      </div>

      {/* Comment rows */}
      <div className="flex flex-col gap-1">
        {comments.map((comment) => (
          <Collapsible key={comment.comment_id}>
            <div className="flex items-center gap-2 rounded-md hover:bg-muted/30 transition-colors">
              <CollapsibleTrigger className="flex-1 flex items-center gap-2 py-1.5 px-2 text-left min-w-0">
                <StatusIcon status={comment.status} />
                <span className="font-mono text-xs text-accent shrink-0">
                  {formatLocation(comment.file_path, comment.line)}
                </span>
                <span className="text-xs text-muted-foreground truncate">
                  {comment.body.slice(0, 80)}
                  {comment.body.length > 80 ? '...' : ''}
                </span>
              </CollapsibleTrigger>
              <a
                href={comment.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 p-1.5 text-muted-foreground hover:text-foreground transition-colors"
                aria-label={`View comment on GitHub`}
              >
                <ExternalLink className="size-3.5" />
              </a>
            </div>

            <CollapsibleContent>
              <div className={cn(
                'ml-6 pl-2 py-2 border-l-2 text-xs space-y-1',
                comment.status === 'fixed' && 'border-l-green-500/30',
                comment.status === 'failed' && 'border-l-red-500/30',
                comment.status === 'skipped' && 'border-l-muted-foreground/30',
              )}>
                <p className="text-foreground/80 whitespace-pre-wrap">{comment.body}</p>
                <p className="text-muted-foreground">
                  by {comment.author}
                  {comment.file_path && (
                    <> &middot; {formatLocation(comment.file_path, comment.line)}</>
                  )}
                </p>
                {comment.status_reason && (
                  <p className="text-muted-foreground/60 italic">
                    {comment.status === 'skipped' ? 'Skipped' : 'Reason'}: {comment.status_reason}
                  </p>
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        ))}
      </div>
    </div>
  );
}
