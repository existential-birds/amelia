import { describe, it, expect } from 'vitest';
import {
  flattenModelsData,
  getPriceTier,
  filterModelsByRequirements,
  formatContextSize,
} from '../models-utils';
import type { ModelInfo, AgentRequirements } from '@/components/model-picker/types';

describe('models-utils', () => {
  describe('flattenModelsData', () => {
    it('should flatten OpenRouter models and extract provider from ID', () => {
      const apiResponse = [
        {
          id: 'anthropic/claude-sonnet-4',
          name: 'Claude Sonnet 4',
          context_length: 200000,
          pricing: { prompt: '0.000003', completion: '0.000015' },
          architecture: { input_modalities: ['text', 'image'], output_modalities: ['text'] },
          top_provider: { context_length: 200000, max_completion_tokens: 16000 },
          supported_parameters: ['tools', 'reasoning', 'response_format'],
        },
        {
          id: 'openai/gpt-4o',
          name: 'GPT-4o',
          context_length: 128000,
          pricing: { prompt: '0.0000025', completion: '0.00001' },
          architecture: { input_modalities: ['text', 'image'], output_modalities: ['text'] },
          top_provider: { context_length: 128000, max_completion_tokens: 16384 },
          supported_parameters: ['tools', 'response_format'],
        },
      ];

      const result = flattenModelsData(apiResponse);

      expect(result).toHaveLength(2);
      expect(result[0]).toEqual({
        id: 'anthropic/claude-sonnet-4',
        name: 'Claude Sonnet 4',
        provider: 'anthropic',
        capabilities: {
          tool_call: true,
          reasoning: true,
          structured_output: true,
        },
        cost: { input: 3, output: 15 },
        limit: { context: 200000, output: 16000 },
        modalities: { input: ['text', 'image'], output: ['text'] },
      });
      expect(result[1]?.provider).toBe('openai');
    });

    it('should handle empty data', () => {
      const result = flattenModelsData([]);
      expect(result).toEqual([]);
    });

    it('should use top_provider.context_length when context_length is null', () => {
      const apiResponse = [
        {
          id: 'provider/model-a',
          name: 'Model A',
          context_length: null,
          pricing: { prompt: '0.000001', completion: '0.000005' },
          architecture: { input_modalities: ['text'], output_modalities: ['text'] },
          top_provider: { context_length: 64000, max_completion_tokens: 8000 },
          supported_parameters: ['tools'],
        },
      ];

      const result = flattenModelsData(apiResponse);
      expect(result).toHaveLength(1);
      expect(result[0]?.limit.context).toBe(64000);
    });

    it('should skip models without tools in supported_parameters', () => {
      const apiResponse = [
        {
          id: 'provider/no-tools',
          name: 'No Tools Model',
          context_length: 4096,
          pricing: { prompt: '0.000001', completion: '0.000001' },
          architecture: { input_modalities: ['text'], output_modalities: ['text'] },
          top_provider: { context_length: 4096, max_completion_tokens: 4096 },
          supported_parameters: ['temperature'],
        },
      ];

      const result = flattenModelsData(apiResponse);
      expect(result).toEqual([]);
    });

    it('should convert per-token pricing strings to per-1M numbers', () => {
      const apiResponse = [
        {
          id: 'test/model',
          name: 'Test Model',
          context_length: 100000,
          pricing: { prompt: '0.000003', completion: '0.000015' },
          architecture: { input_modalities: ['text'], output_modalities: ['text'] },
          top_provider: { context_length: 100000, max_completion_tokens: 8000 },
          supported_parameters: ['tools'],
        },
      ];

      const result = flattenModelsData(apiResponse);
      expect(result[0]?.cost.input).toBe(3);
      expect(result[0]?.cost.output).toBe(15);
    });
  });

  describe('getPriceTier', () => {
    it('should return budget for output cost < $1', () => {
      expect(getPriceTier(0.5)).toBe('budget');
      expect(getPriceTier(0.99)).toBe('budget');
    });

    it('should return standard for output cost $1-$10', () => {
      expect(getPriceTier(1)).toBe('standard');
      expect(getPriceTier(5)).toBe('standard');
      expect(getPriceTier(10)).toBe('standard');
    });

    it('should return premium for output cost > $10', () => {
      expect(getPriceTier(10.01)).toBe('premium');
      expect(getPriceTier(75)).toBe('premium');
    });
  });

  describe('filterModelsByRequirements', () => {
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

    it('should filter by required capabilities', () => {
      const requirements: AgentRequirements = {
        capabilities: ['tool_call', 'reasoning'],
        minContext: 0,
        priceTier: 'any',
      };

      const result = filterModelsByRequirements(models, requirements);
      expect(result).toHaveLength(1);
      expect(result[0]?.id).toBe('model-a');
    });

    it('should filter by minimum context size', () => {
      const requirements: AgentRequirements = {
        capabilities: ['tool_call'],
        minContext: 100000,
        priceTier: 'any',
      };

      const result = filterModelsByRequirements(models, requirements);
      expect(result).toHaveLength(1);
      expect(result[0]?.id).toBe('model-a');
    });

    it('should filter by price tier', () => {
      const requirements: AgentRequirements = {
        capabilities: ['tool_call'],
        minContext: 0,
        priceTier: 'budget',
      };

      const result = filterModelsByRequirements(models, requirements);
      expect(result).toHaveLength(1);
      expect(result[0]?.id).toBe('model-b');
    });

    it('should return all matching models when priceTier is any', () => {
      const requirements: AgentRequirements = {
        capabilities: ['tool_call'],
        minContext: 0,
        priceTier: 'any',
      };

      const result = filterModelsByRequirements(models, requirements);
      expect(result).toHaveLength(2);
    });
  });

  describe('formatContextSize', () => {
    it('should format context size in K notation', () => {
      expect(formatContextSize(200000)).toBe('200K');
      expect(formatContextSize(128000)).toBe('128K');
      expect(formatContextSize(8000)).toBe('8K');
    });

    it('should handle context sizes over 1M', () => {
      expect(formatContextSize(1000000)).toBe('1M');
      expect(formatContextSize(2000000)).toBe('2M');
    });
  });
});
