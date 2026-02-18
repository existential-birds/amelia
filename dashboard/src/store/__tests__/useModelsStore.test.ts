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
      data: [
        {
          id: 'anthropic/claude-sonnet-4',
          name: 'Claude Sonnet 4',
          context_length: 200000,
          pricing: { prompt: '0.000003', completion: '0.000015' },
          architecture: { input_modalities: ['text', 'image'], output_modalities: ['text'] },
          top_provider: { context_length: 200000, max_completion_tokens: 16000 },
          supported_parameters: ['tools', 'reasoning', 'response_format'],
        },
      ],
    };

    it('should fetch and store models', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockApiResponse),
      });

      await useModelsStore.getState().fetchModels();

      const state = useModelsStore.getState();
      expect(state.models).toHaveLength(1);
      expect(state.models[0]?.id).toBe('anthropic/claude-sonnet-4');
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
        data: [
          {
            id: 'test/new-model',
            name: 'New Model',
            context_length: 100000,
            pricing: { prompt: '0.000001', completion: '0.000001' },
            architecture: { input_modalities: ['text'], output_modalities: ['text'] },
            top_provider: { context_length: 100000, max_completion_tokens: 8000 },
            supported_parameters: ['tools', 'reasoning', 'response_format'],
          },
        ],
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
      expect(state.models[0]?.id).toBe('test/new-model');
    });

    it('should abort pending request when new refresh is triggered', async () => {
      const abortSpy = vi.fn();
      const mockAbortController = {
        abort: abortSpy,
        signal: new AbortController().signal,
      };

      useModelsStore.setState({
        abortController: mockAbortController as unknown as AbortController,
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      });

      await useModelsStore.getState().refreshModels();

      expect(abortSpy).toHaveBeenCalledOnce();
    });

    it('should not update state when request is aborted', async () => {
      const abortError = new Error('Aborted');
      abortError.name = 'AbortError';

      mockFetch.mockRejectedValueOnce(abortError);

      const initialState = useModelsStore.getState();
      await useModelsStore.getState().refreshModels();

      const finalState = useModelsStore.getState();
      expect(finalState.error).toBeNull();
      expect(finalState.models).toEqual(initialState.models);
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
