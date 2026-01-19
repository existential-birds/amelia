/**
 * @fileoverview Trend chart component for costs visualization.
 * Supports multi-model breakdown with stacked area and line views.
 */
import { useState, useMemo } from 'react';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Area, AreaChart, Line, LineChart, XAxis, YAxis } from 'recharts';
import { formatCost } from '@/utils/workflow';
import { getModelColor } from '@/utils/chart-colors';
import type { UsageTrendPoint } from '@/types';

interface CostsTrendChartProps {
  /** Trend data points to display. */
  data: UsageTrendPoint[];
  /** Optional className for styling. */
  className?: string;
}

type ChartType = 'stacked' | 'line';

/**
 * Formats a date string for chart display.
 * Uses UTC to avoid timezone-related off-by-one display issues.
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

/**
 * Displays a multi-model cost trend chart with toggle between stacked and line views.
 */
export function CostsTrendChart({ data, className }: CostsTrendChartProps) {
  const [chartType, setChartType] = useState<ChartType>('stacked');

  // Extract unique models sorted by total cost descending
  const { models, chartData, chartConfig } = useMemo(() => {
    // Aggregate total cost per model across all days
    const modelTotals: Record<string, number> = {};
    for (const point of data) {
      if (point.by_model) {
        for (const [model, cost] of Object.entries(point.by_model)) {
          modelTotals[model] = (modelTotals[model] || 0) + cost;
        }
      }
    }

    // Sort models by total cost descending
    const sortedModels = Object.entries(modelTotals)
      .sort((a, b) => b[1] - a[1])
      .map(([model]) => model);

    // If no by_model data, fall back to single series
    if (sortedModels.length === 0) {
      return {
        models: [],
        chartData: data,
        chartConfig: {
          cost_usd: {
            label: 'Cost',
            color: 'var(--primary)',
          },
        } as ChartConfig,
      };
    }

    // Transform data for recharts (flatten by_model into top-level keys)
    const transformedData = data.map((point) => ({
      date: point.date,
      ...Object.fromEntries(
        sortedModels.map((model) => [model, point.by_model?.[model] ?? 0])
      ),
    }));

    // Build chart config for legend
    const config: ChartConfig = {};
    sortedModels.forEach((model, index) => {
      config[model] = {
        label: model,
        color: getModelColor(index),
      };
    });

    return {
      models: sortedModels,
      chartData: transformedData,
      chartConfig: config,
    };
  }, [data]);

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

  // Single series fallback (no by_model data)
  if (models.length === 0) {
    return (
      <div data-slot="costs-trend-chart" className={className}>
        <ChartContainer
          config={{ cost_usd: { label: 'Cost', color: 'var(--primary)' } }}
          className="h-64 w-full"
          role="figure"
        >
          <AreaChart data={chartData} margin={{ left: 12, right: 12, top: 12, bottom: 12 }}>
            <defs>
              <linearGradient id="fillCost" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
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
                  formatter={(value) => (
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
              stroke="var(--primary)"
              strokeWidth={2}
            />
          </AreaChart>
        </ChartContainer>
      </div>
    );
  }

  // Multi-model chart
  return (
    <div data-slot="costs-trend-chart" className={className}>
      <div className="flex justify-end mb-4">
        <ToggleGroup
          type="single"
          value={chartType}
          onValueChange={(value) => value && setChartType(value as ChartType)}
          aria-label="Chart type"
        >
          <ToggleGroupItem value="stacked" aria-label="Stacked area chart">
            Stacked
          </ToggleGroupItem>
          <ToggleGroupItem value="line" aria-label="Line chart">
            Lines
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      <div>
        <ChartContainer config={chartConfig} className="h-64 w-full" role="figure">
          {chartType === 'stacked' ? (
            <AreaChart data={chartData} margin={{ left: 12, right: 12, top: 12, bottom: 12 }}>
              <defs>
                {models.map((model, index) => (
                  <linearGradient key={model} id={`gradient-${index}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={getModelColor(index)} stopOpacity={0.4} />
                    <stop offset="95%" stopColor={getModelColor(index)} stopOpacity={0.05} />
                  </linearGradient>
                ))}
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
                content={
                  <ChartTooltipContent
                    labelFormatter={(label) => formatChartDate(String(label))}
                  />
                }
              />
              {models.map((model, index) => (
                <Area
                  key={model}
                  dataKey={model}
                  stackId="costs"
                  type="monotone"
                  fill={`url(#gradient-${index})`}
                  stroke={getModelColor(index)}
                  strokeWidth={1.5}
                />
              ))}
            </AreaChart>
          ) : (
            <LineChart data={chartData} margin={{ left: 12, right: 12, top: 12, bottom: 12 }}>
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
                content={
                  <ChartTooltipContent
                    labelFormatter={(label) => formatChartDate(String(label))}
                  />
                }
              />
              {models.map((model, index) => (
                <Line
                  key={model}
                  dataKey={model}
                  type="monotone"
                  stroke={getModelColor(index)}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              ))}
            </LineChart>
          )}
        </ChartContainer>
      </div>
    </div>
  );
}
