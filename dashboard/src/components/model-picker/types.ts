/**
 * Model information from models.dev API.
 */
export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  capabilities: {
    tool_call: boolean;
    reasoning: boolean;
    structured_output: boolean;
  };
  limit: {
    context: number;
    output: number;
  };
  cost: {
    input: number;
    output: number;
    reasoning?: number;
  };
  modalities: {
    input: string[];
    output: string[];
  };
  release_date?: string;
  knowledge?: string;
}

/**
 * Agent capability requirements for model filtering.
 */
export interface AgentRequirements {
  capabilities: ('tool_call' | 'reasoning' | 'structured_output')[];
  minContext: number;
  priceTier: 'budget' | 'standard' | 'premium' | 'any';
}

/**
 * Price tier classification based on output cost per 1M tokens.
 */
export type PriceTier = 'budget' | 'standard' | 'premium';
