import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useModelsStore } from '../useModelsStore';
import type { ModelInfo } from '@/components/model-picker/types';

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('useModelsStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset store state
    useModelsStore.setState({
      models: [],
      providers: [],
      isLoading: false,
      error: null,
      lastFetched: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('fetchModels', () => {
    const mockApiResponse = {
      anthropic: {
        id: 'anthropic',
        name: 'Anthropic',
        models: {
          'claude-sonnet-4': {
            id: 'claude-sonnet-4',
            name: 'Claude Sonnet 4',
            tool_call: true,
            reasoning: true,
            structured_output: true,
            cost: { input: 3, output: 15 },
            limit: { context: 200000, output: 16000 },
            modalities: { input: ['text', 'image'], output: ['text'] },
          },
        },
      },
    };

    it('should fetch and store models', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockApiResponse),
      });

      await useModelsStore.getState().fetchModels();

      const state = useModelsStore.getState();
      expect(state.models).toHaveLength(1);
      expect(state.models[0]?.id).toBe('claude-sonnet-4');
      expect(state.providers).toEqual(['anthropic']);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.lastFetched).not.toBeNull();
    });

    it('should skip fetch if already loaded this session', async () => {
      useModelsStore.setState({
        models: [{ id: 'existing' } as ModelInfo],
        lastFetched: Date.now(),
      });

      await useModelsStore.getState().fetchModels();

      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('should set error state on fetch failure', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      await useModelsStore.getState().fetchModels();

      const state = useModelsStore.getState();
      expect(state.error).toBe('Failed to load models. Check your connection.');
      expect(state.isLoading).toBe(false);
    });

    it('should set loading state during fetch', async () => {
      let resolvePromise: (value: unknown) => void;
      const fetchPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });

      mockFetch.mockReturnValueOnce(fetchPromise);

      const fetchPromiseResult = useModelsStore.getState().fetchModels();

      expect(useModelsStore.getState().isLoading).toBe(true);

      resolvePromise!({
        ok: true,
        json: () => Promise.resolve(mockApiResponse),
      });

      await fetchPromiseResult;

      expect(useModelsStore.getState().isLoading).toBe(false);
    });
  });

  describe('refreshModels', () => {
    it('should force refetch even if already loaded', async () => {
      const mockApiResponse = {
        anthropic: {
          id: 'anthropic',
          name: 'Anthropic',
          models: {
            'new-model': {
              id: 'new-model',
              name: 'New Model',
              tool_call: true,
              reasoning: true,
              structured_output: true,
              cost: { input: 1, output: 1 },
              limit: { context: 100000, output: 8000 },
              modalities: { input: ['text'], output: ['text'] },
            },
          },
        },
      };

      useModelsStore.setState({
        models: [{ id: 'old-model' } as ModelInfo],
        lastFetched: Date.now(),
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockApiResponse),
      });

      await useModelsStore.getState().refreshModels();

      const state = useModelsStore.getState();
      expect(state.models).toHaveLength(1);
      expect(state.models[0]?.id).toBe('new-model');
    });
  });

  describe('getModelsForAgent', () => {
    it('should filter models by agent requirements', () => {
      const models: ModelInfo[] = [
        {
          id: 'model-a',
          name: 'Model A',
          provider: 'test',
          capabilities: { tool_call: true, reasoning: true, structured_output: true },
          cost: { input: 3, output: 15 },
          limit: { context: 200000, output: 16000 },
          modalities: { input: ['text'], output: ['text'] },
        },
        {
          id: 'model-b',
          name: 'Model B',
          provider: 'test',
          capabilities: { tool_call: true, reasoning: false, structured_output: true },
          cost: { input: 0.1, output: 0.5 },
          limit: { context: 64000, output: 8000 },
          modalities: { input: ['text'], output: ['text'] },
        },
      ];

      useModelsStore.setState({ models });

      // Architect requires reasoning
      const architectModels = useModelsStore.getState().getModelsForAgent('architect');
      expect(architectModels).toHaveLength(1);
      expect(architectModels[0]?.id).toBe('model-a');

      // Developer doesn't require reasoning
      const developerModels = useModelsStore.getState().getModelsForAgent('developer');
      expect(developerModels).toHaveLength(1);
      expect(developerModels[0]?.id).toBe('model-a'); // model-b fails context requirement
    });

    it('should return all models for unknown agent', () => {
      const models: ModelInfo[] = [
        {
          id: 'model-a',
          name: 'Model A',
          provider: 'test',
          capabilities: { tool_call: true, reasoning: true, structured_output: true },
          cost: { input: 3, output: 15 },
          limit: { context: 200000, output: 16000 },
          modalities: { input: ['text'], output: ['text'] },
        },
      ];

      useModelsStore.setState({ models });

      const result = useModelsStore.getState().getModelsForAgent('unknown-agent');
      expect(result).toHaveLength(1);
    });
  });
});
