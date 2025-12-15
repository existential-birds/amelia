import { describe, it, expect } from 'vitest';
import { formatTime } from '../utils';

describe('formatTime', () => {
  it('formats valid ISO timestamp to HH:MM:SS.mmm', () => {
    expect(formatTime('2025-12-13T10:30:45.123Z')).toBe('10:30:45.123');
  });

  it('returns "-" for invalid timestamp string', () => {
    expect(formatTime('invalid')).toBe('-');
  });

  it('returns "-" for empty string', () => {
    expect(formatTime('')).toBe('-');
  });

  it('returns "-" for malformed date', () => {
    expect(formatTime('not-a-date')).toBe('-');
  });

  it('returns "-" for null', () => {
    expect(formatTime(null)).toBe('-');
  });

  it('returns "-" for undefined', () => {
    expect(formatTime(undefined)).toBe('-');
  });
});
