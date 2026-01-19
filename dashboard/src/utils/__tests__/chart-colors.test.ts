import { describe, it, expect } from 'vitest';
import { getModelColor, MODEL_COLORS } from '../chart-colors';

describe('chart-colors', () => {
  describe('MODEL_COLORS', () => {
    it('should have 6 colors defined', () => {
      expect(MODEL_COLORS).toHaveLength(6);
    });

    it('should use CSS variables', () => {
      expect(MODEL_COLORS[0]).toBe('var(--chart-model-1)');
      expect(MODEL_COLORS[5]).toBe('var(--chart-model-6)');
    });
  });

  describe('getModelColor', () => {
    it('should return first color for rank 0', () => {
      expect(getModelColor(0)).toBe('var(--chart-model-1)');
    });

    it('should return second color for rank 1', () => {
      expect(getModelColor(1)).toBe('var(--chart-model-2)');
    });

    it('should cycle colors for rank >= 6', () => {
      expect(getModelColor(6)).toBe('var(--chart-model-1)');
      expect(getModelColor(7)).toBe('var(--chart-model-2)');
    });
  });
});
