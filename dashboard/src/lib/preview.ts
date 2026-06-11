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
  if (!rawText) {
    return '';
  }

  const text = rawText.trim();
  if (!text) {
    return '';
  }

  const paragraphSplit = text.split('\n\n');
  if (paragraphSplit.length > 1 && paragraphSplit[0]) {
    const firstParagraph = paragraphSplit[0].trim();
    if (firstParagraph) {
      return firstParagraph;
    }
  }

  const sentences = [];
  const sentenceRegex = /[^.!?]+[.!?]+/g;
  let match;

  while ((match = sentenceRegex.exec(text)) !== null) {
    sentences.push(match[0]);

    if (sentences.length >= 3) {
      break;
    }
  }

  if (sentences.length > 0) {
    const combined = sentences.join('').trim();
    if (combined.length <= maxLength) {
      return combined;
    }
    const truncated = combined.substring(0, maxLength);
    const lastSpace = truncated.lastIndexOf(' ');
    if (lastSpace > 0) {
      return combined.substring(0, lastSpace).trim();
    }
    return truncated.trim();
  }

  if (text.length < 200) {
    return text;
  }

  if (text.length <= maxLength) {
    return text;
  }

  const truncated = text.substring(0, maxLength);
  const lastSpace = truncated.lastIndexOf(' ');

  if (lastSpace > 0) {
    return truncated.substring(0, lastSpace).trim();
  }

  return truncated.trim();
}
