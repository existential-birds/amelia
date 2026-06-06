import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { request } from '../utils';

const mockOnce = (r: unknown) =>
  vi.mocked(fetch).mockResolvedValueOnce(r as Response);

describe('request()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns parsed JSON, prepends base URL, and attaches a signal', async () => {
    mockOnce({ ok: true, json: async () => ({ value: 1 }) });

    expect(await request<{ value: number }>('/thing')).toEqual({ value: 1 });
    expect(fetch).toHaveBeenCalledWith(
      '/api/thing',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('drops undefined params, stringifies numbers, omits trailing ? when empty', async () => {
    mockOnce({ ok: true, json: async () => [] });

    await request('/issues', { params: { profile: 'p', search: undefined, limit: 5 } });

    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/issues?profile=p&limit=5');
  });

  it('sets Content-Type header and stringifies a JSON body', async () => {
    mockOnce({ ok: true, json: async () => ({}) });

    await request('/x', { method: 'POST', body: { a: 1 } });

    expect(fetch).toHaveBeenCalledWith(
      '/api/x',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ a: 1 }),
      })
    );
  });

  it('passes FormData as-is with no Content-Type header', async () => {
    const fd = new FormData();
    mockOnce({ ok: true, json: async () => ({}) });

    await request('/upload', { method: 'POST', body: fd });

    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(fd);
    expect(init.headers).toBeUndefined();
  });

  it('resolves undefined on 204 without calling json() (the bug fix)', async () => {
    mockOnce({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error('must not parse');
      },
    });

    await expect(request('/del', { method: 'DELETE' })).resolves.toBeUndefined();
  });

  it('throws ApiError with message from .detail on error', async () => {
    mockOnce({ ok: false, status: 404, json: async () => ({ detail: 'nope', code: 'NOT_FOUND' }) });

    await expect(request('/x')).rejects.toMatchObject({
      name: 'ApiError',
      code: 'NOT_FOUND',
      status: 404,
      message: 'nope',
    });
  });

  it('falls back to .error for the message when no .detail', async () => {
    mockOnce({ ok: false, status: 500, json: async () => ({ error: 'boom' }) });

    await expect(request('/x')).rejects.toMatchObject({ message: 'boom', code: 'HTTP_ERROR' });
  });

  it('throws ApiError ABORTED without fetching when signal is already aborted', async () => {
    const ctrl = new AbortController();
    ctrl.abort();

    await expect(request('/x', { signal: ctrl.signal })).rejects.toMatchObject({
      name: 'ApiError',
      code: 'ABORTED',
    });
    expect(fetch).not.toHaveBeenCalled();
  });
});
