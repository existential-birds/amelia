/**
 * Shared API types used across multiple domains.
 */

/**
 * Standard error response format for all API endpoints.
 * Returned with appropriate HTTP error status codes (4xx, 5xx).
 *
 * @example
 * ```typescript
 * const error: ErrorResponse = {
 *   error: 'Workflow not found',
 *   code: 'WORKFLOW_NOT_FOUND',
 *   details: { workflow_id: 'wf123' }
 * };
 * ```
 */
export interface ErrorResponse {
  /** Human-readable error message. */
  error: string;

  /** Machine-readable error code for programmatic handling. */
  code: string;

  /** Optional additional context about the error. */
  details?: Record<string, unknown>;
}
