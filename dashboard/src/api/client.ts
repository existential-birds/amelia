import type {
  WorkflowSummary,
  WorkflowStatus,
  WorkflowDetailResponse,
  WorkflowListResponse,
  ErrorResponse,
} from '../types';

/**
 * Base URL for all API requests.
 *
 * Defaults to '/api' if VITE_API_BASE_URL environment variable is not set.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Custom error class for API-related errors.
 *
 * Extends the standard Error class to include additional context about API failures,
 * including error codes, HTTP status codes, and optional error details.
 *
 * @example
 * ```typescript
 * throw new ApiError('Resource not found', 'NOT_FOUND', 404);
 * ```
 */
class ApiError extends Error {
  /**
   * Creates a new ApiError instance.
   *
   * @param message - Human-readable error message.
   * @param code - Machine-readable error code (e.g., 'NOT_FOUND', 'VALIDATION_ERROR').
   * @param status - HTTP status code associated with the error.
   * @param details - Optional additional error details or metadata.
   */
  constructor(
    message: string,
    public code: string,
    public status: number,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Handles HTTP response parsing and error handling.
 *
 * Checks if the response is successful, parses the JSON body, and throws
 * ApiError if the response indicates an error. Attempts to parse error
 * details from the response body when available.
 *
 * @param response - The fetch Response object to handle.
 * @returns The parsed JSON response body.
 * @throws {ApiError} When the response status is not OK (non-2xx status code).
 *
 * @example
 * ```typescript
 * const response = await fetch('/api/workflows');
 * const data = await handleResponse<WorkflowListResponse>(response);
 * ```
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: ErrorResponse;
    try {
      errorData = await response.json();
    } catch {
      throw new ApiError(
        `HTTP ${response.status}: ${response.statusText}`,
        'HTTP_ERROR',
        response.status
      );
    }

    throw new ApiError(
      errorData.error,
      errorData.code,
      response.status,
      errorData.details
    );
  }

  return response.json();
}

/**
 * API client for interacting with the Amelia workflow management backend.
 *
 * Provides methods for fetching, approving, rejecting, and canceling workflows,
 * as well as retrieving workflow history.
 */
export const api = {
  /**
   * Retrieves all active workflows.
   *
   * Active workflows are those with status 'in_progress' or 'blocked'.
   *
   * @returns Array of workflow summaries for all active workflows.
   * @throws {ApiError} When the API request fails.
   *
   * @example
   * ```typescript
   * const workflows = await api.getWorkflows();
   * console.log(`Found ${workflows.length} active workflows`);
   * ```
   */
  async getWorkflows(): Promise<WorkflowSummary[]> {
    const response = await fetch(`${API_BASE_URL}/workflows/active`);
    const data = await handleResponse<WorkflowListResponse>(response);
    return data.workflows;
  },

  /**
   * Retrieves a single workflow by ID with full details.
   *
   * Returns comprehensive workflow information including state, events,
   * and execution details.
   *
   * @param id - The unique identifier of the workflow to retrieve.
   * @returns Detailed workflow information including full execution state.
   * @throws {ApiError} When the workflow is not found or the API request fails.
   *
   * @example
   * ```typescript
   * const workflow = await api.getWorkflow('workflow-123');
   * console.log(`Workflow status: ${workflow.status}`);
   * ```
   */
  async getWorkflow(id: string): Promise<WorkflowDetailResponse> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}`);
    return handleResponse<WorkflowDetailResponse>(response);
  },

  /**
   * Approves a blocked workflow's plan.
   *
   * Approving a workflow allows it to proceed with execution after
   * human review of the proposed plan.
   *
   * @param id - The unique identifier of the workflow to approve.
   * @returns Promise that resolves when the approval is successful.
   * @throws {ApiError} When the workflow is not found, not in a blocked state, or the API request fails.
   *
   * @example
   * ```typescript
   * await api.approveWorkflow('workflow-123');
   * console.log('Workflow approved and will resume execution');
   * ```
   */
  async approveWorkflow(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    await handleResponse(response);
  },

  /**
   * Rejects a workflow's plan with feedback.
   *
   * Rejecting a workflow sends it back for re-planning with the provided
   * feedback to guide improvements.
   *
   * @param id - The unique identifier of the workflow to reject.
   * @param feedback - Human feedback explaining why the plan was rejected and what should be changed.
   * @returns Promise that resolves when the rejection is successful.
   * @throws {ApiError} When the workflow is not found, not in a blocked state, or the API request fails.
   *
   * @example
   * ```typescript
   * await api.rejectWorkflow('workflow-123', 'Please add more unit tests to the plan');
   * console.log('Workflow rejected and sent back for re-planning');
   * ```
   */
  async rejectWorkflow(id: string, feedback: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback }),
    });
    await handleResponse(response);
  },

  /**
   * Cancels a running workflow.
   *
   * Canceling immediately stops workflow execution and transitions it
   * to the 'cancelled' state.
   *
   * @param id - The unique identifier of the workflow to cancel.
   * @returns Promise that resolves when the cancellation is successful.
   * @throws {ApiError} When the workflow is not found, not in a cancellable state, or the API request fails.
   *
   * @example
   * ```typescript
   * await api.cancelWorkflow('workflow-123');
   * console.log('Workflow cancelled successfully');
   * ```
   */
  async cancelWorkflow(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    await handleResponse(response);
  },

  /**
   * Retrieves workflow history for completed, failed, and cancelled workflows.
   *
   * Makes parallel requests for each status type (completed, failed, cancelled)
   * since the server only supports single status filtering. Results are combined
   * and sorted by start time in descending order (most recent first).
   *
   * @returns Array of workflow summaries sorted by start time (newest first).
   * @throws {ApiError} When any of the API requests fail.
   *
   * @example
   * ```typescript
   * const history = await api.getWorkflowHistory();
   * console.log(`Found ${history.length} historical workflows`);
   * history.forEach(w => console.log(`${w.id}: ${w.status}`));
   * ```
   */
  async getWorkflowHistory(): Promise<WorkflowSummary[]> {
    const statuses: WorkflowStatus[] = ['completed', 'failed', 'cancelled'];
    const results = await Promise.all(
      statuses.map(async (status) => {
        const response = await fetch(`${API_BASE_URL}/workflows?status=${status}`);
        const data = await handleResponse<WorkflowListResponse>(response);
        return data.workflows;
      })
    );
    // Flatten and sort by started_at descending (most recent first)
    return results
      .flat()
      .sort((a, b) => {
        const aTime = a.started_at ? new Date(a.started_at).getTime() : 0;
        const bTime = b.started_at ? new Date(b.started_at).getTime() : 0;
        return bTime - aTime;
      });
  },
};

export { ApiError };
