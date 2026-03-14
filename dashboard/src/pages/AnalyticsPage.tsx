/**
 * @fileoverview Analytics page with Costs and PR Fix Metrics tabs.
 * Combines existing costs visualization with new PR auto-fix metrics.
 */
import { useMemo } from 'react';
import { useLoaderData, useSearchParams } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Download, Calendar, ChevronDown, BarChart3, Activity } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { CostsTrendChart } from '@/components/CostsTrendChart';
import { Sparkline } from '@/components/Sparkline';
import { SuccessRateBadge } from '@/components/SuccessRateBadge';
import { PRFixMetricsTab } from '@/components/PRFixMetricsTab';
import { DataTable } from '@/components/ui/data-table';
import { DataTableColumnHeader } from '@/components/ui/data-table-column-header';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from '@/components/ui/empty';
import { formatTokens, formatCost, formatDuration } from '@/utils/workflow';
import { getModelColor } from '@/utils/chart-colors';
import { cn } from '@/lib/utils';
import type { analyticsLoader } from '@/loaders/analytics';
import type { UsageByModel } from '@/types';

/**
 * Date range preset options.
 */
const PRESETS = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: 'all', label: 'All time' },
];

/**
 * Get a filename-safe version of the preset label for exports.
 */
function getExportFilename(preset: string): string {
  return getPresetLabel(preset).toLowerCase().replace(/\s+/g, '-');
}

/**
 * Get the display label for a preset value.
 */
function getPresetLabel(preset: string): string {
  return PRESETS.find((p) => p.value === preset)?.label ?? 'Custom range';
}

/**
 * Returns a grammatically correct description for the preset range.
 */
function getPresetDescription(preset: string): string {
  if (preset === 'all') return 'all time';
  return `the last ${getPresetLabel(preset).toLowerCase()}`;
}

/**
 * Escape a CSV field value to handle special characters.
 */
