import type {
  WorkflowSummary,
  WorkflowStatus,
  WorkflowDetailResponse,
  WorkflowListResponse,
  ErrorResponse,
  PromptSummary,
  PromptDetail,
  VersionSummary,
  VersionDetail,
  DefaultContent,
  CreateWorkflowRequest,
  CreateWorkflowResponse,
  StartWorkflowResponse,
  BatchStartRequest,
  BatchStartResponse,
} from '../types';

/**
 * Base URL for all API requests.
 *
 * Defaults to '/api' if VITE_API_BASE_URL environment variable is not set.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Default timeout for API requests in milliseconds (30 seconds).
 */
const DEFAULT_TIMEOUT_MS = 30000;

/**
 * Creates an AbortSignal that triggers after the specified timeout.
 *
 * @param timeoutMs - Timeout duration in milliseconds.
 * @returns An AbortSignal that will abort after the timeout.
 */
function createTimeoutSignal(timeoutMs: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}

/**
 * Wraps fetch with timeout support.
 *
 * @param url - The URL to fetch.
 * @param options - Fetch options (method, headers, body, etc.).
 * @returns The fetch Response.
 * @throws {ApiError} When the request times out or fails.
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const signal = createTimeoutSignal();

  try {
    return await fetch(url, { ...options, signal });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new ApiError('Request timeout', 'TIMEOUT', 408);
    }
    throw error;
  }
}

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
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/active`);
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
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}`);
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
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}/approve`, {
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
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}/reject`, {
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
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}/cancel`, {
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
        const response = await fetchWithTimeout(`${API_BASE_URL}/workflows?status=${status}`);
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

  /**
   * Creates a new workflow via Quick Shot.
   *
   * @param request - The workflow creation request.
   * @returns The created workflow response.
   * @throws {ApiError} When validation fails, worktree is in use, or API request fails.
   *
   * @example
   * ```typescript
   * const response = await api.createWorkflow({
   *   issue_id: 'TASK-001',
   *   worktree_path: '/Users/me/projects/repo',
   *   task_title: 'Add logout button',
   * });
   * console.log(`Created workflow: ${response.id}`);
   * ```
   */
  async createWorkflow(
    request: CreateWorkflowRequest
  ): Promise<CreateWorkflowResponse> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return handleResponse<CreateWorkflowResponse>(response);
  },

  /**
   * Starts a pending workflow.
   *
   * Transitions the workflow from 'pending' to 'in_progress' status
   * and begins execution.
   *
   * @param id - The unique identifier of the workflow to start.
   * @returns The started workflow response with workflow_id and status.
   * @throws {ApiError} When the workflow is not found, not in pending state, or the API request fails.
   *
   * @example
   * ```typescript
   * const result = await api.startWorkflow('workflow-123');
   * console.log(`Started workflow: ${result.workflow_id}, status: ${result.status}`);
   * ```
   */
  async startWorkflow(id: string): Promise<StartWorkflowResponse> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<StartWorkflowResponse>(response);
  },

  /**
   * Starts multiple pending workflows in batch.
   *
   * Allows starting all pending workflows, or filtering by specific IDs
   * or worktree path. Returns both successfully started workflows and
   * any errors that occurred.
   *
   * @param request - The batch start request with optional filters.
   * @returns Response with lists of started workflow IDs and any errors.
   * @throws {ApiError} When the API request fails.
   *
   * @example
   * ```typescript
   * // Start specific workflows
   * const result = await api.startBatch({ workflow_ids: ['wf-1', 'wf-2'] });
   *
   * // Start all pending for a worktree
   * const result = await api.startBatch({ worktree_path: '/path/to/repo' });
   *
   * console.log(`Started: ${result.started.length}, Errors: ${Object.keys(result.errors).length}`);
   * ```
   */
  async startBatch(request: BatchStartRequest): Promise<BatchStartResponse> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/start-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return handleResponse<BatchStartResponse>(response);
  },

  /**
   * Retrieves the most recent workflow defaults for Quick Shot pre-population.
   *
   * Fetches the most recent workflow (by started_at) and returns its
   * worktree_path and profile for use as form defaults.
   *
   * @returns Object with worktree_path and profile, or null values if no workflows exist.
   * @throws {ApiError} When the API request fails.
   *
   * @example
   * ```typescript
   * const defaults = await api.getWorkflowDefaults();
   * console.log(`Default path: ${defaults.worktree_path}`);
   * ```
   */
  async getWorkflowDefaults(): Promise<{
    worktree_path: string | null;
    profile: string | null;
  }> {
    // Fetch most recent workflow (limit=1, sorted by started_at desc)
    const response = await fetchWithTimeout(`${API_BASE_URL}/workflows?limit=1`);
    const data = await handleResponse<WorkflowListResponse>(response);

    const mostRecent = data.workflows[0];
    if (mostRecent) {
      return {
        worktree_path: mostRecent.worktree_path,
        profile: mostRecent.profile,
      };
    }

    return { worktree_path: null, profile: null };
  },

  // ==========================================================================
  // Prompts API
  // ==========================================================================

  /**
   * Get all prompts with current version info.
   *
   * @returns Array of prompt summaries.
   * @throws {ApiError} When the API request fails.
   *
   * @example
   * ```typescript
   * const prompts = await api.getPrompts();
   * console.log(`Found ${prompts.length} prompts`);
   * ```
   */
  async getPrompts(): Promise<PromptSummary[]> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/prompts`);
    const data = await handleResponse<{ prompts: PromptSummary[] }>(response);
    return data.prompts;
  },

  /**
   * Get prompt detail with version history.
   *
   * @param id - The unique identifier of the prompt.
   * @returns Detailed prompt information including version history.
   * @throws {ApiError} When the prompt is not found or the API request fails.
   *
   * @example
   * ```typescript
   * const prompt = await api.getPrompt('architect.system');
   * console.log(`Prompt has ${prompt.versions.length} versions`);
   * ```
   */
  async getPrompt(id: string): Promise<PromptDetail> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${id}`);
    return handleResponse<PromptDetail>(response);
  },

  /**
   * Get all versions for a prompt.
   *
   * @param promptId - The unique identifier of the prompt.
   * @returns Array of version summaries.
   * @throws {ApiError} When the prompt is not found or the API request fails.
   *
   * @example
   * ```typescript
   * const versions = await api.getPromptVersions('architect.system');
   * versions.forEach(v => console.log(`v${v.version_number}: ${v.change_note}`));
   * ```
   */
  async getPromptVersions(promptId: string): Promise<VersionSummary[]> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${promptId}/versions`);
    const data = await handleResponse<{ versions: VersionSummary[] }>(response);
    return data.versions;
  },

  /**
   * Get a specific version with full content.
   *
   * @param promptId - The unique identifier of the prompt.
   * @param versionId - The unique identifier of the version.
   * @returns The version details including content.
   * @throws {ApiError} When the version is not found or the API request fails.
   *
   * @example
   * ```typescript
   * const version = await api.getPromptVersion('architect.system', 'version-uuid');
   * console.log(`Content: ${version.content}`);
   * ```
   */
  async getPromptVersion(
    promptId: string,
    versionId: string
  ): Promise<VersionDetail> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/prompts/${promptId}/versions/${versionId}`
    );
    return handleResponse<VersionDetail>(response);
  },

  /**
   * Create a new version (becomes active immediately).
   *
   * @param promptId - The unique identifier of the prompt.
   * @param content - The new prompt content.
   * @param changeNote - Optional note describing the changes.
   * @returns The created version details.
   * @throws {ApiError} When the prompt is not found or the API request fails.
   *
   * @example
   * ```typescript
   * const version = await api.createPromptVersion(
   *   'architect.system',
   *   'New prompt content...',
   *   'Updated to include security considerations'
   * );
   * console.log(`Created version ${version.version_number}`);
   * ```
   */
  async createPromptVersion(
    promptId: string,
    content: string,
    changeNote: string | null
  ): Promise<VersionDetail> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${promptId}/versions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, change_note: changeNote }),
    });
    return handleResponse<VersionDetail>(response);
  },

  /**
   * Reset prompt to hardcoded default.
   *
   * @param promptId - The unique identifier of the prompt.
   * @returns Promise that resolves when the reset is successful.
   * @throws {ApiError} When the prompt is not found or the API request fails.
   *
   * @example
   * ```typescript
   * await api.resetPromptToDefault('architect.system');
   * console.log('Prompt reset to default');
   * ```
   */
  async resetPromptToDefault(promptId: string): Promise<void> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${promptId}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    await handleResponse(response);
  },

  /**
   * Get the hardcoded default content for a prompt.
   *
   * @param promptId - The unique identifier of the prompt.
   * @returns The default content for the prompt.
   * @throws {ApiError} When the prompt is not found or the API request fails.
   *
   * @example
   * ```typescript
   * const defaultContent = await api.getPromptDefault('architect.system');
   * console.log(`Default content: ${defaultContent.content}`);
   * ```
   */
  async getPromptDefault(promptId: string): Promise<DefaultContent> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${promptId}/default`);
    return handleResponse<DefaultContent>(response);
  },
};

export { ApiError };
