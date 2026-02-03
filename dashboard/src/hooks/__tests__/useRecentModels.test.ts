import { describe, it, expect, beforeEach, afterEach, vi, type MockInstance } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRecentModels } from '../useRecentModels';
import { RECENT_MODELS_KEY, MAX_RECENT_MODELS } from '@/components/model-picker/constants';

describe('useRecentModels', () => {
  let store: Record<string, string> = {};
  let getItemSpy: MockInstance<(key: string) => string | null>;
  let setItemSpy: MockInstance<(key: string, value: string) => void>;

  beforeEach(() => {
    store = {};
    getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key: string) => store[key] ?? null);
    setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key: string, value: string) => {
      store[key] = value;
    });
  });

  afterEach(() => {
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
