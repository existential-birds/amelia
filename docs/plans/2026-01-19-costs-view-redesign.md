# Costs View Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the dashboard costs view with multi-model chart visualization, improved table with sorting/sparklines, and responsive mobile support.

**Architecture:** Backend extends existing usage endpoint to add per-model breakdown in trend data, previous period comparison, and success rates. Frontend adds chart type toggle, sortable DataTable, sparklines, responsive date picker, and loading/empty states.

**Tech Stack:** Python/FastAPI/Pydantic (backend), React/TypeScript/Recharts/@tanstack/react-table/Tailwind (frontend)

---

## Phase 1: Foundation (Frontend CSS & Utilities)

### Task 1: Add Chart Color CSS Variables

**Files:**
- Modify: `dashboard/src/styles/globals.css`
- Test: Visual inspection

**Step 1: Add new CSS variables after the existing chart colors**

Add after line 157 (after `--chart-5`):

```css
  /* Multi-model chart palette (ordered by cost rank) */
  --chart-model-1: oklch(72% 0.14 195);    /* Teal - highest cost */
  --chart-model-2: oklch(68% 0.12 280);    /* Violet */
  --chart-model-3: oklch(70% 0.10 45);     /* Coral */
  --chart-model-4: oklch(65% 0.13 160);    /* Mint */
  --chart-model-5: oklch(60% 0.08 230);    /* Steel Blue */
  --chart-model-6: oklch(65% 0.10 330);    /* Dusty Rose */

  /* Cost-specific (demoted from gold for table values) */
  --cost-value: oklch(75% 0.08 90);        /* Warm cream */
```

**Step 2: Map the new variables to Tailwind utilities in @theme inline block**

Add after line 66 (after agent-bg colors):

```css
  /* Multi-model chart palette */
  --color-chart-model-1: var(--chart-model-1);
  --color-chart-model-2: var(--chart-model-2);
  --color-chart-model-3: var(--chart-model-3);
  --color-chart-model-4: var(--chart-model-4);
  --color-chart-model-5: var(--chart-model-5);
  --color-chart-model-6: var(--chart-model-6);
  --color-cost-value: var(--cost-value);
```

**Step 3: Verify no syntax errors**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 4: Commit**

```bash
git add dashboard/src/styles/globals.css
git commit -m "feat(costs): add multi-model chart color palette CSS variables"
```

---

### Task 2: Create Chart Colors Utility

**Files:**
- Create: `dashboard/src/utils/chart-colors.ts`
- Test: `dashboard/src/utils/__tests__/chart-colors.test.ts`

**Step 1: Write the failing test**

```typescript
import { describe, it, expect } from 'vitest';
import { getModelColor, MODEL_COLORS } from '../chart-colors';

describe('chart-colors', () => {
  describe('MODEL_COLORS', () => {
    it('should have 6 colors defined', () => {
      expect(MODEL_COLORS).toHaveLength(6);
    });

    it('should use CSS variables', () => {
      expect(MODEL_COLORS[0]).toBe('var(--chart-model-1)');
      expect(MODEL_COLORS[5]).toBe('var(--chart-model-6)');
    });
  });

  describe('getModelColor', () => {
    it('should return first color for rank 0', () => {
      expect(getModelColor(0)).toBe('var(--chart-model-1)');
    });

    it('should return second color for rank 1', () => {
      expect(getModelColor(1)).toBe('var(--chart-model-2)');
    });

    it('should cycle colors for rank >= 6', () => {
      expect(getModelColor(6)).toBe('var(--chart-model-1)');
      expect(getModelColor(7)).toBe('var(--chart-model-2)');
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/utils/__tests__/chart-colors.test.ts`
Expected: FAIL with "Cannot find module '../chart-colors'"

**Step 3: Write minimal implementation**

```typescript
/**
 * @fileoverview Chart color utilities for multi-model visualization.
 */

/**
 * Ordered color palette for multi-model charts.
 * Models are sorted by cost descending, highest cost gets first color.
 */
export const MODEL_COLORS = [
  'var(--chart-model-1)',
  'var(--chart-model-2)',
  'var(--chart-model-3)',
  'var(--chart-model-4)',
  'var(--chart-model-5)',
  'var(--chart-model-6)',
] as const;

/**
 * Get color for a model based on its cost rank.
 * Colors cycle if more than 6 models.
 *
 * @param rankIndex - Zero-based rank (0 = highest cost)
 * @returns CSS variable reference for the color
 */
export function getModelColor(rankIndex: number): string {
  return MODEL_COLORS[rankIndex % MODEL_COLORS.length];
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/utils/__tests__/chart-colors.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/utils/chart-colors.ts dashboard/src/utils/__tests__/chart-colors.test.ts
git commit -m "feat(costs): add chart color utility for multi-model visualization"
```

---

### Task 3: Create Sparkline Component

**Files:**
- Create: `dashboard/src/components/Sparkline.tsx`
- Test: `dashboard/src/components/__tests__/Sparkline.test.tsx`

**Step 1: Write the failing test**

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Sparkline } from '../Sparkline';

