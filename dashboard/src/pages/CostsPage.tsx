/**
 * @fileoverview Costs page for usage monitoring and analysis.
 */
import { useLoaderData, useNavigate, useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { CostsTrendChart } from '@/components/CostsTrendChart';
import { formatTokens, formatCost, formatDuration } from '@/utils/workflow';
import { cn } from '@/lib/utils';
import type { costsLoader } from '@/loaders/costs';

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
 * Costs page displaying usage metrics, trends, and model breakdown.
 *
 * @returns The costs page UI
 */
export default function CostsPage() {
  const { usage, currentPreset } = useLoaderData<typeof costsLoader>();
  const [_searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const handlePresetChange = (preset: string) => {
    setSearchParams({ preset });
  };

  const handleModelClick = (model: string) => {
    navigate(`/history?model=${encodeURIComponent(model)}`);
  };

  return (
    <div className="flex flex-col w-full">
      {/* Header */}
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>COSTS</PageHeader.Label>
          <PageHeader.Title>Usage & Spending</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Center>
          <PageHeader.Value glow>
            {formatCost(usage.summary.total_cost_usd)}
          </PageHeader.Value>
        </PageHeader.Center>
        <PageHeader.Right>
          {/* Date range selector */}
          <div className="flex gap-1">
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
        </PageHeader.Right>
      </PageHeader>

      <div className="flex flex-col gap-6 p-6">
        {/* Summary row */}
        <div className="flex items-center gap-2 text-sm flex-wrap">
          <span className="text-primary font-semibold">
            {formatCost(usage.summary.total_cost_usd)}
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-foreground">{usage.summary.total_workflows}</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-foreground">
            {formatTokens(usage.summary.total_tokens)} tokens
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-foreground">
            {formatDuration(usage.summary.total_duration_ms)}
          </span>
        </div>

        {/* Trend chart */}
        <div className="border border-border rounded-lg p-4 bg-card/50">
          <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-4">
            DAILY COSTS
          </h3>
          <CostsTrendChart data={usage.trend} />
        </div>

        {/* Model breakdown table */}
        <div className="border border-border rounded-lg p-4 bg-card/50">
          <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-4">
            BY MODEL
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="text-left py-2 pr-4 text-muted-foreground font-medium">
                    Model
                  </th>
                  <th scope="col" className="text-right py-2 px-3 text-muted-foreground font-medium">
                    Workflows
                  </th>
                  <th scope="col" className="text-right py-2 px-3 text-muted-foreground font-medium">
                    Tokens
                  </th>
                  <th scope="col" className="text-right py-2 px-3 text-muted-foreground font-medium">
                    Cost
                  </th>
                  <th scope="col" className="text-right py-2 pl-3 text-muted-foreground font-medium">
                    Share
                  </th>
                </tr>
              </thead>
              <tbody>
                {usage.by_model.map((model) => {
                  const share = usage.summary.total_cost_usd > 0
                    ? (model.cost_usd / usage.summary.total_cost_usd) * 100
                    : 0;
                  return (
                    <tr
                      key={model.model}
                      onClick={() => handleModelClick(model.model)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleModelClick(model.model);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      aria-label={`View history for ${model.model}`}
                      className={cn(
                        'border-b border-border/50 last:border-0 cursor-pointer',
                        'hover:bg-muted/50 transition-colors'
                      )}
                    >
                      <td className="py-2 pr-4 text-foreground font-medium">
                        {model.model}
                      </td>
                      <td className="py-2 px-3 text-right text-muted-foreground tabular-nums">
                        {model.workflows}
                      </td>
                      <td className="py-2 px-3 text-right text-muted-foreground tabular-nums">
                        {formatTokens(model.tokens)}
                      </td>
                      <td className="py-2 px-3 text-right text-primary tabular-nums">
                        {formatCost(model.cost_usd)}
                      </td>
                      <td className="py-2 pl-3 text-right text-muted-foreground tabular-nums">
                        {share.toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
