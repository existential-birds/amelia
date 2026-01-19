# Costs View Redesign

**Date:** 2026-01-19
**Status:** Proposed

## Overview

This design improves the dashboard's costs view to provide better visual hierarchy, multi-model insights, and mobile usability.

### Goals

- Reduce gold color overuse—reserve it for the single most important metric (total cost)
- Show per-model cost trends in the chart with distinct, harmonious colors
- Enable users to toggle between stacked area and line chart views
- Make date range selection mobile-friendly via collapsible dropdown
- Add period-over-period comparison to contextualize spending
- Enhance the table with sorting, sparklines, and CSV export
- Show goal completion rate (success rate) per model and aggregate
- Provide skeleton loading states and helpful empty states

### Non-Goals

- Custom date range picker (presets only for now)
- Real-time updates or websocket streaming
- User-configurable color assignments
- Drill-down into individual workflow costs from this view

## Data Model & API Changes

### Extended UsageTrendPoint

The backend extends the existing trend data to include per-model breakdown:

```typescript
interface UsageTrendPoint {
  date: string;                         // ISO date (YYYY-MM-DD)
  cost_usd: number;                     // Total cost for this date
  workflows: number;                    // Total workflows for this date
  by_model: Record<string, number>;     // Per-model costs
  // e.g., { "claude-sonnet-4": 5.20, "gpt-4o": 2.10 }
}
```

### Extended UsageSummary

Add previous period comparison data:

```typescript
interface UsageSummary {
  total_cost_usd: number;
  total_workflows: number;
  total_tokens: number;
  total_duration_ms: number;
  cache_hit_rate?: number;
  cache_savings_usd?: number;
  previous_period_cost_usd: number | null;  // null if no prior data
  successful_workflows: number;             // Not canceled or failed
  success_rate: number;                     // 0-1 (successful / total)
}
```

The frontend calculates the cost delta: `((current - previous) / previous) * 100`.

The aggregate success rate displays in the summary cards alongside total cost, workflows, tokens, and duration.

### Extended UsageByModel

Add per-model trend for sparklines:

```typescript
interface UsageByModel {
  model: string;
  workflows: number;
  successful_workflows: number;  // Not canceled or failed
  tokens: number;
  cost_usd: number;
  trend: number[];               // Daily costs array for sparkline
  success_rate: number;          // 0-1 (successful_workflows / workflows)
}
```

## Color Palette & Design System

### Reduced Gold Usage

Gold (`--primary`) reserved for hero elements only:

- Header total cost with glow effect
- Active date range button
- Summary row total cost value

### New CSS Variables

Add to `globals.css`:

```css
:root {
  /* Cost-specific (demoted from gold) */
  --cost-value: oklch(75% 0.08 90);        /* Warm cream for table costs */

  /* Multi-model chart palette (ordered by cost rank) */
  --chart-model-1: oklch(72% 0.14 195);    /* Teal - highest cost */
  --chart-model-2: oklch(68% 0.12 280);    /* Violet */
  --chart-model-3: oklch(70% 0.10 45);     /* Coral */
  --chart-model-4: oklch(65% 0.13 160);    /* Mint */
  --chart-model-5: oklch(60% 0.08 230);    /* Steel Blue */
  --chart-model-6: oklch(65% 0.10 330);    /* Dusty Rose */
}
```

### Color Mapping Logic

Models sorted by total cost descending. Highest-cost model gets `--chart-model-1` (teal), second gets `--chart-model-2` (violet), etc. If more than 6 models, colors cycle.

```typescript
function getModelColor(rankIndex: number): string {
  const colors = [
    'var(--chart-model-1)', 'var(--chart-model-2)',
    'var(--chart-model-3)', 'var(--chart-model-4)',
    'var(--chart-model-5)', 'var(--chart-model-6)',
  ];
  return colors[rankIndex % colors.length];
}
```

The same color mapping applies to chart lines, table model names, and sparklines.

## Multi-Model Chart Component

### Chart Toggle

A `ToggleGroup` above the chart switches between views:

```tsx
<ToggleGroup type="single" value={chartType} onValueChange={setChartType}>
  <ToggleGroupItem value="stacked">Stacked</ToggleGroupItem>
  <ToggleGroupItem value="line">Lines</ToggleGroupItem>
</ToggleGroup>
```

### Stacked Area View

Areas stack with `stackId="costs"`. Top edge represents total. Each model's area uses its assigned color with gradient fill (40% opacity at top, 5% at bottom).

