import { create } from 'zustand';
import type { ModelInfo } from '@/components/model-picker/types';
import { AGENT_MODEL_REQUIREMENTS, MODELS_API_URL } from '@/components/model-picker/constants';
import { flattenModelsData, filterModelsByRequirements } from '@/lib/models-utils';

/**
 * State for the models store.
 */
interface ModelsState {
  /** Flattened list of all models from OpenRouter */
  models: ModelInfo[];
  /** Unique list of provider IDs */
  providers: string[];
  /** Whether a fetch is in progress */
  isLoading: boolean;
  /** Error message from last fetch attempt */
  error: string | null;
  /** Timestamp of last successful fetch */
  lastFetched: number | null;

  /** Fetch models from models.dev (skips if already loaded) */
  fetchModels: () => Promise<void>;
  /** Force refresh models even if already loaded */
  refreshModels: () => Promise<void>;
  /** Get models filtered by agent requirements */
  getModelsForAgent: (agentKey: string) => ModelInfo[];
}

/**
 * Zustand store for OpenRouter model data.
 */
export const useModelsStore = create<ModelsState>((set, get) => ({
  models: [],
  providers: [],
  isLoading: false,
  error: null,
  lastFetched: null,

  fetchModels: async () => {
    // Skip if already fetched this session
    if (get().models.length > 0 && get().lastFetched) {
      return;
    }

    await get().refreshModels();
  },

  refreshModels: async () => {
    set({ isLoading: true, error: null });

    try {
      const response = await fetch(MODELS_API_URL);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      let data;
      try {
        data = await response.json();
      } catch (parseError) {
        throw new Error(`Invalid JSON response from models API: ${parseError}`);
      }

      const models = flattenModelsData(data.data);
      const providers = [...new Set(models.map((m) => m.provider))];

      set({
        models,
        providers,
        isLoading: false,
        lastFetched: Date.now(),
      });
    } catch (err) {
      console.error('Failed to fetch models:', err);
      set({
        error: 'Failed to load models. Check your connection.',
        isLoading: false,
      });
    }
  },

  getModelsForAgent: (agentKey: string) => {
    const { models } = get();
    const requirements = AGENT_MODEL_REQUIREMENTS[agentKey];

    if (!requirements) {
      // Unknown agent - return all models with tool_call
      return models;
    }

    return filterModelsByRequirements(models, requirements);
  },
}));
