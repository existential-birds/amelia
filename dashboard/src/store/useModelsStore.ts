import { create } from 'zustand';
import type { ModelInfo } from '@/components/model-picker/types';
import { AGENT_MODEL_REQUIREMENTS, MODELS_API_URL } from '@/components/model-picker/constants';
import { flattenModelsData, filterModelsByRequirements } from '@/lib/models-utils';
import { logger } from '@/lib/logger';

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
  /** AbortController for the current fetch */
  abortController: AbortController | null;
  /** Timeout ID for the current fetch timeout */
  timeoutId?: ReturnType<typeof setTimeout>;

  /** Fetch models from OpenRouter API (skips if already loaded) */
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
  abortController: null,
  timeoutId: undefined,

  fetchModels: async () => {
    // Skip if already fetched this session
    if (get().models.length > 0 && get().lastFetched) {
      return;
    }

    await get().refreshModels();
  },

  refreshModels: async () => {
    // Cancel any pending request
    const currentController = get().abortController;
    const currentTimeoutId = get().timeoutId;
    if (currentController) {
      currentController.abort();
    }
    if (currentTimeoutId !== undefined) {
      clearTimeout(currentTimeoutId);
    }

    // Create new AbortController for this request
    const abortController = new AbortController();

    // Set timeout to abort request after 30 seconds
    let timedOut = false;
    const timeoutId = setTimeout(() => {
      timedOut = true;
      abortController.abort();
    }, 30000);

    set({ isLoading: true, error: null, abortController, timeoutId });

    try {
      const response = await fetch(MODELS_API_URL, { signal: abortController.signal });
      clearTimeout(timeoutId);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      let data;
      try {
        data = await response.json();
      } catch (parseError) {
        throw new Error(`Invalid JSON response from models API: ${parseError}`);
      }

      if (!data || !data.data || !Array.isArray(data.data)) {
        throw new Error('Invalid response shape from models API');
      }

      const models = flattenModelsData(data.data);
      const providers = [...new Set(models.map((m) => m.provider))];

      set({
        models,
        providers,
        isLoading: false,
        lastFetched: Date.now(),
        // Safe to clear: if aborted before this point, we return early in the catch block
        abortController: null,
        timeoutId: undefined,
      });
    } catch (err) {
      clearTimeout(timeoutId);
      // Don't update state if the request was aborted (a newer request is in progress)
      if (err instanceof Error && err.name === 'AbortError') {
        set({
          error: timedOut ? 'Request timed out after 30 seconds. Check your connection.' : null,
          isLoading: false,
          abortController: null,
          timeoutId: undefined,
        });
        return;
      }

      logger.error('Failed to fetch models', err, {
        url: MODELS_API_URL,
        timestamp: Date.now(),
      });
      set({
        error: 'Failed to load models. Check your connection.',
        isLoading: false,
        abortController: null,
        timeoutId: undefined,
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
