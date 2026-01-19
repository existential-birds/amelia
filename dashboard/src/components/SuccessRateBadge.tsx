/**
 * @fileoverview Success rate badge with color-coded thresholds.
 */
import { cn } from '@/lib/utils';

interface SuccessRateBadgeProps {
  /** Success rate as decimal (0-1). */
  rate: number;
  /** Optional className for styling. */
  className?: string;
}

/**
 * Displays a success rate percentage with color-coded feedback.
 *
 * Color thresholds:
 * - Green (>= 90%): High reliability
 * - Yellow (70-89%): Moderate reliability
 * - Red (< 70%): Low reliability
 *
 * @param props - Component props
 * @returns Colored percentage badge
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
