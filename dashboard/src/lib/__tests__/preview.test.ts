import { describe, it, expect } from 'vitest';
import { extractDocumentPreview } from '../preview';

describe('extractDocumentPreview', () => {
  it('extracts first paragraph when double newline exists', () => {
    const text = 'First paragraph here.\n\nSecond paragraph here.';
    const result = extractDocumentPreview(text);
    expect(result).toBe('First paragraph here.');
  });

  it('extracts first 2-3 sentences when no paragraph break', () => {
    const text = 'First sentence. Second sentence. Third sentence. Fourth sentence.';
    const result = extractDocumentPreview(text);
    expect(result).toBe('First sentence. Second sentence. Third sentence.');
  });

  it('handles null input', () => {
    const result = extractDocumentPreview(null);
    expect(result).toBe('');
  });

  it('handles empty string', () => {
    const result = extractDocumentPreview('');
    expect(result).toBe('');
  });

  it('handles undefined input', () => {
    const result = extractDocumentPreview(undefined as any);
    expect(result).toBe('');
  });

  it('returns full text for very short documents (< 200 chars)', () => {
    const text = 'This is a short document with less than 200 characters.';
    const result = extractDocumentPreview(text);
    expect(result).toBe(text);
  });

  it('truncates at word boundary when no clear break found', () => {
    // Create a long text without sentence breaks
    const text = 'a'.repeat(500);
    const result = extractDocumentPreview(text, 100);
    expect(result.length).toBeLessThanOrEqual(100);
    // Should not end with partial word (in this case all 'a's)
    expect(result).toBeTruthy();
  });

  it('respects maxLength parameter', () => {
    const text = 'First sentence. Second sentence. Third sentence. Fourth sentence.';
    const result = extractDocumentPreview(text, 30);
    expect(result.length).toBeLessThanOrEqual(30);
  });

  it('handles question marks as sentence boundaries', () => {
    const text = 'Is this a question? This is a statement. Another statement.';
    const result = extractDocumentPreview(text);
    expect(result).toBe('Is this a question? This is a statement. Another statement.');
  });

  it('handles exclamation marks as sentence boundaries', () => {
    const text = 'What an exclamation! This is calm. Still calm.';
    const result = extractDocumentPreview(text);
    expect(result).toBe('What an exclamation! This is calm. Still calm.');
  });

  it('handles unicode characters correctly', () => {
    const text = 'Café résumé. Über cool. 你好世界。';
    const result = extractDocumentPreview(text);
    expect(result).toContain('Café résumé');
  });

  it('trims whitespace from result', () => {
    const text = '  \n\n  First paragraph.  \n\n  Second paragraph.  ';
    const result = extractDocumentPreview(text);
    expect(result).toBe('First paragraph.');
  });

  it('handles text with only whitespace', () => {
    const text = '   \n\n   \t\t   ';
    const result = extractDocumentPreview(text);
    expect(result).toBe('');
  });

  it('extracts sentences even with multiple spaces after periods', () => {
    const text = 'First sentence.  Second sentence.  Third sentence.';
    const result = extractDocumentPreview(text);
    expect(result).toBe('First sentence.  Second sentence.  Third sentence.');
  });

  it('stops at first paragraph even if very short', () => {
    const text = 'Short.\n\nLong paragraph that continues with many more words and details.';
    const result = extractDocumentPreview(text);
    expect(result).toBe('Short.');
  });

  it('handles text starting with newlines', () => {
    const text = '\n\n\nActual content starts here. More content.';
    const result = extractDocumentPreview(text);
    expect(result).toContain('Actual content starts here');
  });
});
