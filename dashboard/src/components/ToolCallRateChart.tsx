/**
 * @fileoverview Stacked area chart showing cumulative tool calls over time by agent.
 */
import { useMemo } from 'react';
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from '@/components/ui/chart';
import type { ToolCall } from '@/types';

interface ToolCallRateChartProps {
  /** Array of tool calls from the workflow. */
  toolCalls: ToolCall[];
  /** Optional CSS class name. */
  className?: string;
}

/** Chart configuration with agent-specific colors. */
const chartConfig = {
  architect: {
    label: 'Architect',
    color: 'var(--agent-architect)',
  },
  developer: {
    label: 'Developer',
    color: 'var(--agent-developer)',
  },
  reviewer: {
    label: 'Reviewer',
    color: 'var(--agent-reviewer)',
  },
  pm: {
    label: 'PM',
    color: 'var(--agent-pm)',
  },
} satisfies ChartConfig;

type AgentKey = keyof typeof chartConfig;

interface ChartDataPoint {
  timestamp: number;
  timeLabel: string;
  architect: number;
  developer: number;
  reviewer: number;
  pm: number;
}

/**
 * Formats a timestamp as a relative time from workflow start.
 */
function formatRelativeTime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${seconds}s`;
}

/**
 * Transforms tool calls into cumulative chart data points.
 * Groups by agent and creates stacked cumulative counts.
 */
function transformToChartData(toolCalls: ToolCall[]): ChartDataPoint[] {
  // Filter out calls without timestamps and sort by time
  const validCalls = toolCalls
    .filter((tc): tc is ToolCall & { timestamp: string } => tc.timestamp !== null)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  if (validCalls.length === 0) {
    return [];
  }

  // Get the start time (first call)
  const startTime = new Date(validCalls[0].timestamp).getTime();

  // Track cumulative counts per agent
  const cumulativeCounts: Record<AgentKey, number> = {
    architect: 0,
    developer: 0,
    reviewer: 0,
    pm: 0,
  };

  // Create data points for each tool call
  const dataPoints: ChartDataPoint[] = validCalls.map((call) => {
    const callTime = new Date(call.timestamp).getTime();
    const relativeMs = callTime - startTime;
    const agent = (call.agent || 'developer') as AgentKey;

    // Increment the count for this agent
    if (agent in cumulativeCounts) {
      cumulativeCounts[agent]++;
    }

    return {
      timestamp: relativeMs,
      timeLabel: formatRelativeTime(relativeMs),
      architect: cumulativeCounts.architect,
      developer: cumulativeCounts.developer,
      reviewer: cumulativeCounts.reviewer,
      pm: cumulativeCounts.pm,
    };
  });

  return dataPoints;
}

/**
 * Determines which agents have data to show in the chart.
 */
function getActiveAgents(data: ChartDataPoint[]): AgentKey[] {
  if (data.length === 0) return [];

  const lastPoint = data[data.length - 1];
  const agents: AgentKey[] = ['pm', 'architect', 'developer', 'reviewer'];

  return agents.filter((agent) => lastPoint[agent] > 0);
}

/**
 * Stacked area chart showing cumulative tool calls over time by agent.
 * Displays the rate of tool usage throughout workflow execution.
 */
export function ToolCallRateChart({ toolCalls, className }: ToolCallRateChartProps) {
  const chartData = useMemo(() => transformToChartData(toolCalls), [toolCalls]);
  const activeAgents = useMemo(() => getActiveAgents(chartData), [chartData]);

  if (chartData.length === 0) {
    return (
      <div className={className}>
        <div className="flex h-[200px] items-center justify-center text-muted-foreground text-sm">
          No tool call data available
        </div>
      </div>
    );
  }

  // Build config for only active agents
  const activeConfig = Object.fromEntries(
    activeAgents.map((agent) => [agent, chartConfig[agent]])
  ) as ChartConfig;

  return (
    <ChartContainer config={activeConfig} className={className}>
      <AreaChart
        accessibilityLayer
        data={chartData}
        margin={{ left: 12, right: 12, top: 12, bottom: 12 }}
      >
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="timeLabel"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          minTickGap={32}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          allowDecimals={false}
        />
        <ChartTooltip
          cursor={false}
          content={<ChartTooltipContent indicator="dot" />}
        />
        <ChartLegend content={<ChartLegendContent />} />
        {activeAgents.map((agent) => (
          <Area
            key={agent}
            dataKey={agent}
            type="monotone"
            fill={`var(--color-${agent})`}
            fillOpacity={0.4}
            stroke={`var(--color-${agent})`}
            strokeWidth={2}
            stackId="a"
          />
        ))}
      </AreaChart>
    </ChartContainer>
  );
}
