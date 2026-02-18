import type { ModelInfo, AgentRequirements, PriceTier } from '@/components/model-picker/types';
import { PRICE_TIER_THRESHOLDS } from '@/components/model-picker/constants';

/**
 * Model data from OpenRouter /api/v1/models endpoint.
 */
interface OpenRouterModel {
  id: string;
  name: string;
  context_length: number | null;
  pricing: { prompt: string; completion: string };
  architecture: { input_modalities: string[]; output_modalities: string[] };
  top_provider: { context_length: number | null; max_completion_tokens: number | null };
  supported_parameters: string[];
}

/**
 * Flatten the OpenRouter API response into a flat array of ModelInfo.
 * Only includes models with tool support (required for all agents).
 */
export function flattenModelsData(data: OpenRouterModel[]): ModelInfo[] {
  const models: ModelInfo[] = [];

  for (const model of data) {
    // Extract provider from model ID (e.g., "anthropic/claude-sonnet-4" -> "anthropic")
    const slashIndex = model.id.indexOf('/');
    const provider = slashIndex !== -1 ? model.id.substring(0, slashIndex) : 'unknown';

    models.push({
      id: model.id,
      name: model.name,
      provider,
      capabilities: {
        tool_call: true,
        reasoning: model.supported_parameters.includes('reasoning'),
        structured_output: model.supported_parameters.includes('response_format'),
      },
      cost: {
        input: Math.round((parseFloat(model.pricing.prompt) || 0) * 1_000_000),
        output: Math.round((parseFloat(model.pricing.completion) || 0) * 1_000_000),
      },
      limit: {
        context: model.context_length ?? model.top_provider?.context_length ?? null,
        output: model.top_provider?.max_completion_tokens ?? null,
      },
      modalities: {
        input: model.architecture.input_modalities,
        output: model.architecture.output_modalities,
      },
    });
  }

  return models;
}

/**
 * Determine the price tier for a model based on output cost per 1M tokens.
 */
export function getPriceTier(outputCost: number): PriceTier {
  if (outputCost < PRICE_TIER_THRESHOLDS.budget) {
    return 'budget';
  }
  if (outputCost <= PRICE_TIER_THRESHOLDS.standard) {
    return 'standard';
  }
  return 'premium';
}

/**
 * Check if a model's price tier matches the required tier.
 *
 * Tier matching uses inclusive semantics for higher tiers:
 * - 'budget': only budget models (strict cost constraint)
 * - 'standard': budget + standard models (moderate cost constraint)
 * - 'premium': all models (no cost constraint - premium agents can afford anything)
 *
 * This allows agents with higher price tiers to use cheaper models when appropriate,
 * while agents with budget constraints are limited to cost-effective options.
 */
function matchesPriceTier(model: ModelInfo, requiredTier: AgentRequirements['priceTier']): boolean {
  if (requiredTier === 'any') return true;

  const modelTier = getPriceTier(model.cost.output);

  // Budget tier only matches budget models (strict cost constraint)
  if (requiredTier === 'budget') {
    return modelTier === 'budget';
  }

  // Standard tier matches budget and standard (moderate cost constraint)
  if (requiredTier === 'standard') {
    return modelTier === 'budget' || modelTier === 'standard';
  }

  // Premium tier matches all models (no cost constraint)
  return true;
}

/**
 * Filter models by agent requirements.
 */
export function filterModelsByRequirements(
  models: ModelInfo[],
  requirements: AgentRequirements
): ModelInfo[] {
  return models.filter((model) => {
    // Check all required capabilities
    for (const cap of requirements.capabilities) {
      if (!model.capabilities[cap]) {
        return false;
      }
    }

    // Check minimum context size
    if (model.limit.context === null || model.limit.context < requirements.minContext) {
      return false;
    }

    // Check price tier
    if (!matchesPriceTier(model, requirements.priceTier)) {
      return false;
    }

    return true;
  });
}

/**
 * Format context size for display (e.g., 200000 -> "200K").
 */
export function formatContextSize(contextSize: number | null): string {
  if (contextSize === null) {
    return 'Unknown';
  }
  if (contextSize >= 1_000_000) {
    return `${Math.round(contextSize / 1_000_000)}M`;
  }
  return `${Math.round(contextSize / 1000)}K`;
}
