import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { extractTitle, generateDesignId, extractTitleFromFilename } from '../design-doc';

describe('extractTitle', () => {
  it('extracts title from H1 and strips "Design" suffix', () => {
    const markdown = '# Queue Workflows Design\n\n## Problem\n\nUsers cannot queue.';
    expect(extractTitle(markdown)).toBe('Queue Workflows');
  });

  it('extracts title without "Design" suffix when not present', () => {
    const markdown = '# API Authentication\n\n## Overview';
    expect(extractTitle(markdown)).toBe('API Authentication');
  });

  it('preserves "Design" when not at end', () => {
    const markdown = '# Foo Design Bar\n\n## Details';
    expect(extractTitle(markdown)).toBe('Foo Design Bar');
  });

  it('returns "Untitled" when no H1 found', () => {
    const markdown = '## Only H2\n\nNo H1 heading.';
    expect(extractTitle(markdown)).toBe('Untitled');
  });

  it('handles H1 with extra whitespace', () => {
    const markdown = '#   Spaced Title Design   \n\nContent';
    expect(extractTitle(markdown)).toBe('Spaced Title');
  });
});

describe('extractTitleFromFilename', () => {
  it('extracts title from filename with date prefix', () => {
    expect(extractTitleFromFilename('2026-01-09-queue-workflows-design.md'))
      .toBe('queue-workflows-design');
  });

  it('extracts title from filename without date prefix', () => {
    expect(extractTitleFromFilename('queue-workflows-design.md'))
      .toBe('queue-workflows-design');
  });

  it('handles uppercase and mixed case', () => {
    expect(extractTitleFromFilename('2026-01-09-API-Auth-Design.MD'))
      .toBe('API-Auth-Design');
  });
});

describe('generateDesignId', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('generates timestamp-based ID', () => {
    vi.setSystemTime(new Date('2026-01-09T14:30:52.000Z'));
    const id = generateDesignId();
    expect(id).toBe('design-20260109143052');
  });

  it('generates unique IDs at different times', () => {
    vi.setSystemTime(new Date('2026-01-09T14:30:52.000Z'));
    const id1 = generateDesignId();

    vi.setSystemTime(new Date('2026-01-09T14:30:53.000Z'));
    const id2 = generateDesignId();

    expect(id1).not.toBe(id2);
  });
});
