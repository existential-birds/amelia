/**
 * Utility functions for design document import.
 */

/**
 * Extract a title from a markdown H1, stripping a trailing document-type word.
 *
 * @example
 * extractTitle('# Queue Workflows Design\n\n## Problem')
 * // Returns: 'Queue Workflows'
 */
export function extractTitle(markdown: string): string {
  // Match first H1 heading: # Title (strip common document-type suffixes)
  const match = markdown.match(/^#\s+(.+?)(?:\s+(?:Design|Plan|Spec|RFC|Proposal))?\s*$/mi);
  if (!match || !match[1]) {
    return 'Untitled';
  }
  return match[1].trim();
}

/**
 * Extract a title from a filename, stripping the date prefix and extension.
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

/**
 * Build a task description that references a design document under docs/plans/.
 *
 * @example
 * buildDescriptionReference('2026-01-09-queue-workflows-design.md')
 * // Returns: 'Implement the feature described in docs/plans/2026-01-09-queue-workflows-design.md'
 */
export function buildDescriptionReference(filename: string): string {
  return `Implement the feature described in docs/plans/${filename}`;
}
