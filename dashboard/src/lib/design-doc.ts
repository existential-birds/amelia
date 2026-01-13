/**
 * Utility functions for design document import.
 */

/**
 * Extract title from markdown H1 heading.
 * Strips "Design" suffix from the title.
 *
 * @param markdown - Markdown content to parse.
 * @returns Extracted title, or "Untitled" if no H1 found.
 *
 * @example
 * extractTitle('# Queue Workflows Design\n\n## Problem')
 * // Returns: 'Queue Workflows'
 */
export function extractTitle(markdown: string): string {
  // Match first H1 heading: # Title
  const match = markdown.match(/^#\s+(.+?)(?:\s+Design)?\s*$/m);
  if (!match) {
    return 'Untitled';
  }
  return match[1].trim();
}

/**
 * Extract title from filename, stripping date prefix and extension.
 *
 * @param filename - Filename to parse (e.g., '2026-01-09-queue-workflows-design.md').
 * @returns Title portion of filename.
 *
 * @example
 * extractTitleFromFilename('2026-01-09-queue-workflows-design.md')
 * // Returns: 'queue-workflows-design'
 */
export function extractTitleFromFilename(filename: string): string {
  // Remove extension
  const withoutExt = filename.replace(/\.[^.]+$/, '');
  // Remove date prefix (YYYY-MM-DD-)
  const withoutDate = withoutExt.replace(/^\d{4}-\d{2}-\d{2}-/, '');
  return withoutDate;
}

/**
 * Generate a timestamp-based design document ID.
 *
 * @returns ID in format 'design-YYYYMMDDHHmmss'.
 *
 * @example
 * generateDesignId()
 * // Returns: 'design-20260109143052'
 */
export function generateDesignId(): string {
  const now = new Date();
  const year = now.getUTCFullYear();
  const month = String(now.getUTCMonth() + 1).padStart(2, '0');
  const day = String(now.getUTCDate()).padStart(2, '0');
  const hours = String(now.getUTCHours()).padStart(2, '0');
  const minutes = String(now.getUTCMinutes()).padStart(2, '0');
  const seconds = String(now.getUTCSeconds()).padStart(2, '0');

  return `design-${year}${month}${day}${hours}${minutes}${seconds}`;
}
