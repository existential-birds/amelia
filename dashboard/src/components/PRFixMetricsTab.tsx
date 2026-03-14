/**
 * @fileoverview PR Fix Metrics tab content for the Analytics page.
 * Displays summary cards, latency line chart, success breakdown bar chart,
 * and classification audit log.
 */
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from '@/components/ui/empty';
import { Bar, BarChart, Line, LineChart, XAxis, YAxis } from 'recharts';
import { Activity } from 'lucide-react';
import { ClassificationAuditLog } from '@/components/ClassificationAuditLog';
import type { PRAutoFixMetricsResponse } from '@/types';

interface PRFixMetricsTabProps {
  /** Metrics response data from the API. */
  metrics: PRAutoFixMetricsResponse;
  /** Current date preset for filtering. */
  preset: string;
}

/**
 * Formats a date string for chart display.
 * Uses UTC to avoid timezone off-by-one issues.
 */
function formatChartDate(dateStr: string): string {
  const [year, month, day] = dateStr.split('-').map(Number) as [number, number, number];
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

/** Chart config for the latency line chart. */
const latencyChartConfig: ChartConfig = {
  avg_latency_s: {
    label: 'Avg Latency',
    color: 'var(--chart-model-1)',
  },
};

/** Chart config for the success breakdown bar chart. */
const breakdownChartConfig: ChartConfig = {
  fixed: {
    label: 'Fixed',
    color: 'oklch(0.723 0.191 149.579)',
  },
  failed: {
    label: 'Failed',
    color: 'oklch(0.637 0.237 25.331)',
  },
  skipped: {
    label: 'Skipped',
    color: 'oklch(0.795 0.184 86.047)',
  },
};

/**
 * PR Fix Metrics tab with summary cards, charts, and classification audit log.
 */
export function PRFixMetricsTab({ metrics, preset }: PRFixMetricsTabProps) {
  const { summary, daily, by_aggressiveness } = metrics;

  // Empty state when no data
  if (daily.length === 0 && by_aggressiveness.length === 0 && summary.total_runs === 0) {
    return (
      <div className="flex flex-col gap-6">
        <Empty className="h-[400px]">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Activity />
            </EmptyMedia>
            <EmptyTitle>No PR auto-fix data</EmptyTitle>
            <EmptyDescription>
              No PR auto-fix runs found for this period.
              Configure PR auto-fix on a profile to start collecting metrics.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard label="Total Runs" value={summary.total_runs.toLocaleString()} />
        <SummaryCard
          label="Fix Rate"
          value={`${(summary.fix_rate * 100).toFixed(1)}%`}
        />
        <SummaryCard
          label="Avg Latency"
          value={`${summary.avg_latency_seconds.toFixed(1)}s`}
        />
        <SummaryCard
          label="Comments Processed"
          value={summary.total_comments_processed.toLocaleString()}
        />
      </div>

      {/* Latency trend line chart */}
      {daily.length > 0 && (
        <div className="border border-border rounded-lg p-4 bg-card/50">
          <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-4">
            LATENCY TREND
          </h3>
          <ChartContainer config={latencyChartConfig} className="h-64 w-full" role="figure">
            <LineChart data={daily} margin={{ left: 12, right: 12, top: 12, bottom: 12 }}>
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
                tickFormatter={(value) => `${value}s`}
                tickMargin={8}
                width={50}
                className="text-xs"
              />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    formatter={(value) => `${Number(value).toFixed(1)}s`}
                    labelFormatter={(label) => formatChartDate(String(label))}
                  />
                }
              />
              <Line
                dataKey="avg_latency_s"
                type="monotone"
                stroke="var(--chart-model-1)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ChartContainer>
        </div>
      )}

      {/* Success breakdown stacked bar chart */}
      {by_aggressiveness.length > 0 && (
        <div className="border border-border rounded-lg p-4 bg-card/50">
          <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-4">
            SUCCESS BREAKDOWN BY AGGRESSIVENESS
          </h3>
          <ChartContainer config={breakdownChartConfig} className="h-64 w-full" role="figure">
            <BarChart
              data={by_aggressiveness}
              margin={{ left: 12, right: 12, top: 12, bottom: 12 }}
            >
              <XAxis
                dataKey="level"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                className="text-xs"
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                width={50}
                className="text-xs"
              />
              <ChartTooltip
                content={<ChartTooltipContent />}
              />
              <Bar
                dataKey="fixed"
                stackId="breakdown"
                fill="oklch(0.723 0.191 149.579)"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="failed"
                stackId="breakdown"
                fill="oklch(0.637 0.237 25.331)"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="skipped"
                stackId="breakdown"
                fill="oklch(0.795 0.184 86.047)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ChartContainer>
        </div>
      )}

      {/* Classification audit log */}
      <div className="border border-border rounded-lg p-4 bg-card/50">
        <ClassificationAuditLog preset={preset} />
      </div>
    </div>
  );
}

/**
 * Simple summary card for displaying a metric.
 */
function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border rounded-lg p-4 bg-card/50">
      <p className="font-heading text-[10px] font-semibold tracking-widest text-muted-foreground mb-1">
        {label.toUpperCase()}
      </p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
