import type {
  WorkflowSummary,
  WorkflowStatus,
  WorkflowDetailApiResponse,
  WorkflowDetailResponse,
  WorkflowListResponse,

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
  SetPlanRequest,
  SetPlanResponse,
  FileListResponse,
  ConfigResponse,
  FileReadResponse,
  PathValidationResponse,
  UsageResponse,
  GitHubIssuesResponse,
  RequestReviewRequest,
  PRAutoFixMetricsResponse,
  ClassificationsResponse,
  CondenseDescriptionResponse,
} from '../types';
import type {
  KnowledgeDocument,
  KnowledgeDocumentListResponse,
  SearchResult,
} from '../types/knowledge';
import { request, ApiError } from './utils';

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
    const data = await request<WorkflowListResponse>('/workflows/active');
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
    const { recent_events, ...rest } = await request<WorkflowDetailApiResponse>(
      `/workflows/${id}`
    );

    // Extract recoverable flag from recent_events in the raw API response
    // so recovery detection survives page refresh without ephemeral store events.
    // Only set recoverable when we find a workflow_failed event — an empty array
    // must leave recoverable undefined so the store-events fallback still works.
    let recoverable: boolean | undefined;
    if (rest.status === 'failed' && recent_events?.length) {
      const failedEvents = recent_events
        .filter(e => e.event_type === 'workflow_failed')
        .sort((a, b) => b.sequence - a.sequence);
      const latest = failedEvents[0];
      if (latest && typeof latest.data?.recoverable === 'boolean') {
        recoverable = latest.data.recoverable;
      }
    }

    return recoverable === undefined ? rest : { ...rest, recoverable };
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
    await request(`/workflows/${id}/approve`, { method: 'POST' });
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
    await request(`/workflows/${id}/reject`, { method: 'POST', body: { feedback } });
  },

  /**
   * Requests re-planning for a blocked workflow.
   *
   * Sends the workflow back to the Architect for a new plan,
   * preserving context from the previous attempt.
   *
   * @param id - The unique identifier of the workflow to replan.
   * @returns Promise that resolves when the replan request is successful.
   * @throws {ApiError} When the workflow is not found, not in a blocked state, or the API request fails.
   *
   * @example
   * ```typescript
   * await api.replanWorkflow('workflow-123');
   * console.log('Workflow sent back for re-planning');
   * ```
   */
  async replanWorkflow(id: string): Promise<void> {
    await request(`/workflows/${id}/replan`, { method: 'POST' });
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
    await request(`/workflows/${id}/cancel`, { method: 'POST' });
  },

  /**
   * Resume a failed workflow from its last checkpoint.
   *
   * @param id - The unique identifier of the workflow to resume.
   * @returns Promise that resolves when the resume request is successful.
   * @throws {ApiError} When the workflow is not found, not in a failed state, or the API request fails.
   *
   * @example
   * ```typescript
   * await api.resumeWorkflow('workflow-123');
   * ```
   */
  async resumeWorkflow(id: string): Promise<void> {
    await request(`/workflows/${id}/resume`, { method: 'POST' });
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
        const data = await request<WorkflowListResponse>('/workflows', {
          params: { status },
        });
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
   * Creates a new workflow.
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
    payload: CreateWorkflowRequest
  ): Promise<CreateWorkflowResponse> {
    return request<CreateWorkflowResponse>('/workflows', { method: 'POST', body: payload });
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
    return request<StartWorkflowResponse>(`/workflows/${id}/start`, { method: 'POST' });
  },

  /**
   * Sets or replaces the plan for a queued workflow.
   *
   * Allows importing an external plan either from a file path or inline content.
   * The workflow must be in 'queued' status. Use `force: true` to overwrite
   * an existing plan.
   *
   * Note: `plan_file` and `plan_content` are mutually exclusive.
   *
   * @param id - The unique identifier of the workflow.
   * @param request - The plan request with either plan_file or plan_content.
   * @returns Response with extracted goal, key_files, and total_tasks.
   * @throws {ApiError} When workflow not found, not queued, validation fails, or API request fails.
   *
   * @example
   * ```typescript
   * // Set plan from file
   * const result = await api.setPlan('workflow-123', {
   *   plan_file: 'docs/plans/feature.md',
   * });
   *
   * // Set plan from inline content
   * const result = await api.setPlan('workflow-123', {
   *   plan_content: '# Plan\n\n### Task 1: Do thing',
   *   force: true,
   * });
   *
   * console.log(`Goal: ${result.goal}, Tasks: ${result.total_tasks}`);
   * ```
   */
  async setPlan(id: string, payload: SetPlanRequest): Promise<SetPlanResponse> {
    return request<SetPlanResponse>(`/workflows/${id}/plan`, { method: 'POST', body: payload });
  },

  /**
   * Lists files in a directory matching a glob pattern.
   *
   * @param directory - Relative directory path within the base directory.
   * @param globPattern - Glob pattern to filter files (default: '*.md').
   * @param worktreePath - Optional worktree path to use as base directory.
   *                      If not provided, uses active profile's repo_root.
   * @returns Response with matching file entries and directory path.
   * @throws {ApiError} When directory not found or API request fails.
   *
   * @example
   * ```typescript
   * const result = await api.listFiles('docs/plans', '*.md', '/path/to/worktree');
   * console.log(`Found ${result.files.length} files in ${result.directory}`);
   * ```
   */
  async listFiles(
    directory: string,
    globPattern: string = '*.md',
    worktreePath?: string
  ): Promise<FileListResponse> {
    return request<FileListResponse>('/files/list', {
      params: { directory, glob_pattern: globPattern, worktree_path: worktreePath },
    });
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
  async startBatch(payload: BatchStartRequest): Promise<BatchStartResponse> {
    return request<BatchStartResponse>('/workflows/start-batch', { method: 'POST', body: payload });
  },

  /**
   * Fetches open GitHub issues for a profile's repository.
   *
   * @param profile - Profile name to resolve repo context.
   * @param search - Optional search query for filtering.
   * @param signal - Optional AbortSignal for cancellation.
   * @returns List of GitHub issue summaries.
   */
  async getGitHubIssues(
    profile: string,
    search?: string,
    signal?: AbortSignal,
  ): Promise<GitHubIssuesResponse> {
    return request<GitHubIssuesResponse>('/github/issues', {
      params: { profile, search },
      signal,
    });
  },

  /**
   * Condenses a long GitHub issue body using an LLM.
   *
   * @param description - The issue body text to condense.
   * @param profile - Optional profile name; server falls back to active profile.
   * @returns Condensed description text.
   */
  async condenseDescription(
    description: string,
    profile?: string,
  ): Promise<CondenseDescriptionResponse> {
    return request<CondenseDescriptionResponse>('/descriptions/condense', {
      method: 'POST',
      body: { description, profile },
    });
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
    const data = await request<{ prompts: PromptSummary[] }>('/prompts');
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
    return request<PromptDetail>(`/prompts/${id}`);
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
    const data = await request<{ versions: VersionSummary[] }>(`/prompts/${promptId}/versions`);
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
    return request<VersionDetail>(`/prompts/${promptId}/versions/${versionId}`);
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
    return request<VersionDetail>(`/prompts/${promptId}/versions`, {
      method: 'POST',
      body: { content, change_note: changeNote },
    });
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
    await request(`/prompts/${promptId}/reset`, { method: 'POST' });
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
    return request<DefaultContent>(`/prompts/${promptId}/default`);
  },

  // ==========================================================================
  // Config API
  // ==========================================================================

  /**
   * Retrieves server configuration for dashboard.
   *
   * @returns Server configuration including repo_root and max_concurrent.
   * @throws {ApiError} When the API request fails.
   *
   * @example
   * ```typescript
   * const config = await api.getConfig();
   * console.log(`Working dir: ${config.repo_root}`);
   * ```
   */
  async getConfig(): Promise<ConfigResponse> {
    return request<ConfigResponse>('/config');
  },

  // ==========================================================================
  // Files API
  // ==========================================================================

  /**
   * Reads file content for design document import.
   *
   * @param path - Absolute path to the file to read.
   * @param worktreePath - Optional worktree path to use as base directory. If not provided, uses active profile's repo_root.
   * @returns File content and filename.
   * @throws {ApiError} When file not found, path invalid, or API request fails.
   *
   * @example
   * ```typescript
   * const file = await api.readFile('/path/to/design.md', '/path/to/worktree');
   * console.log(`Content: ${file.content}`);
   * ```
   */
  async readFile(path: string, worktreePath?: string): Promise<FileReadResponse> {
    return request<FileReadResponse>('/files/read', {
      method: 'POST',
      params: { worktree_path: worktreePath },
      body: { path },
    });
  },

  // ==========================================================================
  // Path Validation API
  // ==========================================================================

  /**
   * Validates a filesystem path and returns git repository info.
   *
   * @param path - Absolute path to validate.
   * @param signal - Optional AbortSignal to cancel the request.
   * @returns Validation result with exists, is_git_repo, branch info.
   * @throws {ApiError} When API request fails.
   *
   * @example
   * ```typescript
   * const result = await api.validatePath('/Users/me/my-repo');
   * if (result.is_git_repo) {
   *   console.log(`On branch: ${result.branch}`);
   * }
   * ```
   */
  async validatePath(path: string, signal?: AbortSignal): Promise<PathValidationResponse> {
    return request<PathValidationResponse>('/paths/validate', {
      method: 'POST',
      body: { path },
      signal,
    });
  },

  // ==========================================================================
  // Usage API
  // ==========================================================================

  /**
   * Retrieves usage metrics for a date range.
   *
   * @param params - Query parameters (preset or start/end dates).
   * @returns UsageResponse with summary, trend, and by_model.
   * @throws {ApiError} When the API request fails.
   *
   * @example
   * ```typescript
   * // With preset
   * const usage = await api.getUsage({ preset: '30d' });
   *
   * // With date range
   * const usage = await api.getUsage({ start: '2026-01-01', end: '2026-01-15' });
   * ```
   */
  async getUsage(params: {
    start?: string;
    end?: string;
    preset?: string;
  }): Promise<UsageResponse> {
    const queryParams =
      params.start && params.end
        ? { start: params.start, end: params.end }
        : { preset: params.preset ?? '30d' };

    return request<UsageResponse>('/usage', { params: queryParams });
  },

  // ==========================================================================
  // Knowledge API
  // ==========================================================================

  /**
   * List all knowledge documents.
   *
   * @returns Array of knowledge documents.
   * @throws {ApiError} When the API request fails.
   */
  async getKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
    const data = await request<KnowledgeDocumentListResponse>('/knowledge/documents');
    return data.documents;
  },

  /**
   * Upload a document for ingestion.
   *
   * @param file - File to upload (PDF or Markdown).
   * @param name - Document display name.
   * @param tags - Tags for filtering.
   * @returns Created document with pending status.
   * @throws {ApiError} When upload fails or file type unsupported.
   */
  async uploadKnowledgeDocument(
    file: File,
    name: string,
    tags: string[]
  ): Promise<KnowledgeDocument> {
    // Validate tags don't contain commas
    const invalidTag = tags.find(tag => tag.includes(','));
    if (invalidTag) {
      throw new ApiError(`Tag "${invalidTag}" cannot contain commas`, 'VALIDATION_ERROR', 400);
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    formData.append('tags', tags.join(','));

    return request<KnowledgeDocument>('/knowledge/documents', {
      method: 'POST',
      body: formData,
    });
  },

  /**
   * Delete a knowledge document.
   *
   * @param documentId - Document UUID.
   * @throws {ApiError} When document not found or API request fails.
   */
  async deleteKnowledgeDocument(documentId: string): Promise<void> {
    await request(`/knowledge/documents/${documentId}`, { method: 'DELETE' });
  },

  /**
   * Search knowledge documents.
   *
   * @param query - Natural language search query.
   * @param topK - Maximum results (default 5).
   * @param tags - Optional tags to filter.
   * @returns Ranked search results.
   * @throws {ApiError} When search fails.
   */
  async searchKnowledge(
    query: string,
    topK: number = 5,
    tags?: string[],
    signal?: AbortSignal
  ): Promise<SearchResult[]> {
    return request<SearchResult[]>('/knowledge/search', {
      method: 'POST',
      body: { query, top_k: topK, tags },
      signal,
    });
  },

  // ==========================================================================
  // Review API
  // ==========================================================================

  /**
   * Requests an on-demand code review for a workflow.
   *
   * @param workflowId - The unique identifier of the workflow.
   * @param request - Review request with mode and review types.
   * @returns Promise that resolves when the review is queued.
   * @throws {ApiError} When the workflow is not found or the API request fails.
   */
  async requestReview(
    workflowId: string,
    payload: RequestReviewRequest
  ): Promise<void> {
    await request(`/workflows/${workflowId}/review`, { method: 'POST', body: payload });
  },

  // ==========================================================================
  // PR Auto-Fix Metrics API
  // ==========================================================================

  /**
   * Retrieves PR auto-fix metrics for a date range.
   *
   * @param params - Query parameters (preset or start/end dates, optional filters).
   * @returns PRAutoFixMetricsResponse with summary, daily, and by_aggressiveness.
   * @throws {ApiError} When the API request fails.
   */
  async getAutoFixMetrics(params: {
    start?: string;
    end?: string;
    preset?: string;
    profile?: string;
    aggressiveness?: string;
  }): Promise<PRAutoFixMetricsResponse> {
    return request<PRAutoFixMetricsResponse>('/github/pr-autofix/metrics', { params });
  },

  /**
   * Retrieves paginated classification audit log.
   *
   * @param params - Query parameters (preset or start/end dates, pagination).
   * @returns ClassificationsResponse with classifications list and total count.
   * @throws {ApiError} When the API request fails.
   */
  async getClassifications(params: {
    start?: string;
    end?: string;
    preset?: string;
    limit?: number;
    offset?: number;
  }): Promise<ClassificationsResponse> {
    return request<ClassificationsResponse>('/github/pr-autofix/classifications', { params });
  },
};

export { ApiError };
