import { Skeleton } from '@/components/ui/skeleton';

/**
 * Props for the JobQueueSkeleton component.
 * @property count - Number of skeleton items to display (default: 3)
 */
interface JobQueueSkeletonProps {
  count?: number;
}

/**
 * JobQueueSkeleton provides loading placeholder for JobQueue.
 * Matches the structure of JobQueueItem for smooth transition.
 *
 * @param props - Component props
 * @param props.count - Number of skeleton items to display (default: 3)
 * @returns React element with skeleton loading placeholders
 */
export function JobQueueSkeleton({ count = 3 }: JobQueueSkeletonProps) {
  return (
    <div data-slot="job-queue-skeleton" className="flex flex-col gap-2 p-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 p-3 rounded-lg border border-border/50"
        >
          {/* Status indicator */}
          <Skeleton className="h-4 w-16 rounded-md" />

          {/* Content */}
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-12" /> {/* Issue ID */}
            <Skeleton className="h-3 w-32" /> {/* Worktree name */}
          </div>

          {/* Stage */}
          <Skeleton className="h-3 w-20" />
        </div>
      ))}
    </div>
  );
}
