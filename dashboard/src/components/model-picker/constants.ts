// Re-export from lib/constants for backward compatibility
export { AGENT_MODEL_REQUIREMENTS } from '@/lib/constants';

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
 * localStorage key for recently used models.
 */
export const RECENT_MODELS_KEY = 'amelia:recent-models';

/**
 * Maximum number of recent models to track.
 */
export const MAX_RECENT_MODELS = 10;

/**
 * OpenRouter API endpoint for model listing.
 */
export const MODELS_API_URL = 'https://openrouter.ai/api/v1/models?supported_parameters=tools';
