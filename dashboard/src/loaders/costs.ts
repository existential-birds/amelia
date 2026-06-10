/**
 * @fileoverview Loader for the Costs page.
 */
import { api } from '@/api/client';
import type { LoaderFunctionArgs } from 'react-router-dom';
import type { UsageResponse } from '@/types';

/**
 * Loader data type for CostsPage.
 */
export interface CostsLoaderData {
  /** Usage data from API. */
  usage: UsageResponse;
  /** Current preset value (for UI state). */
  currentPreset: string | null;
  /** Current start date (for custom range). */
  currentStart: string | null;
  /** Current end date (for custom range). */
  currentEnd: string | null;
}

/**
 * Loader for the Costs page.
 * Fetches usage data based on URL query parameters.
 *
 * @param args - React Router loader arguments.
 * @returns CostsLoaderData with usage metrics and current params.
 *
 * @example
 * // URL: /costs?preset=30d
 * const { usage, currentPreset } = await costsLoader({ request });
 *
 * @example
 * // URL: /costs?start=2026-01-01&end=2026-01-15
 * const { usage, currentStart, currentEnd } = await costsLoader({ request });
 */
export async function costsLoader({
  request,
}: LoaderFunctionArgs): Promise<CostsLoaderData> {
  const url = new URL(request.url);
  const preset = url.searchParams.get('preset');
  const start = url.searchParams.get('start');
  const end = url.searchParams.get('end');

  let apiParams: { preset?: string; start?: string; end?: string };
  if (start && end) {
    apiParams = { start, end };
  } else {
    apiParams = { preset: preset ?? '30d' };
  }

  const usage = await api.getUsage(apiParams);

  return {
    usage,
    currentPreset: start && end ? null : (preset ?? '30d'),
    currentStart: start,
    currentEnd: end,
  };
}