```tsx
{models.map((model, i) => (
  <Area
    key={model}
    dataKey={model}
    stackId="costs"
    type="monotone"
    fill={`url(#gradient-${i})`}
    stroke={getModelColor(i)}
    strokeWidth={1.5}
  />
))}
```

### Line View

Independent lines, no stacking. Each line uses same color mapping. Includes `activeDot` for hover feedback.

```tsx
{models.map((model, i) => (
  <Line
    key={model}
    dataKey={model}
    type="monotone"
    stroke={getModelColor(i)}
    strokeWidth={2}
    dot={false}
    activeDot={{ r: 4 }}
  />
))}
```

### Enhanced Tooltip

Shows all models for hovered date, sorted by cost descending, with colored indicators and a total row at bottom.

### Legend

Inline `<ChartLegend>` below chart showing model names with color swatches.

## Responsive Components

### Mobile Date Range Dropdown

CSS-only responsive pattern using `hidden`/`md:hidden`:

```tsx
<PageHeader.Right>
  {/* Desktop: horizontal buttons */}
  <div className="hidden md:flex gap-1">
    {PRESETS.map(preset => (
      <button className={cn(
        'px-3 py-1.5 text-sm font-medium rounded-md',
        isActive ? 'bg-primary text-primary-foreground' : 'bg-muted'
      )}>
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
          <span>{currentLabel}</span>
          <ChevronDown className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={currentPreset} onValueChange={handleChange}>
          {PRESETS.map(p => <DropdownMenuRadioItem ... />)}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</PageHeader.Right>
```

### Responsive Table → Cards

On mobile (`<md`), the table converts to stacked cards:

```tsx
{/* Desktop: table */}
<table className="hidden md:table w-full">...</table>

{/* Mobile: cards */}
<div className="md:hidden space-y-3">
  {models.map(model => (
    <div className="bg-card rounded-lg p-4">
      <div className="flex justify-between items-center">
        <span className="font-medium" style={{ color: modelColor }}>
          {model.model}
        </span>
        <SuccessRateBadge rate={model.success_rate} />
      </div>
      <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
        <div>Workflows: {model.workflows}</div>
        <div>Tokens: {formatTokens(model.tokens)}</div>
        <div>Cost: {formatCost(model.cost_usd)}</div>
        <div>Share: {share}%</div>
      </div>
      <Sparkline data={model.trend} color={modelColor} className="mt-2" />
    </div>
  ))}
</div>
```

## Table Enhancements

### Sortable Columns with DataTable

Use `@tanstack/react-table` DataTable pattern from shadcn/ui for built-in sorting with proper accessibility:

```tsx
const columns: ColumnDef<UsageByModel>[] = [
  {
    accessorKey: 'model',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Model" />
    ),
    cell: ({ row }) => (
      <span style={{ color: getModelColor(row.index) }}>
        {row.getValue('model')}
      </span>
    ),
  },
  {
    accessorKey: 'success_rate',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Success" />
    ),
    cell: ({ row }) => (
      <SuccessRateBadge rate={row.getValue('success_rate')} />
    ),
  },
  {
    accessorKey: 'cost_usd',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Cost" />
    ),
    cell: ({ row }) => formatCost(row.getValue('cost_usd')),
  },
  // ... workflows, tokens, share columns
];

