/**
 * Shared mock configuration for useModelsStore.
 * Used by components that depend on the models store (ApiModelSelect, ModelPickerSheet, etc.).
 *
 * @example Basic usage
 * ```ts
 * import { vi } from 'vitest';
 * import { useModelsStore } from '@/store/useModelsStore';
 * import { createMockModelsStore, defaultModelStoreState } from '@/test/mocks/modelsStore';
 *
 * vi.mock('@/store/useModelsStore');
 *
 * beforeEach(() => {
 *   vi.mocked(useModelsStore).mockImplementation(createMockModelsStore());
 * });
 * ```
 *
 * @example With custom state
 * ```ts
 * vi.mocked(useModelsStore).mockImplementation(
 *   createMockModelsStore({
 *     isLoading: true,
 *     models: [],
 *   })
 * );
 * ```
 */

import { vi } from 'vitest';
import type { useModelsStore } from '@/store/useModelsStore';
import type { ModelInfo } from '@/components/model-picker/types';

/**
 * Default mock models for testing.
 *
 * Use this export when you need to:
 * - Reference sample model data in test assertions
 * - Provide model options to components under test
 * - Create custom store states with specific model configurations
 *
 * @example
 * ```ts
 * // Assert against expected model data
 * expect(result).toContain(mockModels[0]);
 *
 * // Create custom store state with different models
 * const customState = { ...defaultModelsStoreState, models: [mockModels[0]] };
 * ```
 */
export const mockModels: ModelInfo[] = [
  {
    id: 'claude-sonnet-4',
    name: 'Claude Sonnet 4',
    provider: 'anthropic',
    capabilities: { tool_call: true, reasoning: true, structured_output: true },
    cost: { input: 3, output: 15 },
    limit: { context: 200000, output: 16000 },
    modalities: { input: ['text'], output: ['text'] },
  },
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    provider: 'openai',
    capabilities: { tool_call: true, reasoning: false, structured_output: true },
    cost: { input: 2.5, output: 10 },
    limit: { context: 128000, output: 16384 },
    modalities: { input: ['text'], output: ['text'] },
  },
];

/**
 * Default mock state for the models store.
 *
 * Use this export when you need to:
 * - Create partial overrides with `createMockModelsStore({ ...overrides })`
 * - Build custom store states while preserving base data
 *
 * Represents a fully populated models store with:
 * - Pre-loaded models from `mockModels`
 * - Default loading/error states
 *
 * Note: Mock functions (fetchModels, refreshModels, etc.) are created fresh
 * in createMockModelsStore() for test isolation.
 *
 * @example
 * ```ts
 * // Override specific state while keeping defaults
 * const customStore = createMockModelsStore({ isLoading: true });
 * ```
 */
export const defaultModelsStoreState = {
  models: mockModels,
  providers: ['anthropic', 'openai'],
  isLoading: false,
  error: null,
  lastFetched: Date.now(),
};

/**
 * Creates a mock implementation of useModelsStore that supports both
 * selector pattern (useModelsStore((s) => s.models)) and direct call pattern (useModelsStore()).
 *
 * This matches the Zustand store API which allows both usage patterns.
 *
 * @param overrides - Partial state to override defaults
 * @returns Mock implementation function for vi.mocked(useModelsStore)
 */
export function createMockModelsStore(
  overrides: Partial<ReturnType<typeof useModelsStore>> = {}
) {
  const state = {
    ...defaultModelsStoreState,
    fetchModels: vi.fn(),
    refreshModels: vi.fn(),
    getModelsForAgent: vi.fn().mockReturnValue(mockModels),
    ...overrides,
  };

  // Support both selector pattern and direct call pattern
  return (selector?: unknown) =>
    typeof selector === 'function' ? selector(state) : state;
}
