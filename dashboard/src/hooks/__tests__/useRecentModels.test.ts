import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRecentModels } from '../useRecentModels';
import { RECENT_MODELS_KEY, MAX_RECENT_MODELS } from '@/components/model-picker/constants';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

describe('useRecentModels', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it('should return empty array when no recent models', () => {
    const { result } = renderHook(() => useRecentModels());

    expect(result.current.recentModelIds).toEqual([]);
  });

  it('should load recent models from localStorage', () => {
    localStorageMock.getItem.mockReturnValueOnce(JSON.stringify(['model-a', 'model-b']));

    const { result } = renderHook(() => useRecentModels());

    expect(result.current.recentModelIds).toEqual(['model-a', 'model-b']);
  });

  it('should add model to recent list', () => {
    const { result } = renderHook(() => useRecentModels());

    act(() => {
      result.current.addRecentModel('model-a');
    });

    expect(result.current.recentModelIds).toEqual(['model-a']);
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      RECENT_MODELS_KEY,
      JSON.stringify(['model-a'])
    );
  });

  it('should move existing model to front', () => {
    localStorageMock.getItem.mockReturnValueOnce(JSON.stringify(['model-a', 'model-b', 'model-c']));

    const { result } = renderHook(() => useRecentModels());

    act(() => {
      result.current.addRecentModel('model-c');
    });

    expect(result.current.recentModelIds).toEqual(['model-c', 'model-a', 'model-b']);
  });

  it('should limit to MAX_RECENT_MODELS', () => {
    const existingModels = Array.from({ length: MAX_RECENT_MODELS }, (_, i) => `model-${i}`);
    localStorageMock.getItem.mockReturnValueOnce(JSON.stringify(existingModels));

    const { result } = renderHook(() => useRecentModels());

    act(() => {
      result.current.addRecentModel('new-model');
    });

    expect(result.current.recentModelIds).toHaveLength(MAX_RECENT_MODELS);
    expect(result.current.recentModelIds[0]).toBe('new-model');
    expect(result.current.recentModelIds).not.toContain(`model-${MAX_RECENT_MODELS - 1}`);
  });

  it('should handle invalid JSON in localStorage', () => {
    localStorageMock.getItem.mockReturnValueOnce('invalid json');

    const { result } = renderHook(() => useRecentModels());

    expect(result.current.recentModelIds).toEqual([]);
  });
});
