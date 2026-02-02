import type { ModelInfo, AgentRequirements, PriceTier } from '@/components/model-picker/types';
import { PRICE_TIER_THRESHOLDS } from '@/components/model-picker/constants';

/**
 * Raw model data from models.dev API.
 */
interface RawModelData {
  id: string;
  name: string;
  tool_call: boolean;
  reasoning: boolean;
  structured_output: boolean;
  cost: { input: number; output: number; reasoning?: number };
  limit: { context: number; output: number };
  modalities: { input: string[]; output: string[] };
  release_date?: string;
  knowledge?: string;
}

/**
 * Provider data from models.dev API.
 */
interface ProviderData {
  id: string;
  name: string;
  models: Record<string, RawModelData>;
}

/**
 * Flatten the nested models.dev API response into a flat array of ModelInfo.
 * Only includes models with tool_call capability (required for all agents).
 */
export function flattenModelsData(
  data: Record<string, ProviderData>
): ModelInfo[] {
  const models: ModelInfo[] = [];

  for (const [providerId, provider] of Object.entries(data)) {
    if (!provider.models) continue;

    for (const rawModel of Object.values(provider.models)) {
      // Skip models without tool_call - all agents require it
      if (!rawModel.tool_call) continue;

      // Skip models with missing required fields
      if (!rawModel.cost || !rawModel.limit) continue;

      models.push({
        id: rawModel.id,
        name: rawModel.name,
        provider: providerId,
        capabilities: {
          tool_call: rawModel.tool_call,
          reasoning: rawModel.reasoning,
          structured_output: rawModel.structured_output,
        },
        cost: rawModel.cost,
        limit: rawModel.limit,
        modalities: rawModel.modalities,
        release_date: rawModel.release_date,
        knowledge: rawModel.knowledge,
      });
    }
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
 */
function matchesPriceTier(model: ModelInfo, requiredTier: AgentRequirements['priceTier']): boolean {
  if (requiredTier === 'any') return true;

  const modelTier = getPriceTier(model.cost.output);

  // Budget tier only matches budget models
  if (requiredTier === 'budget') {
    return modelTier === 'budget';
  }

  // Standard tier matches budget and standard
  if (requiredTier === 'standard') {
    return modelTier === 'budget' || modelTier === 'standard';
  }

  // Premium tier matches all
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
    if (model.limit.context < requirements.minContext) {
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
export function formatContextSize(contextSize: number): string {
  if (contextSize >= 1_000_000) {
    return `${Math.round(contextSize / 1_000_000)}M`;
  }
  return `${Math.round(contextSize / 1000)}K`;
}
