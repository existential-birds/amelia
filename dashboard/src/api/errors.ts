/**
 * Parse FastAPI error detail into a human-readable message.
 * Handles string, Pydantic validation array, and object formats.
 */
export function parseErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e: { msg?: string; loc?: string[] }) => {
        const loc = e.loc?.slice(1).join('.') ?? '';
        return loc ? `${loc}: ${e.msg}` : (e.msg ?? String(e));
      })
      .join('; ');
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail);
  return fallback;
}
