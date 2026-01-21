/**
 * @fileoverview Skeleton loader for settings pages showing a grid of profile cards.
 */
import { ProfileCardSkeleton } from './ProfileCardSkeleton';
import { Skeleton } from '@/components/ui/skeleton';

interface SettingsPageSkeletonProps {
  /** Number of skeleton cards to display (default: 6) */
  count?: number;
}

/**
 * Full page skeleton for the settings profiles page.
 * Displays a header with title and button placeholder, filter controls,
 * and a responsive grid of ProfileCardSkeleton components.
 */
export function SettingsPageSkeleton({ count = 6 }: SettingsPageSkeletonProps) {
  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header with title and create button */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-9 w-36" />
      </div>

      {/* Filter controls */}
      <div className="flex items-center gap-4">
        {/* Toggle group */}
        <div className="flex">
          <Skeleton className="h-9 w-12 rounded-r-none" />
          <Skeleton className="h-9 w-12 rounded-none" />
          <Skeleton className="h-9 w-12 rounded-l-none" />
        </div>
        {/* Search input */}
        <Skeleton className="h-9 w-64" />
      </div>

      {/* Profile cards grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: count }).map((_, i) => (
          <ProfileCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
