import { cn } from '@/lib/utils';

interface SparklineProps {
  /** Array of numeric values to display. */
  data: number[];
  /** Stroke color (CSS variable or color value). */
  color: string;
  /** Optional className for the SVG element. */
  className?: string;
}

/**
 * Renders a small inline line chart (sparkline) for trend visualization.
 * Fixed height of 24px, width scales with container or defaults to 80px.
 */
export function Sparkline({ data, color, className }: SparklineProps) {
  const width = Math.max(data.length * 2, 80);
  const height = 24;
  const padding = 2;

  // Handle edge cases
  if (data.length === 0) {
    return (
      <svg
        role="img"
        aria-label="Empty sparkline"
        viewBox={`0 0 ${width} ${height}`}
        className={cn('w-20 h-6', className)}
      />
    );
  }

  // Normalize data to fit in viewBox
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1; // Avoid division by zero

  const normalize = (value: number): number => {
    return height - padding - ((value - min) / range) * (height - padding * 2);
  };

  // Generate points for polyline
  const xStep = data.length > 1 ? (width - padding * 2) / (data.length - 1) : 0;
  const points = data
    .map((value, index) => {
      const x = padding + index * xStep;
      const y = normalize(value);
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg
      role="img"
      aria-label="Sparkline chart"
      viewBox={`0 0 ${width} ${height}`}
      className={cn('w-20 h-6', className)}
    >
      <polyline
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}