describe('Sparkline', () => {
  it('should render SVG element', () => {
    render(<Sparkline data={[1, 2, 3]} color="var(--chart-model-1)" />);

    const svg = screen.getByRole('img', { hidden: true });
    expect(svg).toBeInTheDocument();
    expect(svg.tagName).toBe('svg');
  });

  it('should render polyline with data points', () => {
    const { container } = render(
      <Sparkline data={[0, 12, 6]} color="var(--chart-model-1)" />
    );

    const polyline = container.querySelector('polyline');
    expect(polyline).toBeInTheDocument();
    expect(polyline).toHaveAttribute('stroke', 'var(--chart-model-1)');
  });

  it('should handle empty data gracefully', () => {
    const { container } = render(
      <Sparkline data={[]} color="var(--chart-model-1)" />
    );

    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('should handle single data point', () => {
    const { container } = render(
      <Sparkline data={[5]} color="var(--chart-model-1)" />
    );

    const polyline = container.querySelector('polyline');
    expect(polyline).toBeInTheDocument();
  });

  it('should apply custom className', () => {
    const { container } = render(
      <Sparkline data={[1, 2, 3]} color="var(--chart-model-1)" className="custom-class" />
    );

    expect(container.querySelector('svg')).toHaveClass('custom-class');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/__tests__/Sparkline.test.ts`
Expected: FAIL with "Cannot find module '../Sparkline'"

**Step 3: Write minimal implementation**

```typescript
/**
 * @fileoverview Sparkline component for inline trend visualization.
 */
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
 *
 * @param props - Component props
 * @returns SVG sparkline visualization
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
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/__tests__/Sparkline.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/Sparkline.tsx dashboard/src/components/__tests__/Sparkline.test.tsx
git commit -m "feat(costs): add Sparkline component for inline trend visualization"
```

---

### Task 4: Create SuccessRateBadge Component

**Files:**
- Create: `dashboard/src/components/SuccessRateBadge.tsx`
- Test: `dashboard/src/components/__tests__/SuccessRateBadge.test.tsx`

**Step 1: Write the failing test**

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SuccessRateBadge } from '../SuccessRateBadge';

describe('SuccessRateBadge', () => {
  it('should display percentage value', () => {
    render(<SuccessRateBadge rate={0.85} />);

    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('should round to nearest integer', () => {
    render(<SuccessRateBadge rate={0.856} />);

    expect(screen.getByText('86%')).toBeInTheDocument();
  });

  it('should apply green color for rate >= 90%', () => {
    render(<SuccessRateBadge rate={0.95} />);

    const badge = screen.getByText('95%');
    expect(badge).toHaveClass('text-green-400');
  });

  it('should apply yellow color for rate 70-89%', () => {
    render(<SuccessRateBadge rate={0.75} />);

    const badge = screen.getByText('75%');
    expect(badge).toHaveClass('text-yellow-400');
  });

  it('should apply red color for rate < 70%', () => {
    render(<SuccessRateBadge rate={0.5} />);

    const badge = screen.getByText('50%');
    expect(badge).toHaveClass('text-red-400');
  });

  it('should handle 0% rate', () => {
    render(<SuccessRateBadge rate={0} />);

    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('should handle 100% rate', () => {
    render(<SuccessRateBadge rate={1} />);

    expect(screen.getByText('100%')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/__tests__/SuccessRateBadge.test.ts`
Expected: FAIL with "Cannot find module '../SuccessRateBadge'"

**Step 3: Write minimal implementation**

```typescript
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
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/__tests__/SuccessRateBadge.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/SuccessRateBadge.tsx dashboard/src/components/__tests__/SuccessRateBadge.test.tsx
git commit -m "feat(costs): add SuccessRateBadge component with color thresholds"
```

---

### Task 5: Add Toggle Group UI Component

**Files:**
- Create: `dashboard/src/components/ui/toggle-group.tsx`

**Step 1: Install @radix-ui/react-toggle-group dependency**

Run: `cd dashboard && pnpm add @radix-ui/react-toggle-group`
Expected: Package added to package.json

**Step 2: Create toggle-group component following shadcn/ui pattern**

```typescript
import * as React from 'react';
import * as ToggleGroupPrimitive from '@radix-ui/react-toggle-group';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const toggleGroupVariants = cva(
  'inline-flex items-center justify-center rounded-md bg-muted p-1 text-muted-foreground',
  {
    variants: {
      variant: {
        default: 'bg-muted',
        outline: 'border border-input bg-transparent',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

const toggleGroupItemVariants = cva(
  'inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default:
          'data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-sm',
        outline:
          'border border-transparent data-[state=on]:border-input data-[state=on]:bg-background data-[state=on]:text-foreground',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

const ToggleGroupContext = React.createContext<
  VariantProps<typeof toggleGroupVariants>
>({
  variant: 'default',
});

function ToggleGroup({
  className,
  variant,
  children,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Root> &
  VariantProps<typeof toggleGroupVariants>) {
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      className={cn(toggleGroupVariants({ variant }), className)}
      {...props}
    >
      <ToggleGroupContext.Provider value={{ variant }}>
        {children}
      </ToggleGroupContext.Provider>
    </ToggleGroupPrimitive.Root>
  );
}

function ToggleGroupItem({
  className,
  children,
  variant,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Item> &
  VariantProps<typeof toggleGroupItemVariants>) {
  const context = React.useContext(ToggleGroupContext);

  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      className={cn(
        toggleGroupItemVariants({ variant: variant ?? context.variant }),
        className
      )}
      {...props}
    >
      {children}
    </ToggleGroupPrimitive.Item>
  );
}

export { ToggleGroup, ToggleGroupItem };
```

**Step 3: Verify no type errors**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 4: Commit**

```bash
git add dashboard/package.json dashboard/pnpm-lock.yaml dashboard/src/components/ui/toggle-group.tsx
git commit -m "feat(ui): add ToggleGroup component from shadcn/ui"
```

---

## Phase 2: Backend API Changes

### Task 6: Extend UsageTrendPoint Model

**Files:**
- Modify: `amelia/server/models/usage.py`
- Test: `tests/unit/server/models/test_usage.py`

**Step 1: Write the failing test**

```python
import pytest
from amelia.server.models.usage import UsageTrendPoint


def test_usage_trend_point_with_by_model():
    """UsageTrendPoint should include optional by_model breakdown."""
    point = UsageTrendPoint(
        date="2026-01-15",
        cost_usd=10.50,
        workflows=5,
        by_model={"claude-sonnet-4": 6.30, "gpt-4o": 4.20},
    )

    assert point.by_model == {"claude-sonnet-4": 6.30, "gpt-4o": 4.20}


def test_usage_trend_point_by_model_defaults_to_none():
    """UsageTrendPoint.by_model should default to None for backwards compat."""
    point = UsageTrendPoint(
        date="2026-01-15",
        cost_usd=10.50,
        workflows=5,
    )

    assert point.by_model is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_usage.py -v`
Expected: FAIL with "unexpected keyword argument 'by_model'"

**Step 3: Update UsageTrendPoint model**

```python
class UsageTrendPoint(BaseModel):
    """Single data point for the trend chart."""

    date: str  # ISO date YYYY-MM-DD
    cost_usd: float
    workflows: int
    by_model: dict[str, float] | None = None  # Per-model cost breakdown
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_usage.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/usage.py tests/unit/server/models/test_usage.py
git commit -m "feat(api): add by_model breakdown to UsageTrendPoint"
```

---

### Task 7: Extend UsageSummary Model

**Files:**
- Modify: `amelia/server/models/usage.py`
- Test: `tests/unit/server/models/test_usage.py`

**Step 1: Write the failing test**

```python
def test_usage_summary_with_comparison_and_success():
    """UsageSummary should include period comparison and success metrics."""
    summary = UsageSummary(
        total_cost_usd=127.50,
        total_workflows=24,
        total_tokens=1200000,
        total_duration_ms=2820000,
        previous_period_cost_usd=100.00,
        successful_workflows=20,
        success_rate=0.833,
    )

    assert summary.previous_period_cost_usd == 100.00
    assert summary.successful_workflows == 20
    assert summary.success_rate == 0.833


def test_usage_summary_new_fields_default_to_none():
    """New UsageSummary fields should default to None for backwards compat."""
    summary = UsageSummary(
        total_cost_usd=127.50,
        total_workflows=24,
        total_tokens=1200000,
        total_duration_ms=2820000,
    )

    assert summary.previous_period_cost_usd is None
    assert summary.successful_workflows is None
    assert summary.success_rate is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_usage.py::test_usage_summary_with_comparison_and_success -v`
Expected: FAIL with "unexpected keyword argument"

**Step 3: Update UsageSummary model**

```python
class UsageSummary(BaseModel):
    """Aggregated usage statistics for a time period."""

    total_cost_usd: float
    total_workflows: int
    total_tokens: int
    total_duration_ms: int
    cache_hit_rate: float | None = None
    cache_savings_usd: float | None = None
    previous_period_cost_usd: float | None = None  # For period-over-period comparison
    successful_workflows: int | None = None  # Workflows not cancelled or failed
    success_rate: float | None = None  # 0-1, successful_workflows / total_workflows
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_usage.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/usage.py tests/unit/server/models/test_usage.py
git commit -m "feat(api): add period comparison and success metrics to UsageSummary"
```

---

### Task 8: Extend UsageByModel Model

**Files:**
- Modify: `amelia/server/models/usage.py`
- Test: `tests/unit/server/models/test_usage.py`

**Step 1: Write the failing test**

```python
def test_usage_by_model_with_trend_and_success():
    """UsageByModel should include trend data and success metrics."""
    model_usage = UsageByModel(
        model="claude-sonnet-4",
        workflows=18,
        tokens=892000,
        cost_usd=42.17,
        trend=[10.5, 12.3, 8.7, 10.67],
        successful_workflows=16,
        success_rate=0.889,
    )

    assert model_usage.trend == [10.5, 12.3, 8.7, 10.67]
    assert model_usage.successful_workflows == 16
    assert model_usage.success_rate == 0.889


def test_usage_by_model_new_fields_default_to_none():
    """New UsageByModel fields should default to None for backwards compat."""
    model_usage = UsageByModel(
        model="claude-sonnet-4",
        workflows=18,
        tokens=892000,
        cost_usd=42.17,
    )

    assert model_usage.trend is None
    assert model_usage.successful_workflows is None
    assert model_usage.success_rate is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_usage.py::test_usage_by_model_with_trend_and_success -v`
Expected: FAIL with "unexpected keyword argument"

**Step 3: Update UsageByModel model**

```python
class UsageByModel(BaseModel):
    """Usage breakdown for a single model."""

    model: str
    workflows: int
    tokens: int
    cost_usd: float
    cache_hit_rate: float | None = None
    cache_savings_usd: float | None = None
    trend: list[float] | None = None  # Daily costs array for sparkline
    successful_workflows: int | None = None  # Workflows not cancelled or failed
    success_rate: float | None = None  # 0-1, successful_workflows / workflows
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_usage.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/usage.py tests/unit/server/models/test_usage.py
git commit -m "feat(api): add trend and success metrics to UsageByModel"
```

---

### Task 9: Update Repository get_usage_trend Method

**Files:**
- Modify: `amelia/server/database/repository.py`
- Test: `tests/unit/server/database/test_repository_usage.py`

**Step 1: Write the failing test**

```python
import pytest
from datetime import date
from amelia.server.database.repository import WorkflowRepository


@pytest.mark.asyncio
async def test_get_usage_trend_includes_by_model(db_with_token_usage):
    """get_usage_trend should include per-model breakdown."""
    repo = WorkflowRepository(db_with_token_usage)

    trend = await repo.get_usage_trend(
        start_date=date(2026, 1, 15),
        end_date=date(2026, 1, 17),
    )

    # Check that by_model is included
    for point in trend:
        assert "by_model" in point
        assert isinstance(point["by_model"], dict)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_repository_usage.py::test_get_usage_trend_includes_by_model -v`
Expected: FAIL with KeyError: 'by_model'

**Step 3: Update get_usage_trend method**

```python
async def get_usage_trend(
    self,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Get daily usage trend for a date range.

    Args:
        start_date: Start of date range (inclusive).
        end_date: End of date range (inclusive).

    Returns:
        List of dicts with date, cost_usd, workflows, by_model.
    """
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    # Get daily totals
    rows = await self._db.fetch_all(
        """
        SELECT
            DATE(t.timestamp) as date,
            SUM(t.cost_usd) as cost_usd,
            COUNT(DISTINCT t.workflow_id) as workflows
        FROM token_usage t
        WHERE DATE(t.timestamp) >= ? AND DATE(t.timestamp) <= ?
        GROUP BY DATE(t.timestamp)
        ORDER BY date
        """,
        (start_str, end_str),
    )

    # Get per-model breakdown for each day
    model_rows = await self._db.fetch_all(
        """
        SELECT
            DATE(t.timestamp) as date,
            t.model,
            SUM(t.cost_usd) as cost_usd
        FROM token_usage t
        WHERE DATE(t.timestamp) >= ? AND DATE(t.timestamp) <= ?
        GROUP BY DATE(t.timestamp), t.model
        ORDER BY date, cost_usd DESC
        """,
        (start_str, end_str),
    )

    # Build model breakdown lookup by date
    by_model_lookup: dict[str, dict[str, float]] = {}
    for row in model_rows:
        day = row[0]
        if day not in by_model_lookup:
            by_model_lookup[day] = {}
        by_model_lookup[day][row[1]] = row[2]

    return [
        {
            "date": row[0],
            "cost_usd": row[1],
            "workflows": row[2],
            "by_model": by_model_lookup.get(row[0], {}),
        }
        for row in rows
    ]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_repository_usage.py::test_get_usage_trend_includes_by_model -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/repository.py tests/unit/server/database/test_repository_usage.py
git commit -m "feat(api): include per-model breakdown in usage trend data"
```

---

### Task 10: Update Repository get_usage_summary Method

**Files:**
- Modify: `amelia/server/database/repository.py`
- Test: `tests/unit/server/database/test_repository_usage.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_get_usage_summary_includes_success_metrics(db_with_workflows_and_usage):
    """get_usage_summary should include success rate and previous period cost."""
    repo = WorkflowRepository(db_with_workflows_and_usage)

    summary = await repo.get_usage_summary(
        start_date=date(2026, 1, 15),
        end_date=date(2026, 1, 21),
    )

    assert "previous_period_cost_usd" in summary
    assert "successful_workflows" in summary
    assert "success_rate" in summary
    assert isinstance(summary["success_rate"], (int, float))
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_repository_usage.py::test_get_usage_summary_includes_success_metrics -v`
Expected: FAIL with KeyError

**Step 3: Update get_usage_summary method**

```python
async def get_usage_summary(
    self,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Get aggregated usage summary for a date range.

    Args:
        start_date: Start of date range (inclusive).
        end_date: End of date range (inclusive).

    Returns:
        Dict with usage metrics including success rate and previous period comparison.
    """
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    # Calculate previous period dates (same duration, immediately before)
    period_days = (end_date - start_date).days + 1
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_days - 1)

    # Get current period metrics
    row = await self._db.fetch_one(
        """
        SELECT
            COALESCE(SUM(t.cost_usd), 0) as total_cost_usd,
            COUNT(DISTINCT t.workflow_id) as total_workflows,
            COALESCE(SUM(t.input_tokens + t.output_tokens), 0) as total_tokens,
            COALESCE(SUM(t.duration_ms), 0) as total_duration_ms
        FROM token_usage t
        WHERE DATE(t.timestamp) >= ? AND DATE(t.timestamp) <= ?
        """,
        (start_str, end_str),
    )

    # Get previous period cost for comparison
    prev_row = await self._db.fetch_one(
        """
        SELECT COALESCE(SUM(t.cost_usd), 0) as cost_usd
        FROM token_usage t
        WHERE DATE(t.timestamp) >= ? AND DATE(t.timestamp) <= ?
        """,
        (prev_start.isoformat(), prev_end.isoformat()),
    )
    previous_period_cost = prev_row[0] if prev_row and prev_row[0] > 0 else None

    # Get success metrics from workflows table
    # Success = completed (not cancelled, failed, pending, planning, in_progress, blocked)
    success_row = await self._db.fetch_one(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful
        FROM workflows w
        WHERE EXISTS (
            SELECT 1 FROM token_usage t
            WHERE t.workflow_id = w.id
            AND DATE(t.timestamp) >= ? AND DATE(t.timestamp) <= ?
        )
        """,
        (start_str, end_str),
    )

    total_workflows_with_status = success_row[0] if success_row else 0
    successful_workflows = success_row[1] if success_row else 0
    success_rate = (
        successful_workflows / total_workflows_with_status
        if total_workflows_with_status > 0
        else None
    )

    return {
        "total_cost_usd": row[0] if row else 0.0,
        "total_workflows": row[1] if row else 0,
        "total_tokens": row[2] if row else 0,
        "total_duration_ms": row[3] if row else 0,
        "previous_period_cost_usd": previous_period_cost,
        "successful_workflows": successful_workflows if total_workflows_with_status > 0 else None,
        "success_rate": success_rate,
    }
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_repository_usage.py::test_get_usage_summary_includes_success_metrics -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/repository.py tests/unit/server/database/test_repository_usage.py
git commit -m "feat(api): add success metrics and period comparison to usage summary"
```

---

### Task 11: Update Repository get_usage_by_model Method

**Files:**
- Modify: `amelia/server/database/repository.py`
- Test: `tests/unit/server/database/test_repository_usage.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_get_usage_by_model_includes_trend_and_success(db_with_workflows_and_usage):
    """get_usage_by_model should include trend array and success metrics."""
    repo = WorkflowRepository(db_with_workflows_and_usage)

    by_model = await repo.get_usage_by_model(
        start_date=date(2026, 1, 15),
        end_date=date(2026, 1, 21),
    )

    for model_data in by_model:
        assert "trend" in model_data
        assert isinstance(model_data["trend"], list)
        assert "successful_workflows" in model_data
        assert "success_rate" in model_data
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_repository_usage.py::test_get_usage_by_model_includes_trend_and_success -v`
Expected: FAIL with KeyError

**Step 3: Update get_usage_by_model method**

```python
async def get_usage_by_model(
    self,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Get usage breakdown by model for a date range.

    Args:
        start_date: Start of date range (inclusive).
        end_date: End of date range (inclusive).

    Returns:
        List of dicts with model, workflows, tokens, cost_usd, trend, success metrics.
    """
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    # Get aggregated stats per model
    rows = await self._db.fetch_all(
        """
        SELECT
            t.model,
            COUNT(DISTINCT t.workflow_id) as workflows,
            SUM(t.input_tokens + t.output_tokens) as tokens,
            SUM(t.cost_usd) as cost_usd
        FROM token_usage t
        WHERE DATE(t.timestamp) >= ? AND DATE(t.timestamp) <= ?
        GROUP BY t.model
        ORDER BY cost_usd DESC
        """,
        (start_str, end_str),
    )

    # Get daily trend per model for sparklines
    trend_rows = await self._db.fetch_all(
        """
        SELECT
            t.model,
            DATE(t.timestamp) as date,
            SUM(t.cost_usd) as cost_usd
        FROM token_usage t
        WHERE DATE(t.timestamp) >= ? AND DATE(t.timestamp) <= ?
        GROUP BY t.model, DATE(t.timestamp)
        ORDER BY t.model, date
        """,
        (start_str, end_str),
    )

    # Build trend lookup
    trend_lookup: dict[str, list[float]] = {}
    for row in trend_rows:
        model = row[0]
        if model not in trend_lookup:
            trend_lookup[model] = []
        trend_lookup[model].append(row[2])

    # Get success metrics per model
    success_rows = await self._db.fetch_all(
        """
        SELECT
            t.model,
            COUNT(DISTINCT t.workflow_id) as total,
            COUNT(DISTINCT CASE WHEN w.status = 'completed' THEN t.workflow_id END) as successful
        FROM token_usage t
        JOIN workflows w ON t.workflow_id = w.id
        WHERE DATE(t.timestamp) >= ? AND DATE(t.timestamp) <= ?
        GROUP BY t.model
        """,
        (start_str, end_str),
    )

    # Build success lookup
    success_lookup: dict[str, tuple[int, int]] = {}
    for row in success_rows:
        success_lookup[row[0]] = (row[1], row[2])

    return [
        {
            "model": row[0],
            "workflows": row[1],
            "tokens": row[2],
            "cost_usd": row[3],
            "trend": trend_lookup.get(row[0], []),
            "successful_workflows": success_lookup.get(row[0], (0, 0))[1],
            "success_rate": (
                success_lookup[row[0]][1] / success_lookup[row[0]][0]
                if row[0] in success_lookup and success_lookup[row[0]][0] > 0
                else 0.0
            ),
        }
        for row in rows
    ]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_repository_usage.py::test_get_usage_by_model_includes_trend_and_success -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/repository.py tests/unit/server/database/test_repository_usage.py
git commit -m "feat(api): add trend and success metrics to usage by model"
```

---

### Task 12: Update Frontend TypeScript Types

**Files:**
- Modify: `dashboard/src/types/index.ts`

**Step 1: Update UsageTrendPoint interface**

Find and replace the `UsageTrendPoint` interface:

```typescript
/**
 * Daily trend data point.
 */
export interface UsageTrendPoint {
  /** ISO date string (YYYY-MM-DD). */
  date: string;
  /** Cost in USD for this date. */
  cost_usd: number;
  /** Number of workflows on this date. */
  workflows: number;
  /** Per-model cost breakdown (model name -> cost in USD). */
  by_model?: Record<string, number>;
}
```

**Step 2: Update UsageSummary interface**

Find and replace the `UsageSummary` interface:

```typescript
/**
 * Summary statistics for the usage endpoint.
 */
export interface UsageSummary {
  /** Total cost in USD for the period. */
  total_cost_usd: number;
  /** Total number of workflows in the period. */
  total_workflows: number;
  /** Total tokens (input + output) in the period. */
  total_tokens: number;
  /** Total duration in milliseconds. */
  total_duration_ms: number;
  /** Cache hit rate (0-1), optional for efficiency metrics. */
  cache_hit_rate?: number;
  /** Savings from caching in USD, optional for efficiency metrics. */
  cache_savings_usd?: number;
  /** Cost from previous period for comparison, null if no prior data. */
  previous_period_cost_usd?: number | null;
  /** Number of workflows that completed successfully. */
  successful_workflows?: number | null;
  /** Success rate (0-1), successful_workflows / total_workflows. */
  success_rate?: number | null;
}
```

**Step 3: Update UsageByModel interface**

Find and replace the `UsageByModel` interface:

```typescript
/**
 * Usage breakdown by model.
 */
export interface UsageByModel {
  /** Model name (e.g., "claude-sonnet-4"). */
  model: string;
  /** Number of workflows using this model. */
  workflows: number;
  /** Total tokens for this model. */
  tokens: number;
  /** Total cost in USD for this model. */
  cost_usd: number;
  /** Cache hit rate (0-1), optional for efficiency metrics. */
  cache_hit_rate?: number;
  /** Savings from caching in USD, optional for efficiency metrics. */
  cache_savings_usd?: number;
  /** Daily cost array for sparkline visualization. */
  trend?: number[];
  /** Number of workflows that completed successfully. */
  successful_workflows?: number;
  /** Success rate (0-1), successful_workflows / workflows. */
  success_rate?: number;
}
```

**Step 4: Verify no type errors**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 5: Commit**

```bash
git add dashboard/src/types/index.ts
git commit -m "feat(types): extend usage types with trend breakdown and success metrics"
```

---

## Phase 3: Multi-Model Chart

### Task 13: Refactor CostsTrendChart for Multi-Model Support

**Files:**
- Modify: `dashboard/src/components/CostsTrendChart.tsx`
- Modify: `dashboard/src/components/CostsTrendChart.test.tsx`

**Step 1: Write tests for the new functionality**

Add to existing test file:

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CostsTrendChart } from './CostsTrendChart';
import type { UsageTrendPoint } from '@/types';

const mockTrendWithModels: UsageTrendPoint[] = [
  {
    date: '2026-01-15',
    cost_usd: 15.54,
    workflows: 3,
    by_model: { 'claude-sonnet-4': 10.34, 'gpt-4o': 5.20 },
  },
  {
    date: '2026-01-16',
    cost_usd: 18.67,
    workflows: 4,
    by_model: { 'claude-sonnet-4': 12.47, 'gpt-4o': 6.20 },
  },
];

describe('CostsTrendChart multi-model', () => {
  it('should render chart toggle buttons', () => {
    render(<CostsTrendChart data={mockTrendWithModels} />);

    expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /stacked/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /lines/i })).toBeInTheDocument();
  });

  it('should default to stacked view', () => {
    render(<CostsTrendChart data={mockTrendWithModels} />);

    const stackedButton = screen.getByRole('radio', { name: /stacked/i });
    expect(stackedButton).toHaveAttribute('data-state', 'on');
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm test src/components/CostsTrendChart.test.tsx`
Expected: FAIL (no toggle buttons yet)

**Step 3: Implement multi-model chart with toggle**

Replace entire `CostsTrendChart.tsx`:

```typescript
/**
 * @fileoverview Trend chart component for costs visualization.
 * Supports multi-model breakdown with stacked area and line views.
 */
import { useState, useMemo } from 'react';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Area, AreaChart, Line, LineChart, XAxis, YAxis } from 'recharts';
import { formatCost } from '@/utils/workflow';
import { getModelColor, MODEL_COLORS } from '@/utils/chart-colors';
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
            <ChartLegend content={<ChartLegendContent />} />
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
            <ChartLegend content={<ChartLegendContent />} />
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
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test src/components/CostsTrendChart.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/CostsTrendChart.tsx dashboard/src/components/CostsTrendChart.test.tsx
git commit -m "feat(costs): add multi-model chart with stacked/line toggle"
```

---

## Phase 4: Table Enhancements

### Task 14: Install @tanstack/react-table

**Files:**
- Modify: `dashboard/package.json`

**Step 1: Install dependency**

Run: `cd dashboard && pnpm add @tanstack/react-table`
Expected: Package added

**Step 2: Commit**

```bash
git add dashboard/package.json dashboard/pnpm-lock.yaml
git commit -m "chore(deps): add @tanstack/react-table for sortable tables"
```

---

### Task 15: Create DataTable Component

**Files:**
- Create: `dashboard/src/components/ui/data-table.tsx`

**Step 1: Create the DataTable component following shadcn/ui pattern**

```typescript
/**
 * @fileoverview Generic data table component with sorting support.
 */
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { useState } from 'react';
import { cn } from '@/lib/utils';

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  onRowClick?: (row: TData) => void;
}

export function DataTable<TData, TValue>({
  columns,
  data,
  onRowClick,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: {
      sorting,
    },
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-border">
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  scope="col"
                  className={cn(
                    'py-2 px-3 text-muted-foreground font-medium',
                    header.column.getCanSort() && 'cursor-pointer select-none'
                  )}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              onClick={() => onRowClick?.(row.original)}
              onKeyDown={(e) => {
                if ((e.key === 'Enter' || e.key === ' ') && onRowClick) {
                  e.preventDefault();
                  onRowClick(row.original);
                }
              }}
              role={onRowClick ? 'button' : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              className={cn(
                'border-b border-border/50 last:border-0',
                onRowClick && 'cursor-pointer hover:bg-muted/50 transition-colors'
              )}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="py-2 px-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

**Step 2: Verify no type errors**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add dashboard/src/components/ui/data-table.tsx
git commit -m "feat(ui): add DataTable component with sorting support"
```

---

### Task 16: Create DataTableColumnHeader Component

**Files:**
- Create: `dashboard/src/components/ui/data-table-column-header.tsx`

**Step 1: Create sortable column header component**

```typescript
/**
 * @fileoverview Sortable column header for DataTable.
 */
import type { Column } from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DataTableColumnHeaderProps<TData, TValue> {
  column: Column<TData, TValue>;
  title: string;
  className?: string;
  align?: 'left' | 'right' | 'center';
}

export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
  align = 'left',
}: DataTableColumnHeaderProps<TData, TValue>) {
  if (!column.getCanSort()) {
    return (
      <div className={cn('flex items-center', align === 'right' && 'justify-end', className)}>
        {title}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={cn(
        'flex items-center gap-1 hover:text-foreground transition-colors',
        align === 'right' && 'ml-auto',
        className
      )}
      onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
    >
      {title}
      {column.getIsSorted() === 'asc' ? (
        <ArrowUp className="size-3.5" />
      ) : column.getIsSorted() === 'desc' ? (
        <ArrowDown className="size-3.5" />
      ) : (
        <ArrowUpDown className="size-3.5 opacity-50" />
      )}
    </button>
  );
}
```

**Step 2: Verify no type errors**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add dashboard/src/components/ui/data-table-column-header.tsx
git commit -m "feat(ui): add DataTableColumnHeader with sort indicators"
```

---

### Task 17: Update CostsPage with Enhanced Table

**Files:**
- Modify: `dashboard/src/pages/CostsPage.tsx`
- Modify: `dashboard/src/pages/CostsPage.test.tsx`

**Step 1: Add tests for new table features**

Add to existing test file:

```typescript
describe('CostsPage table enhancements', () => {
  it('should render sortable column headers', () => {
    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    // Column headers should exist
    expect(screen.getByRole('button', { name: /model/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cost/i })).toBeInTheDocument();
  });

  it('should render sparklines when trend data available', () => {
    const dataWithTrend = {
      ...mockLoaderData,
      usage: {
        ...mockLoaderData.usage,
        by_model: [
          {
            model: 'claude-sonnet-4',
            workflows: 18,
            tokens: 892000,
            cost_usd: 42.17,
            trend: [10, 12, 8, 12],
            success_rate: 0.89,
          },
        ],
      },
    };
    vi.mocked(useLoaderData).mockReturnValue(dataWithTrend);

    const { container } = render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    // Sparkline SVG should exist
    expect(container.querySelector('svg[role="img"]')).toBeInTheDocument();
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm test src/pages/CostsPage.test.tsx`
Expected: FAIL (no sortable headers yet)

**Step 3: Update CostsPage with enhanced table**

Replace entire `CostsPage.tsx`:

```typescript
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
import { Skeleton } from '@/components/ui/skeleton';
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
 * Export usage data to CSV.
 */
function exportCSV(byModel: UsageByModel[], dateRange: string) {
  const rows = [
    ['Model', 'Workflows', 'Success Rate', 'Tokens', 'Cost (USD)'],
    ...byModel.map((m) => [
      m.model,
      m.workflows,
      m.success_rate !== undefined ? `${Math.round(m.success_rate * 100)}%` : 'N/A',
      m.tokens,
      m.cost_usd.toFixed(2),
    ]),
  ];
  const csv = rows.map((r) => r.join(',')).join('\n');
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
          const rate = row.getValue('success_rate') as number | undefined;
          return rate !== undefined ? (
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
                color={modelColorMap[row.original.model]}
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
            <PageHeader.Value glow>$0.00</PageHeader.Value>
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
                    <span>{PRESETS.find((p) => p.value === currentPreset)?.label}</span>
                    <ChevronDown className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuRadioGroup value={currentPreset ?? '30d'} onValueChange={handlePresetChange}>
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
                No workflows ran in the last{' '}
                {PRESETS.find((p) => p.value === currentPreset)?.label ?? '30 days'}.
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
            <PageHeader.Value glow>{formatCost(usage.summary.total_cost_usd)}</PageHeader.Value>
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
                  <span>{PRESETS.find((p) => p.value === currentPreset)?.label}</span>
                  <ChevronDown className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuRadioGroup value={currentPreset ?? '30d'} onValueChange={handlePresetChange}>
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
          {usage.summary.success_rate !== null && usage.summary.success_rate !== undefined && (
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
              onClick={() => exportCSV(usage.by_model, currentPreset ?? '30d')}
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
                    {model.success_rate !== undefined && (
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
                      color={modelColorMap[model.model]}
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
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test src/pages/CostsPage.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/pages/CostsPage.tsx dashboard/src/pages/CostsPage.test.tsx
git commit -m "feat(costs): add sortable table, sparklines, mobile cards, CSV export"
```

---

## Phase 5: Final Integration & Testing

### Task 18: Run Full Test Suite

**Step 1: Run backend tests**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 2: Run frontend tests**

Run: `cd dashboard && pnpm test:run`
Expected: All tests pass

**Step 3: Run type checks**

Run: `uv run mypy amelia && cd dashboard && pnpm type-check`
Expected: No errors

**Step 4: Run linting**

Run: `uv run ruff check amelia tests && cd dashboard && pnpm lint`
Expected: No errors

**Step 5: Commit any fixes needed**

If any tests fail, fix and commit.

---

### Task 19: Manual Visual Verification

**Step 1: Start the development server**

Run: `uv run amelia dev`
Expected: Server starts on localhost:8420

**Step 2: Navigate to costs page and verify**

- [ ] Page loads without errors
- [ ] Date range buttons work (desktop)
- [ ] Date range dropdown works (mobile, resize window)
- [ ] Chart toggle switches between stacked and line views
- [ ] Multi-model colors are consistent between chart and table
- [ ] Table sorting works on all columns
- [ ] Sparklines render in table
- [ ] Success rate badges show correct colors
- [ ] CSV export downloads file
- [ ] Empty state shows when no data
- [ ] Mobile card view displays correctly

**Step 3: Document any issues found**

If issues found, create follow-up tasks.

---

### Task 20: Final Commit

**Step 1: Stage all changes**

Run: `git status`
Verify all changes are staged.

**Step 2: Create final commit if needed**

If there are uncommitted changes:

```bash
git add -A
git commit -m "chore(costs): final cleanup and polish"
```

**Step 3: Push branch**

Run: `git push -u origin feat/costs-view`
Expected: Branch pushed successfully

---

## Summary

This plan implements the costs view redesign in 5 phases:

1. **Foundation**: CSS variables, chart colors utility, Sparkline, SuccessRateBadge, ToggleGroup
2. **Backend API**: Extended models and repository methods for by_model, previous_period, success metrics
3. **Multi-Model Chart**: Refactored CostsTrendChart with stacked/line toggle
4. **Table Enhancements**: DataTable, sortable columns, sparklines, CSV export, mobile cards
5. **Integration**: Full test suite, manual verification, final commit

Each task follows TDD with specific file paths, exact code, and commit messages.
