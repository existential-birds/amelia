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
    it('should flatten nested provider/models structure', () => {
      const apiResponse = {
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
        openai: {
          id: 'openai',
          name: 'OpenAI',
          models: {
            'gpt-4o': {
              id: 'gpt-4o',
              name: 'GPT-4o',
              tool_call: true,
              reasoning: false,
              structured_output: true,
              cost: { input: 2.5, output: 10 },
              limit: { context: 128000, output: 16384 },
              modalities: { input: ['text', 'image'], output: ['text'] },
            },
          },
        },
      };

      const result = flattenModelsData(apiResponse);

      expect(result).toHaveLength(2);
      expect(result[0]).toEqual({
        id: 'claude-sonnet-4',
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
      expect(result[1].provider).toBe('openai');
    });

    it('should handle empty providers', () => {
      const result = flattenModelsData({});
      expect(result).toEqual([]);
    });

    it('should skip models without tool_call capability', () => {
      const apiResponse = {
        provider: {
          id: 'provider',
          name: 'Provider',
          models: {
            'no-tools': {
              id: 'no-tools',
              name: 'No Tools Model',
              tool_call: false,
              reasoning: false,
              structured_output: false,
              cost: { input: 1, output: 1 },
              limit: { context: 4096, output: 4096 },
              modalities: { input: ['text'], output: ['text'] },
            },
          },
        },
      };

      const result = flattenModelsData(apiResponse);
      expect(result).toEqual([]);
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
      expect(result[0].id).toBe('model-a');
    });

    it('should filter by minimum context size', () => {
      const requirements: AgentRequirements = {
        capabilities: ['tool_call'],
        minContext: 100000,
        priceTier: 'any',
      };

      const result = filterModelsByRequirements(models, requirements);
      expect(result).toHaveLength(1);
      expect(result[0].id).toBe('model-a');
    });

    it('should filter by price tier', () => {
      const requirements: AgentRequirements = {
        capabilities: ['tool_call'],
        minContext: 0,
        priceTier: 'budget',
      };

      const result = filterModelsByRequirements(models, requirements);
      expect(result).toHaveLength(1);
      expect(result[0].id).toBe('model-b');
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
