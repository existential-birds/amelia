/**
 * @fileoverview Chart color utilities for multi-model visualization.
 */

/**
 * Ordered color palette for multi-model charts.
 * Models are sorted by cost descending, highest cost gets first color.
 */
export const MODEL_COLORS = [
  'var(--chart-model-1)',
  'var(--chart-model-2)',
  'var(--chart-model-3)',
  'var(--chart-model-4)',
  'var(--chart-model-5)',
  'var(--chart-model-6)',
] as const;

/**
 * Get color for a model based on its cost rank.
 * Colors cycle if more than 6 models.
 *
 * @param rankIndex - Zero-based rank (0 = highest cost)
 * @returns CSS variable reference for the color
 */
export function getModelColor(rankIndex: number): string {
  const index = rankIndex % MODEL_COLORS.length;
  return MODEL_COLORS[index] ?? MODEL_COLORS[0];
}

/**
 * OKLCH color constants for PR fix outcome categories.
 * Used in chart configs and Bar component fills.
 */
export const PR_FIX_COLORS = {
  fixed: 'oklch(0.723 0.191 149.579)',
  failed: 'oklch(0.637 0.237 25.331)',
  skipped: 'oklch(0.795 0.184 86.047)',
} as const;
