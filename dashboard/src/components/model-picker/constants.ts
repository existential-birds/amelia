import type { AgentRequirements } from './types';

/**
 * Price tier thresholds based on output cost per 1M tokens.
 * - Budget: < $1
 * - Standard: $1 - $10
 * - Premium: > $10
 */
export const PRICE_TIER_THRESHOLDS = {
  budget: 1,
  standard: 10,
} as const;

/**
 * Agent-specific model requirements.
 * All agents require tool_call. Secondary capabilities vary.
 */
export const AGENT_MODEL_REQUIREMENTS: Record<string, AgentRequirements> = {
  architect: {
    capabilities: ['tool_call', 'reasoning', 'structured_output'],
    minContext: 200_000,
    priceTier: 'any',
  },
  developer: {
    capabilities: ['tool_call', 'structured_output'],
    minContext: 200_000,
    priceTier: 'any',
  },
  reviewer: {
    capabilities: ['tool_call', 'reasoning'],
    minContext: 128_000,
    priceTier: 'any',
  },
  plan_validator: {
    capabilities: ['tool_call', 'structured_output'],
    minContext: 64_000,
    priceTier: 'budget',
  },
  task_reviewer: {
    capabilities: ['tool_call', 'reasoning'],
    minContext: 64_000,
    priceTier: 'budget',
  },
  evaluator: {
    capabilities: ['tool_call', 'structured_output'],
    minContext: 64_000,
    priceTier: 'budget',
  },
  brainstormer: {
    capabilities: ['tool_call', 'reasoning'],
    minContext: 64_000,
    priceTier: 'standard',
  },
};

/**
 * localStorage key for recently used models.
 */
export const RECENT_MODELS_KEY = 'amelia:recent-models';

/**
 * Maximum number of recent models to track.
 */
export const MAX_RECENT_MODELS = 10;

/**
 * models.dev API endpoint.
 */
export const MODELS_API_URL = 'https://models.dev/api.json';
