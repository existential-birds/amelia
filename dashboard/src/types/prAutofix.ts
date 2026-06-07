/**
 * PR auto-fix metrics and classification audit types.
 * Mirrors the Python Pydantic models in `amelia/server/models/metrics.py`.
 */

/** Aggregated summary statistics for PR auto-fix pipeline runs. */
export interface PRAutoFixMetricsSummary {
  total_runs: number;
  total_comments_processed: number;
  total_fixed: number;
  total_failed: number;
  total_skipped: number;
  avg_latency_seconds: number;
  /** fixed / (fixed + failed + skipped), 0.0 when no data. */
  fix_rate: number;
}

/** Single day of aggregated PR auto-fix metrics. */
export interface PRAutoFixDailyBucket {
  /** ISO date string (YYYY-MM-DD). */
  date: string;
  total_runs: number;
  fixed: number;
  failed: number;
  skipped: number;
  avg_latency_s: number;
}

/** Metrics breakdown for a single aggressiveness level. */
export interface AggressivenessBreakdown {
  level: string;
  runs: number;
  fixed: number;
  failed: number;
  skipped: number;
  fix_rate: number;
}

/** Response from GET /api/github/pr-autofix/metrics. */
export interface PRAutoFixMetricsResponse {
  summary: PRAutoFixMetricsSummary;
  daily: PRAutoFixDailyBucket[];
  by_aggressiveness: AggressivenessBreakdown[];
}

/** Single classification audit log entry. */
export interface ClassificationRecord {
  comment_id: number;
  body_snippet: string;
  category: string;
  confidence: number;
  actionable: boolean;
  aggressiveness_level: string;
  prompt_hash: string | null;
  created_at: string;
}

/** Response from GET /api/github/pr-autofix/classifications. */
export interface ClassificationsResponse {
  classifications: ClassificationRecord[];
  total: number;
}
