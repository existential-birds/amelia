import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRecentModels } from '../useRecentModels';
import { RECENT_MODELS_KEY, MAX_RECENT_MODELS } from '@/components/model-picker/constants';

describe('useRecentModels', () => {
  let store: Record<string, string>;
  let getItemSpy: ReturnType<typeof vi.fn<(key: string) => string | null>>;
  let setItemSpy: ReturnType<typeof vi.fn<(key: string, value: string) => void>>;

  beforeEach(() => {
    store = {};
    getItemSpy = vi.fn<(key: string) => string | null>((key) => store[key] ?? null);
    setItemSpy = vi.fn<(key: string, value: string) => void>((key, value) => {
      store[key] = value;
    });
    vi.stubGlobal('localStorage', {
      getItem: getItemSpy,
      setItem: setItemSpy,
      removeItem: vi.fn(),
      clear: vi.fn(),
      key: vi.fn(),
      length: 0,
    } satisfies Storage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('should return empty array when no recent models', () => {
    const { result } = renderHook(() => useRecentModels());

    expect(result.current.recentModelIds).toEqual([]);
  });

  it('should load recent models from localStorage', () => {
    getItemSpy.mockReturnValueOnce(JSON.stringify(['model-a', 'model-b']));

    const { result } = renderHook(() => useRecentModels());

    expect(result.current.recentModelIds).toEqual(['model-a', 'model-b']);
  });

  it('should add model to recent list', () => {
    const { result } = renderHook(() => useRecentModels());

    act(() => {
      result.current.addRecentModel('model-a');
    });

    expect(result.current.recentModelIds).toEqual(['model-a']);
    expect(setItemSpy).toHaveBeenCalledWith(
      RECENT_MODELS_KEY,
      JSON.stringify(['model-a'])
    );
  });

  it('should move existing model to front', () => {
    getItemSpy.mockReturnValueOnce(JSON.stringify(['model-a', 'model-b', 'model-c']));

    const { result } = renderHook(() => useRecentModels());

    act(() => {
      result.current.addRecentModel('model-c');
    });

    expect(result.current.recentModelIds).toEqual(['model-c', 'model-a', 'model-b']);
  });

  it('should limit to MAX_RECENT_MODELS', () => {
    const existingModels = Array.from({ length: MAX_RECENT_MODELS }, (_, i) => `model-${i}`);
    getItemSpy.mockReturnValueOnce(JSON.stringify(existingModels));

    const { result } = renderHook(() => useRecentModels());

    act(() => {
      result.current.addRecentModel('new-model');
    });

    expect(result.current.recentModelIds).toHaveLength(MAX_RECENT_MODELS);
    expect(result.current.recentModelIds[0]).toBe('new-model');
    expect(result.current.recentModelIds).not.toContain(`model-${MAX_RECENT_MODELS - 1}`);
  });

  it('should handle invalid JSON in localStorage', () => {
    getItemSpy.mockReturnValueOnce('invalid json');

    const { result } = renderHook(() => useRecentModels());

    expect(result.current.recentModelIds).toEqual([]);
    expect(result.current.hasParseError).toBe(true);
  });
});
