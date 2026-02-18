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
    context: number | null;
    output: number | null;
  };
  cost: {
    input: number | null;
    output: number | null;
    reasoning?: number | null;
  };
  modalities: {
    input: string[];
    output: string[];
  };
  release_date?: string;
  knowledge?: string;
}

// Re-export from lib/constants for backward compatibility
export type { AgentRequirements } from '@/lib/constants';

/**
 * Price tier classification based on output cost per 1M tokens.
 */
export type PriceTier = 'budget' | 'standard' | 'premium';
