/**
 * @fileoverview Token usage card component for workflow detail page.
 */
import { cn } from '@/lib/utils';
import { AGENT_STYLES } from '@/lib/constants';
import { formatTokens, formatCost, formatDuration } from '@/utils/workflow';
import type { TokenSummary } from '@/types';

/**
 * Props for the UsageCard component.
 */
interface UsageCardProps {
  /** Token usage summary with breakdown by agent. Null/undefined hides the card. */
  tokenUsage: TokenSummary | null | undefined;
  /** Optional className for the card container. */
  className?: string;
}

/**
 * Displays token usage statistics for a workflow.
 *
 * Shows a summary line with totals and a table breakdown by agent.
 * Returns null if no token usage data is available.
 *
 * @param props - Component props
 * @returns The usage card UI or null if no data
 */
export function UsageCard({ tokenUsage, className }: UsageCardProps) {
  // Don't render if no token usage data
  if (!tokenUsage) {
    return null;
  }

  const totalTokens = tokenUsage.total_input_tokens + tokenUsage.total_output_tokens;

  return (
    <div
      data-slot="usage-card"
      className={cn('p-4 border border-border rounded-lg bg-card/50', className)}
    >
      <h3 className="font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-3">
        USAGE
      </h3>

      {/* Summary line */}
      <div className="flex items-center gap-2 text-sm mb-4 flex-wrap">
        <span className="text-primary font-semibold">{formatCost(tokenUsage.total_cost_usd)}</span>
        <span className="text-muted-foreground">|</span>
        <span className="text-accent">{formatTokens(totalTokens)} tokens</span>
        <span className="text-muted-foreground">|</span>
        <span className="text-muted-foreground">{formatDuration(tokenUsage.total_duration_ms)}</span>
        <span className="text-muted-foreground">|</span>
        <span className="text-muted-foreground">{tokenUsage.total_turns} turns</span>
      </div>

      {/* Agent breakdown table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[500px]">
          <thead>
            <tr className="border-b border-border">
              <th
                scope="col"
                className="text-left py-2 pr-4 text-muted-foreground font-medium"
              >
                Agent
              </th>
              <th
                scope="col"
                className="text-left py-2 px-3 text-muted-foreground font-medium"
              >
                Model
              </th>
              <th
                scope="col"
                className="text-right py-2 px-3 text-muted-foreground font-medium"
              >
                Input
              </th>
              <th
                scope="col"
                className="text-right py-2 px-3 text-muted-foreground font-medium"
              >
                Output
              </th>
              <th
                scope="col"
                className="text-right py-2 px-3 text-muted-foreground font-medium"
              >
                Cache
              </th>
              <th
                scope="col"
                className="text-right py-2 px-3 text-muted-foreground font-medium"
              >
                Cost
              </th>
              <th
                scope="col"
                className="text-right py-2 pl-3 text-muted-foreground font-medium"
              >
                Time
              </th>
            </tr>
          </thead>
          <tbody>
            {tokenUsage.breakdown.map((usage) => (
              <tr key={usage.id} className="border-b border-border/50 last:border-0">
                <td className={cn('py-2 pr-4', AGENT_STYLES[usage.agent.toUpperCase()]?.text || 'text-foreground')}>{usage.agent}</td>
                <td className="py-2 px-3 text-muted-foreground">{usage.model}</td>
                <td className="py-2 px-3 text-right text-muted-foreground tabular-nums">
                  {formatTokens(usage.input_tokens)}
                </td>
                <td className="py-2 px-3 text-right text-muted-foreground tabular-nums">
                  {formatTokens(usage.output_tokens)}
                </td>
                <td className="py-2 px-3 text-right text-muted-foreground tabular-nums">
                  {formatTokens(usage.cache_read_tokens)}
                </td>
                <td className="py-2 px-3 text-right text-primary tabular-nums">
                  {formatCost(usage.cost_usd)}
                </td>
                <td className="py-2 pl-3 text-right text-muted-foreground tabular-nums">
                  {formatDuration(usage.duration_ms)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
