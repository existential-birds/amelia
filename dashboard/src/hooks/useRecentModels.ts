import { useState, useCallback, useEffect } from 'react';
import { RECENT_MODELS_KEY, MAX_RECENT_MODELS } from '@/components/model-picker/constants';

/**
 * Hook for managing recently used model IDs in localStorage.
 */
export function useRecentModels() {
  const [recentModelIds, setRecentModelIds] = useState<string[]>([]);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(RECENT_MODELS_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setRecentModelIds(parsed);
        }
      }
    } catch (error) {
      // Invalid JSON, start fresh
      console.warn('Failed to load recent models from localStorage:', error);
      setRecentModelIds([]);
    }
  }, []);

  const addRecentModel = useCallback((modelId: string) => {
    setRecentModelIds((prev) => {
      // Remove if already exists (will be added to front)
      const filtered = prev.filter((id) => id !== modelId);
      // Add to front and limit size
      const updated = [modelId, ...filtered].slice(0, MAX_RECENT_MODELS);

      // Persist to localStorage
      localStorage.setItem(RECENT_MODELS_KEY, JSON.stringify(updated));

      return updated;
    });
  }, []);

  return { recentModelIds, addRecentModel };
}