function escapeCsvField(value: string | number): string {
  let text = String(value);
  if (/^[=+\-@]/.test(text)) {
    text = `'${text}`;
  }
  const needsQuote = /[",\n\r]/.test(text);
  text = text.replace(/"/g, '""');
  return needsQuote ? `"${text}"` : text;
}

/**
 * Export usage data to CSV.
 */
function exportCSV(byModel: UsageByModel[], dateRange: string) {
  const rows = [
    ['Model', 'Workflows', 'Success Rate', 'Tokens', 'Cost (USD)'],
    ...byModel.map((m) => [
      m.model,
      m.workflows,
      m.success_rate != null ? `${Math.round(m.success_rate * 100)}%` : 'N/A',
      m.tokens,
      m.cost_usd.toFixed(2),
    ]),
  ];
  const csv = rows.map((r) => r.map(escapeCsvField).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `costs-${dateRange}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Calculate period-over-period delta percentage.
 */
function calculateDelta(current: number, previous: number | null | undefined): number | null {
  if (previous === null || previous === undefined || previous === 0) {
    return null;
  }
  return ((current - previous) / previous) * 100;
}

/**
 * Analytics page with tabbed Costs and PR Fix Metrics views.
 */
export default function AnalyticsPage() {
  const { usage, metrics, currentPreset } = useLoaderData<typeof analyticsLoader>();
  const [_searchParams, setSearchParams] = useSearchParams();

  const handlePresetChange = (preset: string) => {
    setSearchParams({ preset });
  };

  // Calculate cost delta
  const costDelta = calculateDelta(
    usage.summary.total_cost_usd,
    usage.summary.previous_period_cost_usd
  );

  // Sort models by cost descending for consistent color mapping
  const sortedModels = useMemo(
    () => [...usage.by_model].sort((a, b) => b.cost_usd - a.cost_usd),
    [usage.by_model]
  );

  // Create color lookup based on cost rank
  const modelColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    sortedModels.forEach((model, index) => {
      map[model.model] = getModelColor(index);
    });
    return map;
  }, [sortedModels]);

  // Table columns for costs breakdown
  const columns: ColumnDef<UsageByModel>[] = useMemo(
    () => [
      {
        accessorKey: 'model',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Model" align="left" />
        ),
        cell: ({ row }) => (
          <span
            className="font-medium"
            style={{ color: modelColorMap[row.getValue('model') as string] }}
          >
            {row.getValue('model')}
          </span>
        ),
      },
      {
        accessorKey: 'success_rate',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Success" align="right" />
        ),
        cell: ({ row }) => {
          const rate = row.getValue('success_rate') as number | null | undefined;
          return rate != null ? (
            <div className="text-right">
              <SuccessRateBadge rate={rate} />
            </div>
          ) : (
            <div className="text-right text-muted-foreground">--</div>
          );
        },
      },
      {
        accessorKey: 'workflows',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Workflows" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right text-muted-foreground tabular-nums">
            {row.getValue('workflows')}
          </div>
        ),
      },
      {
        accessorKey: 'tokens',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Tokens" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right text-muted-foreground tabular-nums">
            {formatTokens(row.getValue('tokens'))}
          </div>
        ),
      },
      {
        accessorKey: 'cost_usd',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Cost" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right text-cost-value tabular-nums">
            {formatCost(row.getValue('cost_usd'))}
          </div>
        ),
      },
      {
        id: 'share',
        header: () => <div className="text-right">Share</div>,
        cell: ({ row }) => {
          const share =
            usage.summary.total_cost_usd > 0
              ? ((row.original.cost_usd / usage.summary.total_cost_usd) * 100).toFixed(1)
              : '0.0';
          return <div className="text-right text-muted-foreground tabular-nums">{share}%</div>;
        },
      },
      {
        id: 'trend',
        header: () => <div className="text-right">Trend</div>,
        cell: ({ row }) => {
          const trend = row.original.trend;
          if (!trend || trend.length === 0) {
            return <div className="text-right text-muted-foreground">--</div>;
          }
          return (
            <div className="flex justify-end">
              <Sparkline
                data={trend}
                color={modelColorMap[row.original.model] ?? 'var(--chart-model-1)'}
                className="w-16 h-5"
              />
            </div>
          );
        },
      },
    ],
    [modelColorMap, usage.summary.total_cost_usd]
  );

  return (
    <div className="flex flex-col w-full">
      {/* Header */}
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>ANALYTICS</PageHeader.Label>
          <PageHeader.Title>Metrics & Insights</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Right>
          {/* Desktop: horizontal buttons */}
          <div className="hidden md:flex gap-1">
            {PRESETS.map((preset) => (
              <button
                key={preset.value}
                onClick={() => handlePresetChange(preset.value)}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                  currentPreset === preset.value
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                )}
              >
                {preset.label}
              </button>
            ))}
          </div>

          {/* Mobile: dropdown */}
          <div className="md:hidden">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  <Calendar className="size-4" />
                  <span>{getPresetLabel(currentPreset)}</span>
                  <ChevronDown className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuRadioGroup value={currentPreset} onValueChange={handlePresetChange}>
                  {PRESETS.map((p) => (
                    <DropdownMenuRadioItem key={p.value} value={p.value}>
                      {p.label}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </PageHeader.Right>
      </PageHeader>

      <div className="flex flex-col gap-6 p-6">
        <Tabs defaultValue="costs">
          <TabsList>
            <TabsTrigger value="costs">
              <BarChart3 className="size-4" />
              Costs
            </TabsTrigger>
            <TabsTrigger value="pr-fix-metrics">
              <Activity className="size-4" />
              PR Fix Metrics
            </TabsTrigger>
          </TabsList>

          {/* Costs tab */}
          <TabsContent value="costs">
            <CostsTabContent
              usage={usage}
              currentPreset={currentPreset}
              costDelta={costDelta}
              columns={columns}
              modelColorMap={modelColorMap}
              onPresetChange={handlePresetChange}
            />
          </TabsContent>

          {/* PR Fix Metrics tab */}
          <TabsContent value="pr-fix-metrics">
            <PRFixMetricsTab metrics={metrics} preset={currentPreset} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

/**
 * Costs tab content extracted from the original CostsPage.
 */
function CostsTabContent({
  usage,
  currentPreset,
  costDelta,
  columns,
  modelColorMap,
  onPresetChange,
}: {
  usage: ReturnType<typeof useLoaderData<typeof analyticsLoader>>['usage'];
  currentPreset: string;
  costDelta: number | null;
  columns: ColumnDef<UsageByModel>[];
  modelColorMap: Record<string, string>;
  onPresetChange: (preset: string) => void;
}) {
  // Empty state
  if (usage.summary.total_workflows === 0) {
    return (
      <div className="pt-4">
        <Empty className="h-[400px]">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <BarChart3 />
            </EmptyMedia>
            <EmptyTitle>No usage data</EmptyTitle>
            <EmptyDescription>
              No workflows ran in {getPresetDescription(currentPreset)}.
              Try a longer time range or start a new workflow.
            </EmptyDescription>
          </EmptyHeader>
          {currentPreset !== 'all' && (
            <Button variant="outline" onClick={() => onPresetChange('all')}>
              View all time
            </Button>
          )}
        </Empty>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 pt-4">
      {/* Summary row */}
      <div className="flex items-center gap-2 text-sm flex-wrap">
        <span className="text-primary font-semibold">
          {formatCost(usage.summary.total_cost_usd)}
        </span>
        {costDelta !== null && (
          <span
            className={cn(
              'text-xs font-medium',
              costDelta >= 0 ? 'text-red-400' : 'text-green-400'
            )}
          >
            {costDelta >= 0 ? '+' : ''}
            {costDelta.toFixed(1)}% vs prev
          </span>
        )}
        <span className="text-muted-foreground">|</span>
        <span className="text-foreground">{usage.summary.total_workflows} workflows</span>
        <span className="text-muted-foreground">|</span>
        <span className="text-foreground">{formatTokens(usage.summary.total_tokens)} tokens</span>
        <span className="text-muted-foreground">|</span>
        <span className="text-foreground">{formatDuration(usage.summary.total_duration_ms)}</span>
        {usage.summary.success_rate != null && (
          <>
            <span className="text-muted-foreground">|</span>
            <SuccessRateBadge rate={usage.summary.success_rate} />
            <span className="text-muted-foreground">success</span>
          </>
        )}
      </div>

      {/* Trend chart */}
      <div className="border border-border rounded-lg p-4 bg-card/50">
        <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-4">
          DAILY COSTS
        </h3>
        <CostsTrendChart data={usage.trend} />
      </div>

      {/* Model breakdown */}
      <div className="border border-border rounded-lg p-4 bg-card/50">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground">
            BY MODEL
          </h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => exportCSV(usage.by_model, getExportFilename(currentPreset))}
          >
            <Download className="size-4 mr-1" />
            Export CSV
          </Button>
        </div>

        {/* Desktop: DataTable */}
        <div className="hidden md:block">
          <DataTable columns={columns} data={usage.by_model} />
        </div>

        {/* Mobile: Cards */}
        <div className="md:hidden space-y-3">
          {usage.by_model.map((model) => {
            const share =
              usage.summary.total_cost_usd > 0
                ? ((model.cost_usd / usage.summary.total_cost_usd) * 100).toFixed(1)
                : '0.0';
            return (
              <div
                key={model.model}
                className="bg-card rounded-lg p-4"
              >
                <div className="flex justify-between items-center">
                  <span
                    className="font-medium"
                    style={{ color: modelColorMap[model.model] }}
                  >
                    {model.model}
                  </span>
                  {model.success_rate != null && (
                    <SuccessRateBadge rate={model.success_rate} />
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
                  <div className="text-muted-foreground">
                    Workflows: <span className="text-foreground">{model.workflows}</span>
                  </div>
                  <div className="text-muted-foreground">
                    Tokens: <span className="text-foreground">{formatTokens(model.tokens)}</span>
                  </div>
                  <div className="text-muted-foreground">
                    Cost: <span className="text-cost-value">{formatCost(model.cost_usd)}</span>
                  </div>
                  <div className="text-muted-foreground">
                    Share: <span className="text-foreground">{share}%</span>
                  </div>
                </div>
                {model.trend && model.trend.length > 0 && (
                  <Sparkline
                    data={model.trend}
                    color={modelColorMap[model.model] ?? 'var(--chart-model-1)'}
                    className="mt-2 w-full h-6"
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
