import { useState, useEffect } from 'react';
import { Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Time thresholds for loading feedback messages (in milliseconds).
 */
const SLOW_THRESHOLD_MS = 10000;
const VERY_SLOW_THRESHOLD_MS = 30000;

/**
 * Loading stage based on elapsed time.
 */
type LoadingStage = 'normal' | 'slow' | 'verySlow';

/**
 * Loading spinner with progressive timeout feedback.
 *
 * Shows a standard spinner initially, then displays helpful messages
 * if loading takes longer than expected:
 * - After 10s: "Taking longer than expected..."
 * - After 30s: "Check your connection or try refreshing"
 *
 * @param props - Component props
 * @param props.className - Optional additional CSS classes
 * @returns React element with spinner and optional timeout messages
 */
export function LoadingTimeout({ className }: { className?: string }) {
  const [stage, setStage] = useState<LoadingStage>('normal');

  useEffect(() => {
    const slowTimer = setTimeout(() => setStage('slow'), SLOW_THRESHOLD_MS);
    const verySlowTimer = setTimeout(
      () => setStage('verySlow'),
      VERY_SLOW_THRESHOLD_MS
    );

    return () => {
      clearTimeout(slowTimer);
      clearTimeout(verySlowTimer);
    };
  }, []);

  const isSlow = stage === 'slow' || stage === 'verySlow';
  const isVerySlow = stage === 'verySlow';

  return (
    <div
      role="status"
      className={cn(
        'flex flex-col items-center justify-center gap-4',
        className
      )}
    >
      <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />

      {isSlow && !isVerySlow && (
        <p className="text-sm text-muted-foreground animate-in fade-in">
          Taking longer than expected...
        </p>
      )}

      {isVerySlow && (
        <div className="flex flex-col items-center gap-2 animate-in fade-in">
          <div className="flex items-center gap-2 text-yellow-500">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm font-medium">
              Taking longer than expected...
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Check your connection or try refreshing the page
          </p>
        </div>
      )}

      <span className="sr-only">Loading</span>
    </div>
  );
}
