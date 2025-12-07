import type {
  WorkflowSummary,
  WorkflowStatus,
  WorkflowDetailResponse,
  WorkflowListResponse,
  ErrorResponse,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

class ApiError extends Error {
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

export const api = {
  /**
   * Get all active workflows (in_progress or blocked).
   */
  async getWorkflows(): Promise<WorkflowSummary[]> {
    const response = await fetch(`${API_BASE_URL}/workflows/active`);
    const data = await handleResponse<WorkflowListResponse>(response);
    return data.workflows;
  },

  /**
   * Get single workflow by ID with full details.
   */
  async getWorkflow(id: string): Promise<WorkflowDetailResponse> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}`);
    return handleResponse<WorkflowDetailResponse>(response);
  },

  /**
   * Approve a blocked workflow's plan.
   */
  async approveWorkflow(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    await handleResponse(response);
  },

  /**
   * Reject a workflow's plan with feedback.
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
   * Cancel a running workflow.
   */
  async cancelWorkflow(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/workflows/${id}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    await handleResponse(response);
  },

  /**
   * Get workflow history (completed, failed, cancelled).
   * Makes parallel requests for each status since the server only supports single status filtering.
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
