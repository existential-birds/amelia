/**
 * @fileoverview Trend chart component for costs visualization.
 */
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { Area, AreaChart, XAxis, YAxis } from 'recharts';
import { formatCost } from '@/utils/workflow';
import type { UsageTrendPoint } from '@/types';

interface CostsTrendChartProps {
  /** Trend data points to display. */
  data: UsageTrendPoint[];
  /** Optional className for styling. */
  className?: string;
}

const chartConfig = {
  cost_usd: {
    label: 'Cost',
    color: 'hsl(var(--primary))',
  },
} satisfies ChartConfig;

/**
 * Formats a date string for chart display.
 * Uses UTC to avoid timezone-related off-by-one display issues.
 * @param dateStr - ISO date string (YYYY-MM-DD)
 * @returns Formatted date (e.g., "Jan 15")
 */
function formatChartDate(dateStr: string): string {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

/**
 * Displays a line/area chart of daily costs over time.
 *
 * @param props - Component props
 * @returns Chart visualization or empty state
 */
export function CostsTrendChart({ data, className }: CostsTrendChartProps) {
  if (data.length === 0) {
    return (
      <div
        data-slot="costs-trend-chart"
        role="figure"
        className="flex items-center justify-center h-64 text-muted-foreground"
      >
        No data for this period
      </div>
    );
  }

  return (
    <div data-slot="costs-trend-chart" className={className}>
      <ChartContainer config={chartConfig} className="h-64 w-full" role="figure">
        <AreaChart data={data} margin={{ left: 12, right: 12, top: 12, bottom: 12 }}>
          <defs>
            <linearGradient id="fillCost" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
              <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            tickFormatter={formatChartDate}
            tickMargin={8}
            className="text-xs"
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => `$${value}`}
            tickMargin={8}
            width={50}
            className="text-xs"
          />
          <ChartTooltip
            cursor={false}
            content={
              <ChartTooltipContent
                formatter={(value, _name) => (
                  <div className="flex flex-col gap-1">
                    <span className="font-medium">{formatCost(Number(value))}</span>
                  </div>
                )}
                labelFormatter={(label) => formatChartDate(String(label))}
              />
            }
          />
          <Area
            dataKey="cost_usd"
            type="monotone"
            fill="url(#fillCost)"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
          />
        </AreaChart>
      </ChartContainer>
    </div>
  );
}
