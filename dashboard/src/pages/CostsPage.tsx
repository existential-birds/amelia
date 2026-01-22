/**
 * @fileoverview Costs page for usage monitoring and analysis.
 */
import { useMemo } from 'react';
import { useLoaderData, useNavigate, useSearchParams } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Download, Calendar, ChevronDown, BarChart3 } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { CostsTrendChart } from '@/components/CostsTrendChart';
import { Sparkline } from '@/components/Sparkline';
import { SuccessRateBadge } from '@/components/SuccessRateBadge';
import { DataTable } from '@/components/ui/data-table';
import { DataTableColumnHeader } from '@/components/ui/data-table-column-header';
import { Button } from '@/components/ui/button';
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
import type { costsLoader } from '@/loaders/costs';
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
function getExportFilename(preset: string | null): string {
  return getPresetLabel(preset).toLowerCase().replace(/\s+/g, '-');
}

/**
 * Get the display label for a preset value.
 * Returns the preset label if found, or "Custom range" for null/unknown values.
 */
function getPresetLabel(preset: string | null): string {
  if (preset === null) {
    return 'Custom range';
  }
  return PRESETS.find((p) => p.value === preset)?.label ?? 'Custom range';
}

/**
 * Returns a grammatically correct description for the preset range.
 * Used in empty-state messages.
 */
function getPresetDescription(preset: string | null): string {
  if (preset === 'all') return 'all time';
  if (preset === null) return 'the selected range';
  return `the last ${getPresetLabel(preset).toLowerCase()}`;
}

/**
 * Escape a CSV field value to handle special characters.
 * - Neutralizes formula injection by prefixing formula triggers with single quote
 * - Escapes double quotes by doubling them
 * - Wraps fields in quotes if they contain commas, quotes, or newlines
 */
function escapeCsvField(value: string | number): string {
  let text = String(value);
  // Neutralize spreadsheet formula interpretation
  if (/^[=+\-@]/.test(text)) {
    text = `'${text}`;
  }
  // Check if quoting is needed
  const needsQuote = /[",\n\r]/.test(text);
  // Escape existing double quotes
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
 * Costs page displaying usage metrics, trends, and model breakdown.
 */
export default function CostsPage() {
  const { usage, currentPreset } = useLoaderData<typeof costsLoader>();
  const [_searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const handlePresetChange = (preset: string) => {
    setSearchParams({ preset });
  };

  const handleModelClick = (model: UsageByModel) => {
    navigate(`/history?model=${encodeURIComponent(model.model)}`);
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

  // Table columns
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
            <div className="text-right text-muted-foreground">—</div>
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
            return <div className="text-right text-muted-foreground">—</div>;
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

  // Empty state
  if (usage.summary.total_workflows === 0) {
    return (
      <div className="flex flex-col w-full">
        <PageHeader>
          <PageHeader.Left>
            <PageHeader.Label>COSTS</PageHeader.Label>
            <PageHeader.Title>Usage & Spending</PageHeader.Title>
          </PageHeader.Left>
          <PageHeader.Center>
            <PageHeader.Value>$0.00</PageHeader.Value>
          </PageHeader.Center>
          <PageHeader.Right>
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
                  <DropdownMenuRadioGroup value={currentPreset ?? ''} onValueChange={handlePresetChange}>
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

        <div className="flex-1 p-6">
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
              <Button variant="outline" onClick={() => handlePresetChange('all')}>
                View all time
              </Button>
            )}
          </Empty>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full">
      {/* Header */}
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>COSTS</PageHeader.Label>
          <PageHeader.Title>Usage & Spending</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Center>
          <div className="flex flex-col items-center">
            <PageHeader.Value>{formatCost(usage.summary.total_cost_usd)}</PageHeader.Value>
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
          </div>
        </PageHeader.Center>
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
                <DropdownMenuRadioGroup value={currentPreset ?? ''} onValueChange={handlePresetChange}>
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
        {/* Summary row */}
        <div className="flex items-center gap-2 text-sm flex-wrap">
          <span className="text-primary font-semibold">
            {formatCost(usage.summary.total_cost_usd)}
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-foreground">{usage.summary.total_workflows} workflows</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-foreground">{formatTokens(usage.summary.total_tokens)} tokens</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-foreground">{formatDuration(usage.summary.total_duration_ms)}</span>
          {usage.summary.success_rate != null && (
            <>
              <span className="text-muted-foreground">·</span>
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
            <DataTable columns={columns} data={usage.by_model} onRowClick={handleModelClick} />
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
                  onClick={() => handleModelClick(model)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleModelClick(model);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  className="bg-card rounded-lg p-4 cursor-pointer hover:bg-muted/50 transition-colors"
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
    </div>
  );
}