<DataTable columns={columns} data={sortedByModel} />
```

### Sparklines

Small inline chart (80×24px) showing model's daily cost trend:

```tsx
function Sparkline({ data, color }: { data: number[]; color: string }) {
  return (
    <svg viewBox={`0 0 ${data.length} 24`} className="w-20 h-6">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        points={data.map((v, i) => `${i},${24 - normalize(v)}`).join(' ')}
      />
    </svg>
  );
}
```

### Success Rate Column

The "Success" column shows goal completion rate per model with color-coded badges:

```tsx
function SuccessRateBadge({ rate }: { rate: number }) {
  const percentage = Math.round(rate * 100);
  const color =
    percentage >= 90 ? 'text-green-400' :
    percentage >= 70 ? 'text-yellow-400' :
    'text-red-400';

  return (
    <span className={cn('tabular-nums font-medium', color)}>
      {percentage}%
    </span>
  );
}
```

Color thresholds:
- **Green (≥90%)**: High reliability, model performing well
- **Yellow (70-89%)**: Moderate reliability, may need attention
- **Red (<70%)**: Low reliability, investigate failures

Success is defined as workflows that are not `canceled` or `failed`.

### CSV Export

Button in page header triggers download:

```typescript
function exportCSV(usage: UsageResponse, dateRange: string) {
  const rows = [
    ['Model', 'Workflows', 'Success Rate', 'Tokens', 'Cost (USD)', 'Share (%)'],
    ...usage.by_model.map(m => [
      m.model,
      m.workflows,
      `${Math.round(m.success_rate * 100)}%`,
      m.tokens,
      m.cost_usd,
      calcShare(m)
    ])
  ];
  const csv = rows.map(r => r.join(',')).join('\n');
  downloadBlob(csv, `costs-${dateRange}.csv`, 'text/csv');
}
```

## Loading & Empty States

Use shared components consistent with other dashboard views.

### Skeleton Loading

```tsx
function CostsPageSkeleton() {
  return (
    <>
      {/* Summary row skeletons (5 cards: cost, workflows, tokens, duration, success rate) */}
      <div className="grid grid-cols-5 gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-lg" />
        ))}
      </div>

      {/* Chart skeleton */}
      <Skeleton className="h-64 rounded-lg mt-6" />

      {/* Table skeleton */}
      <div className="mt-6 space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 rounded" />
        ))}
      </div>
    </>
  );
}
```

### Helpful Empty State

When `usage.summary.total_workflows === 0`:

```tsx
function EmptyState({ currentPreset, onPresetChange }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <BarChart3 className="size-12 text-muted-foreground mb-4" />
      <h3 className="text-lg font-medium">No usage data</h3>
      <p className="text-muted-foreground mt-1 max-w-sm">
        No workflows ran in the last {presetToLabel(currentPreset)}.
        Try a longer time range or start a new workflow.
      </p>
      {currentPreset !== 'all' && (
        <Button variant="outline" className="mt-4" onClick={() => onPresetChange('all')}>
          View all time
        </Button>
      )}
    </div>
  );
}
```

## Component Structure & Files

### New Files

| File | Purpose |
|------|---------|
| `utils/chart-colors.ts` | Model color mapping utilities |
| `components/Sparkline.tsx` | Reusable sparkline component |
| `components/DataTableColumnHeader.tsx` | Sortable column header (if not present) |
| `components/EmptyState.tsx` | Shared empty state (if not present) |
| `components/PageSkeleton.tsx` | Shared loading skeleton (if not present) |

### Modified Files

| File | Changes |
|------|---------|
| `styles/globals.css` | Add chart color CSS variables |
| `types/index.ts` | Extend `UsageTrendPoint`, `UsageSummary`, `UsageByModel` |
| `components/CostsTrendChart.tsx` | Multi-model stacked/line chart with toggle |
| `pages/CostsPage.tsx` | Responsive header, enhanced table, delta indicator, export button |

### Backend Changes

| File | Changes |
|------|---------|
| Usage endpoint handler | Include `by_model` in each trend point |
| Usage endpoint handler | Add `previous_period_cost_usd` to summary |
| Usage endpoint handler | Add `successful_workflows` and `success_rate` to summary |
| Usage endpoint handler | Add `trend`, `successful_workflows`, and `success_rate` to each `UsageByModel` |

## Implementation Phases

### Phase 1: Foundation (Frontend-only)

- Add chart color CSS variables to `globals.css`
- Create `utils/chart-colors.ts` with color mapping logic
- Implement responsive date range dropdown in `CostsPage.tsx`
- Audit and create shared `EmptyState` / `PageSkeleton` components if needed

### Phase 2: Backend API Changes

- Extend usage endpoint to include `by_model` breakdown in each `UsageTrendPoint`
- Add `previous_period_cost_usd` to `UsageSummary`
- Add `successful_workflows` and `success_rate` to `UsageSummary`
- Add `trend`, `successful_workflows`, and `success_rate` to each `UsageByModel`
- Update TypeScript types in `dashboard/src/types/index.ts`

### Phase 3: Multi-Model Chart

- Refactor `CostsTrendChart.tsx` to support multiple series
- Add chart type toggle (stacked/line) using `ToggleGroup`
- Implement enhanced tooltip with all models + total
- Add chart legend

### Phase 4: Table Enhancements

- Convert table to use `@tanstack/react-table` DataTable pattern
- Add sortable column headers
- Create `Sparkline` component
- Color model names using chart color mapping
- Add CSV export button and logic

### Phase 5: Polish & Mobile

- Implement responsive card layout for mobile table
- Add skeleton loading states
- Add helpful empty state
- Add period-over-period delta indicator to header
- Test across breakpoints

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Color mapping | By cost rank | Visual hierarchy reinforces importance |
| Chart type | Toggle between stacked/line | Flexibility for different analysis needs |
| Backend approach | Extend existing endpoint | Single API call, clean data model |
| Table sorting | `@tanstack/react-table` | Built-in sorting with accessibility |
| Loading/empty states | Shared components | Consistency across dashboard views |
| Mobile table | Card layout | Better touch targets, no horizontal scroll |
| Success definition | Not canceled or failed | Clear, measurable criteria |
| Success rate colors | Green/Yellow/Red thresholds | Intuitive traffic-light pattern |
