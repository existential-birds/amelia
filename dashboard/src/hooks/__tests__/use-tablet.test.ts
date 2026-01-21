/**
 * @fileoverview Tests for the useIsTablet hook.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useIsTablet } from '../use-tablet';

describe('useIsTablet', () => {
  let matchMediaMock: ReturnType<typeof vi.fn>;
  let listeners: Array<() => void>;

  beforeEach(() => {
    listeners = [];
    matchMediaMock = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: (_: string, cb: () => void) => {
        listeners.push(cb);
      },
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    vi.stubGlobal('matchMedia', matchMediaMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns false for viewport width >= 1024px', () => {
    vi.stubGlobal('innerWidth', 1024);

    const { result } = renderHook(() => useIsTablet());

    expect(result.current).toBe(false);
  });

  it('returns true for viewport width < 1024px', () => {
    vi.stubGlobal('innerWidth', 1023);

    const { result } = renderHook(() => useIsTablet());

    expect(result.current).toBe(true);
  });

  it('returns true for viewport width 768px (tablet)', () => {
    vi.stubGlobal('innerWidth', 768);

    const { result } = renderHook(() => useIsTablet());

    expect(result.current).toBe(true);
  });

  it('updates when viewport changes', () => {
    vi.stubGlobal('innerWidth', 1024);

    const { result } = renderHook(() => useIsTablet());
    expect(result.current).toBe(false);

    // Simulate resize to tablet
    act(() => {
      vi.stubGlobal('innerWidth', 800);
      listeners.forEach((cb) => cb());
    });

    expect(result.current).toBe(true);
  });

  it('cleans up event listener on unmount', () => {
    const removeEventListener = vi.fn();
    matchMediaMock.mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener,
    }));

    vi.stubGlobal('innerWidth', 1024);

    const { unmount } = renderHook(() => useIsTablet());
    unmount();

    expect(removeEventListener).toHaveBeenCalledWith('change', expect.any(Function));
  });
});
