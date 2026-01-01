import { Skeleton } from '@/components/ui/skeleton';

/**
 * Props for the ActivityLogSkeleton component.
 * @property lines - Number of skeleton lines to display (default: 5)
 */
interface ActivityLogSkeletonProps {
  lines?: number;
}

/**
 * ActivityLogSkeleton provides loading placeholder for ActivityLog.
 * Matches terminal-style log entry structure.
 *
 * @param props - Component props
 * @param props.lines - Number of skeleton lines to display (default: 5)
 * @returns React element with skeleton loading placeholders mimicking log entries
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
