/**
 * @fileoverview Type badge component for pipeline type display.
 */
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

/** Style map: pipeline_type -> Tailwind classes. */
const TYPE_STYLES: Record<string, string> = {
  full: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  review: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  pr_auto_fix: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
};

/** Label map: pipeline_type -> display label. */
const TYPE_LABELS: Record<string, string> = {
  full: 'Implementation',
  review: 'Review',
  pr_auto_fix: 'PR Fix',
};

/**
 * Displays a color-coded badge for the pipeline type.
 * Defaults to "Implementation" (full) when type is null or undefined.
 *
 * @param type - Pipeline type string, or null for legacy workflows
 */
export function TypeBadge({ type }: { type: string | null }) {
  const resolvedType = type ?? 'full';
  const label = TYPE_LABELS[resolvedType] ?? 'Implementation';
  const style = TYPE_STYLES[resolvedType] ?? TYPE_STYLES.full;

  return (
    <Badge variant="outline" className={cn(style)}>
      {label}
    </Badge>
  );
}
