/**
 * @fileoverview Loader for the Analytics page.
 * Fetches both usage (costs) and PR auto-fix metrics data in parallel.
 */
import { api } from '@/api/client';
import type { LoaderFunctionArgs } from 'react-router-dom';
import type { UsageResponse, PRAutoFixMetricsResponse } from '@/types';

/**
 * Loader data type for AnalyticsPage.
 */
export interface AnalyticsLoaderData {
  /** Usage data from API (for Costs tab). */
  usage: UsageResponse;
  /** PR auto-fix metrics data (for PR Fix Metrics tab). */
  metrics: PRAutoFixMetricsResponse;
  /** Current preset value (for UI state). */
  currentPreset: string;
}

/**
 * Loader for the Analytics page.
 * Fetches usage data and PR auto-fix metrics in parallel based on URL query parameters.
 *
 * @param args - React Router loader arguments.
 * @returns AnalyticsLoaderData with usage, metrics, and current preset.
 */
export async function analyticsLoader({
  request,
}: LoaderFunctionArgs): Promise<AnalyticsLoaderData> {
  const url = new URL(request.url);
  const preset = url.searchParams.get('preset') ?? '30d';

  const [usage, metrics] = await Promise.all([
    api.getUsage({ preset }),
    api.getAutoFixMetrics({ preset }),
  ]);

  return {
    usage,
    metrics,
    currentPreset: preset,
  };
}
