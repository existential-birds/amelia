/**
 * Captures the prefix and UUID parts of IDs like
 * "prefix-12d73bed-8687-49b2-b761-099bb70eaa01", where the prefix may itself
 * contain hyphens, followed by a standard UUID.
 */
const UUID_PATTERN = /^(.+?)-([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})$/i;

/**
 * Truncates a workflow ID for display while keeping it recognizable, e.g.
 * "brainstorm-12d73bed-8687-49b2-b761-099bb70eaa01" -> "brainstorm-12d73bed...a01".
 */
export function truncateWorkflowId(id: string, maxPrefixLength = 20): string {
  if (id.length <= 30) {
    return id;
  }

  const match = id.match(UUID_PATTERN);

  if (match) {
    const prefix = match[1]!;
    const uuidFirstSegment = match[2]!; // First 8 chars of UUID
    const uuidLastSegment = match[6]!; // Last 12 chars of UUID

    // Truncate prefix if needed (guard against invalid maxPrefixLength)
    const safePrefixLength = Math.max(1, maxPrefixLength);
    const displayPrefix = prefix.length > safePrefixLength
      ? prefix.slice(0, safePrefixLength - 1) + '…'
      : prefix;

    const lastChars = uuidLastSegment.slice(-3);

    return `${displayPrefix}-${uuidFirstSegment}...${lastChars}`;
  }

  // Fallback for non-UUID patterns: simple truncation with ellipsis
  if (id.length > 30) {
    return id.slice(0, 24) + '...' + id.slice(-3);
  }

  return id;
}
