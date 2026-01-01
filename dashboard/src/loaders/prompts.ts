/**
 * @fileoverview Loader for the prompts page.
 *
 * Fetches all prompts from the API for display in the prompts page.
 */
import { api } from '@/api/client';
import type { PromptSummary } from '@/types';

/**
 * Data returned by the prompts loader.
 */
export interface PromptsLoaderData {
  /** Array of prompt summaries grouped by agent. */
  prompts: PromptSummary[];
}

/**
 * Loader for the prompts page.
 * Fetches all prompts from the API.
 *
 * @returns Object containing the list of prompts.
 * @throws {Error} When the API request fails.
 *
 * @example
 * ```typescript
 * const { prompts } = await promptsLoader();
 * const grouped = groupPromptsByAgent(prompts);
 * ```
 */
export async function promptsLoader(): Promise<PromptsLoaderData> {
  const prompts = await api.getPrompts();
  return { prompts };
}

/**
 * Groups prompts by agent name for display.
 *
 * @param prompts - Array of prompt summaries.
 * @returns Map of agent names to their prompts.
 *
 * @example
 * ```typescript
 * const grouped = groupPromptsByAgent(prompts);
 * // { architect: [prompt1], developer: [prompt2, prompt3], reviewer: [prompt4] }
 * ```
 */
export function groupPromptsByAgent(
  prompts: PromptSummary[]
): Record<string, PromptSummary[]> {
  return prompts.reduce(
    (acc, prompt) => {
      const agent = prompt.agent;
      if (!acc[agent]) {
        acc[agent] = [];
      }
      acc[agent].push(prompt);
      return acc;
    },
    {} as Record<string, PromptSummary[]>
  );
}
