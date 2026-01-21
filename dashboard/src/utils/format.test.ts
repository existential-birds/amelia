/**
 * @fileoverview Tests for format utility functions.
 */
import { describe, it, expect } from 'vitest';
import { truncateWorkflowId } from './format';

describe('truncateWorkflowId', () => {
  describe('standard prefix-UUID patterns', () => {
    it('truncates a typical workflow ID correctly', () => {
      const input = 'brainstorm-12d73bed-8687-49b2-b761-099bb70eaa01';
      const result = truncateWorkflowId(input);
      expect(result).toBe('brainstorm-12d73bed...a01');
    });

    it('truncates a different prefix correctly', () => {
      const input = 'feature-abc12345-1234-5678-9abc-def012345678';
      const result = truncateWorkflowId(input);
      expect(result).toBe('feature-abc12345...678');
    });

    it('handles uppercase UUID correctly', () => {
      const input = 'TASK-12D73BED-8687-49B2-B761-099BB70EAA01';
      const result = truncateWorkflowId(input);
      expect(result).toBe('TASK-12D73BED...A01');
    });

    it('handles mixed case UUID correctly', () => {
      const input = 'task-12d73BED-8687-49b2-B761-099bb70eaa01';
      const result = truncateWorkflowId(input);
      expect(result).toBe('task-12d73BED...a01');
    });
  });

  describe('long prefixes', () => {
    it('truncates long prefixes to maxPrefixLength', () => {
      const input = 'very-long-prefix-name-here-12d73bed-8687-49b2-b761-099bb70eaa01';
      const result = truncateWorkflowId(input, 20);
      expect(result).toBe('very-long-prefix-na…-12d73bed...a01');
    });

    it('respects custom maxPrefixLength', () => {
      const input = 'long-prefix-12d73bed-8687-49b2-b761-099bb70eaa01';
      const result = truncateWorkflowId(input, 10);
      expect(result).toBe('long-pref…-12d73bed...a01');
    });

    it('does not truncate prefix within maxPrefixLength', () => {
      const input = 'short-12d73bed-8687-49b2-b761-099bb70eaa01';
      const result = truncateWorkflowId(input, 20);
      expect(result).toBe('short-12d73bed...a01');
    });
  });

  describe('short IDs', () => {
    it('returns short IDs unchanged', () => {
      const input = 'ISSUE-123';
      const result = truncateWorkflowId(input);
      expect(result).toBe('ISSUE-123');
    });

    it('returns IDs at threshold length unchanged', () => {
      const input = '123456789012345678901234567890'; // exactly 30 chars
      const result = truncateWorkflowId(input);
      expect(result).toBe('123456789012345678901234567890');
    });

    it('returns simple UUIDs unchanged if under threshold', () => {
      const input = 'abc-123';
      const result = truncateWorkflowId(input);
      expect(result).toBe('abc-123');
    });
  });

  describe('non-UUID patterns', () => {
    it('applies simple truncation to long non-UUID strings', () => {
      const input = 'this-is-a-very-long-string-without-uuid-pattern-at-all';
      const result = truncateWorkflowId(input);
      expect(result).toBe('this-is-a-very-long-stri...all');
    });

    it('handles strings just over threshold', () => {
      const input = '1234567890123456789012345678901'; // 31 chars
      const result = truncateWorkflowId(input);
      expect(result).toBe('123456789012345678901234...901');
    });
  });

  describe('edge cases', () => {
    it('handles empty string', () => {
      const result = truncateWorkflowId('');
      expect(result).toBe('');
    });

    it('handles single character', () => {
      const result = truncateWorkflowId('a');
      expect(result).toBe('a');
    });

    it('handles hyphen-only prefix', () => {
      const input = '---12d73bed-8687-49b2-b761-099bb70eaa01';
      const result = truncateWorkflowId(input);
      expect(result).toBe('---12d73bed...a01');
    });

    it('handles numeric prefix', () => {
      const input = '12345-12d73bed-8687-49b2-b761-099bb70eaa01';
      const result = truncateWorkflowId(input);
      expect(result).toBe('12345-12d73bed...a01');
    });
  });
});
