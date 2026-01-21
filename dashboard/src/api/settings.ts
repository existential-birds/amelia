/**
 * Settings and Profiles API client.
 *
 * Provides functions for managing server settings and profile configurations.
 */

const API_BASE_URL = "/api";
const DEFAULT_TIMEOUT_MS = 30000;

/**
 * Creates an AbortSignal that triggers after the specified timeout.
 */
function createTimeoutSignal(timeoutMs: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}

/**
 * Handles HTTP response parsing and error handling.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

// =============================================================================
// Types
// =============================================================================

/**
 * Server-wide settings configuration.
 */
export interface ServerSettings {
  log_retention_days: number;
  log_retention_max_events: number;
  trace_retention_days: number;
  checkpoint_retention_days: number;
  checkpoint_path: string;
  websocket_idle_timeout_seconds: number;
  workflow_start_timeout_seconds: number;
  max_concurrent: number;
  stream_tool_results: boolean;
}

/**
 * Profile configuration for workflow execution.
 */
export interface Profile {
  id: string;
  driver: string;
  model: string;
  validator_model: string;
  tracker: string;
  working_dir: string;
  plan_output_dir: string;
  plan_path_pattern: string;
  max_review_iterations: number;
  max_task_review_iterations: number;
  auto_approve_reviews: boolean;
  is_active: boolean;
}

/**
 * Request payload for creating a new profile.
 */
export interface ProfileCreate {
  id: string;
  driver: string;
  model: string;
  validator_model: string;
  tracker?: string;
  working_dir: string;
  plan_output_dir?: string;
  plan_path_pattern?: string;
  max_review_iterations?: number;
  max_task_review_iterations?: number;
  auto_approve_reviews?: boolean;
}

/**
 * Request payload for updating an existing profile.
 */
export interface ProfileUpdate {
  driver?: string;
  model?: string;
  validator_model?: string;
  tracker?: string;
  working_dir?: string;
  plan_output_dir?: string;
  plan_path_pattern?: string;
  max_review_iterations?: number;
  max_task_review_iterations?: number;
  auto_approve_reviews?: boolean;
}

// =============================================================================
// Settings API
// =============================================================================

/**
 * Retrieves current server settings.
 *
 * @returns The current server settings configuration.
 * @throws {Error} When the API request fails.
 *
 * @example
 * ```typescript
 * const settings = await getServerSettings();
 * console.log(`Max concurrent: ${settings.max_concurrent}`);
 * ```
 */
export async function getServerSettings(): Promise<ServerSettings> {
  const response = await fetch(`${API_BASE_URL}/settings`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    signal: createTimeoutSignal(),
  });
  return handleResponse<ServerSettings>(response);
}

/**
 * Updates server settings.
 *
 * @param updates - Partial settings to update.
 * @returns The updated server settings.
 * @throws {Error} When the API request fails.
 *
 * @example
 * ```typescript
 * const updated = await updateServerSettings({ max_concurrent: 10 });
 * console.log(`New max concurrent: ${updated.max_concurrent}`);
 * ```
 */
export async function updateServerSettings(
  updates: Partial<ServerSettings>
): Promise<ServerSettings> {
  const response = await fetch(`${API_BASE_URL}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
    signal: createTimeoutSignal(),
  });
  return handleResponse<ServerSettings>(response);
}

// =============================================================================
// Profiles API
// =============================================================================

/**
 * Retrieves all profiles.
 *
 * @returns Array of all profile configurations.
 * @throws {Error} When the API request fails.
 *
 * @example
 * ```typescript
 * const profiles = await getProfiles();
 * console.log(`Found ${profiles.length} profiles`);
 * ```
 */
export async function getProfiles(): Promise<Profile[]> {
  const response = await fetch(`${API_BASE_URL}/profiles`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    signal: createTimeoutSignal(),
  });
  return handleResponse<Profile[]>(response);
}

/**
 * Retrieves a single profile by ID.
 *
 * @param id - The unique identifier of the profile.
 * @returns The profile configuration.
 * @throws {Error} When the profile is not found or the API request fails.
 *
 * @example
 * ```typescript
 * const profile = await getProfile('work');
 * console.log(`Driver: ${profile.driver}`);
 * ```
 */
export async function getProfile(id: string): Promise<Profile> {
  const response = await fetch(`${API_BASE_URL}/profiles/${encodeURIComponent(id)}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    signal: createTimeoutSignal(),
  });
  return handleResponse<Profile>(response);
}

/**
 * Creates a new profile.
 *
 * @param profile - The profile configuration to create.
 * @returns The created profile.
 * @throws {Error} When validation fails or the API request fails.
 *
 * @example
 * ```typescript
 * const profile = await createProfile({
 *   id: 'work',
 *   driver: 'api:openrouter',
 *   model: 'anthropic/claude-3.5-sonnet',
 *   validator_model: 'anthropic/claude-3.5-sonnet',
 *   working_dir: '/Users/me/projects',
 * });
 * ```
 */
export async function createProfile(profile: ProfileCreate): Promise<Profile> {
  const response = await fetch(`${API_BASE_URL}/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
    signal: createTimeoutSignal(),
  });
  return handleResponse<Profile>(response);
}

/**
 * Updates an existing profile.
 *
 * @param id - The unique identifier of the profile to update.
 * @param updates - Partial profile updates to apply.
 * @returns The updated profile.
 * @throws {Error} When the profile is not found or the API request fails.
 *
 * @example
 * ```typescript
 * const updated = await updateProfile('work', { max_review_iterations: 5 });
 * console.log(`Updated iterations: ${updated.max_review_iterations}`);
 * ```
 */
export async function updateProfile(
  id: string,
  updates: ProfileUpdate
): Promise<Profile> {
  const response = await fetch(`${API_BASE_URL}/profiles/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
    signal: createTimeoutSignal(),
  });
  return handleResponse<Profile>(response);
}

/**
 * Deletes a profile.
 *
 * @param id - The unique identifier of the profile to delete.
 * @throws {Error} When the profile is not found or the API request fails.
 *
 * @example
 * ```typescript
 * await deleteProfile('old-profile');
 * console.log('Profile deleted');
 * ```
 */
export async function deleteProfile(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/profiles/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    signal: createTimeoutSignal(),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
  }
}

/**
 * Activates a profile, making it the default for new workflows.
 *
 * @param id - The unique identifier of the profile to activate.
 * @returns The activated profile with is_active set to true.
 * @throws {Error} When the profile is not found or the API request fails.
 *
 * @example
 * ```typescript
 * const active = await activateProfile('work');
 * console.log(`Profile '${active.id}' is now active`);
 * ```
 */
export async function activateProfile(id: string): Promise<Profile> {
  const response = await fetch(
    `${API_BASE_URL}/profiles/${encodeURIComponent(id)}/activate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: createTimeoutSignal(),
    }
  );
  return handleResponse<Profile>(response);
}
