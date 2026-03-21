/**
 * Shared API utilities used by both the main API client and settings client.
 */

/**
 * Base URL for all API requests.
 * Defaults to '/api' if VITE_API_BASE_URL environment variable is not set.
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Default timeout for API requests in milliseconds (30 seconds).
 */
export const DEFAULT_TIMEOUT_MS = 30000;

/**
 * Creates an AbortSignal that triggers after the specified timeout.
 *
 * @param timeoutMs - Timeout duration in milliseconds.
 * @returns An AbortSignal that will abort after the timeout.
 */
export function createTimeoutSignal(timeoutMs: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}
