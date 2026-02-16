/**
 * Extracts a preview from document text.
 *
 * Priority order:
 * 1. For text < 200 chars: return full text (trimmed)
 * 2. First paragraph (text before double newline)
 * 3. First 2-3 sentences (up to 300 chars by default)
 * 4. Truncate at word boundary if no clear break
 *
 * @param rawText - The raw document text to extract preview from
 * @param maxLength - Maximum length of preview (default: 300)
 * @returns Extracted preview text, trimmed
 */
export function extractDocumentPreview(
  rawText: string | null | undefined,
  maxLength: number = 300
): string {
  // Handle null/undefined/empty
  if (!rawText) {
    return '';
  }

  // Trim leading/trailing whitespace
  const text = rawText.trim();
  if (!text) {
    return '';
  }

  // Try to extract first paragraph (text before double newline)
  const paragraphSplit = text.split('\n\n');
  if (paragraphSplit.length > 1 && paragraphSplit[0]) {
    const firstParagraph = paragraphSplit[0].trim();
    if (firstParagraph) {
      return firstParagraph;
    }
  }

  // Try to extract first 2-3 sentences
  // Match sentences ending with . ? ! followed by space or end of string
  const sentences = [];
  const sentenceRegex = /[^.!?]+[.!?]+/g;
  let match;

  while ((match = sentenceRegex.exec(text)) !== null) {
    sentences.push(match[0]);

    // Stop after exactly 3 sentences
    if (sentences.length >= 3) {
      break;
    }
  }

  if (sentences.length > 0) {
    const combined = sentences.join('').trim();
    // If we have exactly what we need (2-3 sentences under maxLength), return it
    if (combined.length <= maxLength) {
      return combined;
    }
    // If combined sentences exceed maxLength, truncate at word boundary
    const truncated = combined.substring(0, maxLength);
    const lastSpace = truncated.lastIndexOf(' ');
    if (lastSpace > 0) {
      return combined.substring(0, lastSpace).trim();
    }
    return truncated.trim();
  }

  // For very short documents (< 200 chars) without sentence breaks, return full text
  if (text.length < 200) {
    return text;
  }

  // Fallback: truncate at word boundary
  if (text.length <= maxLength) {
    return text;
  }

  // Find last space before maxLength
  const truncated = text.substring(0, maxLength);
  const lastSpace = truncated.lastIndexOf(' ');

  if (lastSpace > 0) {
    return truncated.substring(0, lastSpace).trim();
  }

  // No space found, return truncated text
  return truncated.trim();
}
