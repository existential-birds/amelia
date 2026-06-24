/**
 * Usage analytics API types.
 * Mirrors the Python Pydantic models in `amelia/server/models/usage.py`.
 */

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
  successful_workflows?: number | null;
  /** Success rate (0-1), successful_workflows / workflows. */
  success_rate?: number | null;
  /** Peak tokens occupying the model context window. */
  context_tokens?: number | null;
  /** Model context window size in tokens. */
  context_window_tokens?: number | null;
  /** Peak context fill fraction (0-1). */
  context_utilization?: number | null;
  /** Whether context utilization crossed the configured warning threshold. */
  context_window_warning?: boolean;
  /** Warning threshold fraction (defaults to 0.8). */
  context_warning_threshold?: number;
}

/**
 * Response from GET /api/usage endpoint.
 */
export interface UsageResponse {
  /** Aggregated summary statistics. */
  summary: UsageSummary;
  /** Daily trend data points. */
  trend: UsageTrendPoint[];
  /** Breakdown by model. */
  by_model: UsageByModel[];
}
