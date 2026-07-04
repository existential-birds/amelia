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
    expect(p.agents?.architect).toEqual({ driver: 'claude', model: 'opus', options: {} });
  });

  it('toUpdatePayload includes agent options', () => {
    const profile = createMockProfile({
      id: 'dev',
      repo_root: '/r',
      agents: {
        developer: {
          driver: 'claude',
          model: 'opus',
          options: { moa: { enabled: true, proposer_count: 4 } },
        },
      },
    });
    const { result } = renderHook(() => useProfileForm(profile));
    const p = result.current.toUpdatePayload();
    expect(p.agents?.developer?.options).toEqual({
      moa: { enabled: true, proposer_count: 4 },
    });
  });

  it('setAgentOption updates options', () => {
    const { result } = renderHook(() => useProfileForm(createMockProfile()));
    act(() => result.current.setAgentOption('developer', 'moa', { enabled: true }));
    expect(result.current.formData.agents.developer?.options.moa).toEqual({
      enabled: true,
    });
  });

  it('isDirty detects an options change', () => {
    const { result } = renderHook(() => useProfileForm(createMockProfile()));
    expect(result.current.isDirty).toBe(false);
    act(() => result.current.setAgentOption('developer', 'moa', { enabled: true }));
    expect(result.current.isDirty).toBe(true);
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

  it('markSaved() resets isDirty to false', () => {
    const { result } = renderHook(() => useProfileForm(createMockProfile()));
    act(() => result.current.setField('repo_root', '/changed'));
    expect(result.current.isDirty).toBe(true);
    act(() => result.current.markSaved());
    expect(result.current.isDirty).toBe(false);
  });
});
