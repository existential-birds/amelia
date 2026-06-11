import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CostsTrendChart } from './CostsTrendChart';
import type { UsageTrendPoint } from '@/types';

const mockTrend: UsageTrendPoint[] = [
  { date: '2026-01-15', cost_usd: 12.34, workflows: 3 },
  { date: '2026-01-16', cost_usd: 15.67, workflows: 4 },
  { date: '2026-01-17', cost_usd: 8.90, workflows: 2 },
];

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

describe('CostsTrendChart', () => {
  it('should render chart container', () => {
    render(<CostsTrendChart data={mockTrend} />);

    expect(screen.getByRole('figure')).toBeInTheDocument();
  });

  it('should show empty state when no data', () => {
    render(<CostsTrendChart data={[]} />);

    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });

  it('should display chart with data-slot attribute', () => {
    const { container } = render(<CostsTrendChart data={mockTrend} />);

    expect(container.querySelector('[data-slot="costs-trend-chart"]')).toBeInTheDocument();
  });
});

describe('CostsTrendChart multi-model', () => {
  it('should render chart toggle buttons', () => {
    render(<CostsTrendChart data={mockTrendWithModels} />);

    // Radix UI ToggleGroup uses role="group" not "radiogroup"
    expect(screen.getByRole('group', { name: /chart type/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /stacked area chart/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /line chart/i })).toBeInTheDocument();
  });

  it('should default to stacked view', () => {
    render(<CostsTrendChart data={mockTrendWithModels} />);

    const stackedButton = screen.getByRole('radio', { name: /stacked area chart/i });
    expect(stackedButton).toHaveAttribute('data-state', 'on');
  });
});
