import { Skeleton } from '@/components/ui/skeleton';

interface ActivityLogSkeletonProps {
  lines?: number;
}

/**
 * ActivityLogSkeleton provides loading placeholder for ActivityLog.
 * Matches terminal-style log entry structure.
 */
export function ActivityLogSkeleton({ lines = 5 }: ActivityLogSkeletonProps) {
  return (
    <div data-slot="activity-log-skeleton" className="flex flex-col gap-1.5 p-4 font-mono">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          {/* Timestamp */}
          <Skeleton className="h-4 w-16" />

          {/* Agent */}
          <Skeleton className="h-4 w-20" />

          {/* Message - varying widths for natural look */}
          <Skeleton
            className="h-4 flex-1"
            style={{ maxWidth: `${50 + ((i * 17) % 40)}%` }}
          />
        </div>
      ))}
    </div>
  );
}
