/**
 * @fileoverview Tests for CostsPage with enhanced table features.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import CostsPage from '../CostsPage';

vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
    useNavigate: () => vi.fn(),
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

import { useLoaderData } from 'react-router-dom';

const mockLoaderData = {
  usage: {
    summary: {
      total_cost_usd: 127.5,
      total_workflows: 24,
      total_tokens: 1200000,
      total_duration_ms: 2820000,
      previous_period_cost_usd: 100.0,
      successful_workflows: 20,
      success_rate: 0.833,
    },
    trend: [
      { date: '2026-01-15', cost_usd: 15.54, workflows: 3 },
      { date: '2026-01-16', cost_usd: 18.67, workflows: 4 },
    ],
    by_model: [
      {
        model: 'claude-sonnet-4',
        workflows: 18,
        tokens: 892000,
        cost_usd: 42.17,
      },
      {
        model: 'gpt-4o',
        workflows: 6,
        tokens: 308000,
        cost_usd: 85.33,
      },
    ],
  },
  currentPreset: '30d',
  currentStart: null,
  currentEnd: null,
};

describe('CostsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useLoaderData).mockReturnValue(mockLoaderData);
  });

  it('should render page header with title', () => {
    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    expect(screen.getByText('COSTS')).toBeInTheDocument();
    expect(screen.getByText('Usage & Spending')).toBeInTheDocument();
  });

  it('should render total cost in header', () => {
    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    // Format is $127.50 - appears multiple times on page
    const costElements = screen.getAllByText('$127.50');
    expect(costElements.length).toBeGreaterThan(0);
  });

  it('should render date range presets', () => {
    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    // Date range presets appear both in desktop buttons and mobile dropdown
    const sevenDaysButtons = screen.getAllByRole('button', { name: '7 days' });
    expect(sevenDaysButtons.length).toBeGreaterThan(0);
    const thirtyDaysButtons = screen.getAllByRole('button', { name: '30 days' });
    expect(thirtyDaysButtons.length).toBeGreaterThan(0);
  });

  it('should render model breakdown table', () => {
    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    // Model names should appear (may appear multiple times in table + mobile cards)
    const claudeElements = screen.getAllByText('claude-sonnet-4');
    expect(claudeElements.length).toBeGreaterThan(0);
    const gpt4oElements = screen.getAllByText('gpt-4o');
    expect(gpt4oElements.length).toBeGreaterThan(0);
  });
});

describe('CostsPage table enhancements', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useLoaderData).mockReturnValue(mockLoaderData);
  });

  it('should render sortable column headers', () => {
    // Note: DataTable is in hidden md:block container, but the DOM still contains it
    const { container } = render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    // The table is rendered but hidden on mobile via CSS class
    const modelButton = container.querySelector('button[type="button"]');
    expect(modelButton).toBeInTheDocument();

    const sortButtons = container.querySelectorAll('th button');
    expect(sortButtons.length).toBeGreaterThan(0);
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

    // Sparkline SVG should exist (in mobile card view which is visible)
    expect(container.querySelector('svg[role="img"]')).toBeInTheDocument();
  });

  it('should render success rate badges when data available', () => {
    const dataWithSuccess = {
      ...mockLoaderData,
      usage: {
        ...mockLoaderData.usage,
        summary: {
          ...mockLoaderData.usage.summary,
          success_rate: 0.833, // Keep the summary success rate for the row
        },
        by_model: [
          {
            model: 'claude-sonnet-4',
            workflows: 18,
            tokens: 892000,
            cost_usd: 42.17,
            success_rate: 0.95,
          },
        ],
      },
    };
    vi.mocked(useLoaderData).mockReturnValue(dataWithSuccess);

    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    // Success rate badge should show 95% (in mobile card view which is visible)
    const badges = screen.getAllByText(/\d+%/);
    expect(badges.some(b => b.textContent === '95%')).toBe(true);
  });

  it('should render export CSV button', () => {
    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    const exportButton = screen.getByRole('button', { name: /export csv/i });
    expect(exportButton).toBeInTheDocument();
  });

  it('should show period comparison delta when previous period data available', () => {
    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    // With current=127.5 and previous=100, delta should be +27.5%
    expect(screen.getByText(/\+27\.5% vs prev/)).toBeInTheDocument();
  });
});

describe('CostsPage empty state', () => {
  it('should show empty state when no workflows', () => {
    const emptyData = {
      ...mockLoaderData,
      usage: {
        summary: {
          total_cost_usd: 0,
          total_workflows: 0,
          total_tokens: 0,
          total_duration_ms: 0,
          previous_period_cost_usd: null,
          successful_workflows: null,
          success_rate: null,
        },
        trend: [],
        by_model: [],
      },
    };
    vi.mocked(useLoaderData).mockReturnValue(emptyData);

    render(
      <MemoryRouter>
        <CostsPage />
      </MemoryRouter>
    );

    expect(screen.getByText('No usage data')).toBeInTheDocument();
  });
});
