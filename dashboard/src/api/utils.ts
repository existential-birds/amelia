/**
 * Shared API utilities used by both the main API client and settings client.
 */

import { parseErrorDetail } from './errors';

/** Base URL for all API requests; defaults to '/api' when VITE_API_BASE_URL is unset. */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/** Default timeout for API requests, in milliseconds. */
export const DEFAULT_TIMEOUT_MS = 30000;

/**
 * Error for API failures, carrying a machine-readable `code`, HTTP `status`,
 * and optional `details` alongside the message.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Wraps fetch with a timeout, optionally combined with an external abort
 * signal. Throws {@link ApiError} with a TIMEOUT or ABORTED code on abort.
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  abortSignal?: AbortSignal
): Promise<Response> {
  const timeoutSignal = AbortSignal.timeout(DEFAULT_TIMEOUT_MS);

  // Combine timeout signal with optional abort signal
  const signal = abortSignal
    ? AbortSignal.any([timeoutSignal, abortSignal])
    : timeoutSignal;

  try {
    return await fetch(url, { ...options, signal });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      // Check if it was an external abort (not timeout)
      if (abortSignal?.aborted) {
        throw new ApiError('Request aborted', 'ABORTED', 0);
      }
      throw new ApiError('Request timeout', 'TIMEOUT', 408);
    }
    throw error;
  }
}

/**
 * Handles HTTP response parsing and error handling.
 *
 * Checks if the response is successful, parses the JSON body, and throws
 * ApiError if the response indicates an error. Attempts to parse error
 * details from the response body when available.
 *
 * @param response - The fetch Response object to handle.
 * @returns The parsed JSON response body.
 * @throws {ApiError} When the response status is not OK (non-2xx status code).
 *
 * @example
 * ```typescript
 * const response = await fetch('/api/workflows');
 * const data = await handleResponse<WorkflowListResponse>(response);
 * ```
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: Record<string, unknown>;
    try {
      errorData = await response.json();
    } catch {
      throw new ApiError(
        `HTTP ${response.status}: ${response.statusText}`,
        'HTTP_ERROR',
        response.status
      );
    }

    // Handle both our ErrorResponse format ({error, code}) and
    // FastAPI's HTTPException format ({detail})
    const message = parseErrorDetail(
      errorData.detail ?? errorData.error,
      `HTTP ${response.status}: ${response.statusText}`
    );
    const code = (errorData.code as string) || 'HTTP_ERROR';

    throw new ApiError(
      message,
      code,
      response.status,
      errorData.details as Record<string, unknown> | undefined
    );
  }

  // Handle responses with no content (e.g., 204 No Content from DELETE)
  if (response.status === 204 || response.headers?.get('content-length') === '0') {
    return (void 0) as T;
  }

  return response.json();
}

/**
 * Builds a query string from a record of params, skipping `undefined` values
 * and coercing numbers to strings via `String()`. Returns `''` when no
 * defined entries remain (no leading `?`).
 *
 * @example
 * buildQuery({ profile: 'p', limit: 5, search: undefined })
 * // => '?profile=p&limit=5'
 *
 * buildQuery({})   // => ''
 * buildQuery()     // => ''
 */
export function buildQuery(
  params?: Record<string, string | number | undefined>
): string {
  if (!params) {
    return '';
  }
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) {
      continue;
    }
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}

/** Options accepted by {@link request}. */
export interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
}

/**
 * Generic typed HTTP helper: prepends {@link API_BASE_URL}, serializes JSON
 * bodies (passing `FormData` through untouched), maps timeouts/aborts to
 * {@link ApiError}, and parses the response via {@link handleResponse}.
 *
 * @throws {ApiError} with code `ABORTED` if `opts.signal` is already aborted
 * (before any fetch), `TIMEOUT` on timeout, or an HTTP error code on non-2xx.
 */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  if (opts.signal?.aborted) {
    throw new ApiError('Request aborted', 'ABORTED', 0);
  }

  const url = `${API_BASE_URL}${path}${buildQuery(opts.params)}`;
  const isFormData = opts.body instanceof FormData;
  const headers = isFormData ? undefined : { 'Content-Type': 'application/json' };
  const body =
    opts.body === undefined
      ? undefined
      : isFormData
        ? (opts.body as FormData)
        : JSON.stringify(opts.body);

  const response = await fetchWithTimeout(
    url,
    { method: opts.method, headers, body },
    opts.signal
  );
  return handleResponse<T>(response);
}
