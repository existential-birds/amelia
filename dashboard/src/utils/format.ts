/**
 * @fileoverview Formatting utilities for display values.
 */

/**
 * UUID pattern matching - captures the prefix and UUID parts.
 * Matches patterns like "prefix-12d73bed-8687-49b2-b761-099bb70eaa01"
 * where prefix can contain alphanumeric and hyphens, followed by a standard UUID.
 */
const UUID_PATTERN = /^(.+?)-([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})$/i;

/**
 * Truncates a workflow ID for display while preserving recognizability.
 *
 * For IDs matching the pattern "prefix-uuid", shows:
 * - The prefix (up to maxPrefixLength chars)
 * - First 8 chars of UUID
 * - Ellipsis
 * - Last 3 chars of UUID
 *
 * Example:
 * - Input: "brainstorm-12d73bed-8687-49b2-b761-099bb70eaa01"
 * - Output: "brainstorm-12d73bed...a01"
 *
 * @param id - The workflow ID to truncate
 * @param maxPrefixLength - Maximum length for the prefix part (default 20)
 * @returns Truncated ID string suitable for display
 */
export function truncateWorkflowId(id: string, maxPrefixLength = 20): string {
  // Short IDs don't need truncation
  if (id.length <= 30) {
    return id;
  }

  const match = id.match(UUID_PATTERN);

  if (match) {
    // Extract parts: [full, prefix, uuid1, uuid2, uuid3, uuid4, uuid5]
    const prefix = match[1]!;
    const uuidFirstSegment = match[2]!; // First 8 chars of UUID
    const uuidLastSegment = match[6]!; // Last 12 chars of UUID

    // Truncate prefix if needed (guard against invalid maxPrefixLength)
    const safePrefixLength = Math.max(1, maxPrefixLength);
    const displayPrefix = prefix.length > safePrefixLength
      ? prefix.slice(0, safePrefixLength - 1) + '…'
      : prefix;

    // Last 3 chars of the full UUID
    const lastChars = uuidLastSegment.slice(-3);

    return `${displayPrefix}-${uuidFirstSegment}...${lastChars}`;
  }

  // Fallback for non-UUID patterns: simple truncation with ellipsis
  if (id.length > 30) {
    return id.slice(0, 24) + '...' + id.slice(-3);
  }

  return id;
}
