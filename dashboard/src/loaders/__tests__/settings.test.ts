import { describe, it, expect, vi, beforeEach } from 'vitest';
import { profileDetailLoader } from '../settings';
import { getProfile } from '@/api/settings';
import { createMockProfile } from '@/__tests__/fixtures';
import type { LoaderFunctionArgs } from 'react-router-dom';

vi.mock('@/api/settings');

/**
 * Helper to create LoaderFunctionArgs for testing.
 * Mirrors `createLoaderArgs` in workflows.test.ts.
 */
function args(params: Record<string, string>): LoaderFunctionArgs {
  return {
    params,
    request: new Request('http://localhost'),
  } as unknown as LoaderFunctionArgs;
}

describe('profileDetailLoader', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads one profile by id', async () => {
    const profile = createMockProfile({ id: 'dev' });
    vi.mocked(getProfile).mockResolvedValue(profile);
    await expect(profileDetailLoader(args({ id: 'dev' }))).resolves.toEqual({ profile });
    expect(getProfile).toHaveBeenCalledWith('dev');
  });

  it('returns null profile in create mode (no id)', async () => {
    await expect(profileDetailLoader(args({}))).resolves.toEqual({ profile: null });
    expect(getProfile).not.toHaveBeenCalled();
  });

  it('propagates fetch failures for an existing id instead of falling back to create mode', async () => {
    const error = new Error('not found');
    vi.mocked(getProfile).mockRejectedValue(error);
    await expect(profileDetailLoader(args({ id: 'dev' }))).rejects.toThrow('not found');
    expect(getProfile).toHaveBeenCalledWith('dev');
  });
});
