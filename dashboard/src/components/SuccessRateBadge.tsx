import { cn } from '@/lib/utils';

interface SuccessRateBadgeProps {
  /** Success rate as decimal (0-1). */
  rate: number;
  /** Optional className for styling. */
  className?: string;
}

/**
 * Displays a success rate as a percentage, colored green/yellow/red by the
 * reliability thresholds applied below.
 */
export function SuccessRateBadge({ rate, className }: SuccessRateBadgeProps) {
  const percentage = Math.round(rate * 100);

  const colorClass =
    percentage >= 90
      ? 'text-green-400'
      : percentage >= 70
        ? 'text-yellow-400'
        : 'text-red-400';

  return (
    <span className={cn('tabular-nums font-medium', colorClass, className)}>
      {percentage}%
    </span>
  );
}
