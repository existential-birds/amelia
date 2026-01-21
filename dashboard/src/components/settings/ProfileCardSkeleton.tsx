/**
 * @fileoverview Skeleton loader for ProfileCard component.
 */
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Skeleton placeholder that matches the ProfileCard structure.
 * Displays animated loading state for card header with title and badge,
 * and card content with driver badge, model text, and working directory.
 */
export function ProfileCardSkeleton() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2">
          {/* Profile name */}
          <Skeleton className="h-4 w-24" />
          {/* Active badge (sometimes visible) */}
          <Skeleton className="h-5 w-16" />
        </div>
        {/* Menu button */}
        <Skeleton className="h-8 w-8" />
      </CardHeader>
      <CardContent>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            {/* Driver badge */}
            <Skeleton className="h-5 w-20" />
            {/* Model name */}
            <Skeleton className="h-4 w-32" />
          </div>
          {/* Working directory */}
          <Skeleton className="h-4 w-48" />
        </div>
      </CardContent>
    </Card>
  );
}
