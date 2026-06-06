/**
 * Shared mock helpers for the global `fetch` in API tests.
 * Used by API client test suites (client, brainstorm, settings, prompts, etc.)
 * to queue success and error responses without redeclaring local helpers.
 *
 * Requires `fetch` to be mocked first (e.g. `global.fetch = vi.fn()` or
 * `vi.stubGlobal('fetch', vi.fn())`).
 *
 * @example
 * ```ts
 * import { mockFetchSuccess, mockFetchError } from '@/test/mocks/fetch';
 *
 * mockFetchSuccess({ workflows: [] });
 * mockFetchError(404, { error: 'Not found', code: 'NOT_FOUND' });
 * ```
 */

import { vi } from 'vitest';

/**
 * Queues a successful `fetch` response resolving to `data` from `.json()`.
 */
export function mockFetchSuccess<T>(data: T) {
  vi.mocked(fetch).mockResolvedValueOnce({
    ok: true,
    json: async () => data,
  } as Response);
}

/**
 * Queues a failed `fetch` response with the given status and JSON body.
 */
export function mockFetchError(
  status: number,
  body: Record<string, unknown>,
  statusText?: string
) {
  vi.mocked(fetch).mockResolvedValueOnce({
    ok: false,
    status,
    statusText,
    json: async () => body,
  } as Response);
}
