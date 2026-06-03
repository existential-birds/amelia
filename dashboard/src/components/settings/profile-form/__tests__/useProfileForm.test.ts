import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useProfileForm } from '../useProfileForm';
import { createMockProfile } from '@/__tests__/fixtures';

describe('useProfileForm', () => {
  it('reproduces the modal update payload from a profile', () => {
    const profile = createMockProfile({
      id: 'dev',
      repo_root: '/r',
      agents: { architect: { driver: 'claude', model: 'opus', options: {} } },
      sandbox: {
        mode: 'container',
        image: 'img',
        network_allowlist_enabled: true,
        network_allowed_hosts: ['a.com'],
      },
    });
    const { result } = renderHook(() => useProfileForm(profile));
    const p = result.current.toUpdatePayload();
    expect(p.repo_root).toBe('/r');
    expect(p.sandbox).toMatchObject({
      mode: 'container',
      network_allowlist_enabled: true,
      network_allowed_hosts: ['a.com'],
    });
    expect(p.sandbox).not.toHaveProperty('repo_url'); // daytona fields omitted in container mode
    expect(p.agents?.architect).toEqual({ driver: 'claude', model: 'opus' });
  });

  it('blocks: validate() flags empty repo_root and marks identity section', () => {
    const { result } = renderHook(() => useProfileForm(null));
    let ok!: boolean;
    act(() => {
      ok = result.current.validate();
    });
    expect(ok).toBe(false);
    expect(result.current.errors.repo_root).toBeTruthy();
    expect(result.current.sectionErrors.identity).toBe(true);
  });

  it('isDirty flips when a field changes', () => {
    const { result } = renderHook(() => useProfileForm(createMockProfile()));
    expect(result.current.isDirty).toBe(false);
    act(() => result.current.setField('repo_root', '/changed'));
    expect(result.current.isDirty).toBe(true);
  });
});
