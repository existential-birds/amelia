/**
 * Shared API utilities used by both the main API client and settings client.
 */

/** Base URL for all API requests; defaults to '/api' when VITE_API_BASE_URL is unset. */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/** Default timeout for API requests, in milliseconds. */
export const DEFAULT_TIMEOUT_MS = 30000;

/** Creates an AbortSignal that aborts after `timeoutMs`. */
export function createTimeoutSignal(timeoutMs: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}
