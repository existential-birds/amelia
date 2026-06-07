/**
 * Prompt management types.
 */

/**
 * Summary of a prompt for list views.
 */
export interface PromptSummary {
  /** Unique identifier for the prompt. */
  id: string;
  /**
   * Agent type this prompt belongs to (e.g., "architect", "developer").
   *
   * Open string to match the backend — prompts exist for many agents, not just
   * the core trio.
   */
  agent: string;
  /** Human-readable name of the prompt. */
  name: string;
  /** Optional description explaining the prompt's purpose. */
  description: string | null;
  /** ID of the currently active version, or null if using default. */
  current_version_id: string | null;
  /** Version number of the current version, or null if using default. */
  current_version_number: number | null;
}

/**
 * Summary of a prompt version.
 */
export interface VersionSummary {
  /** Unique identifier for this version. */
  id: string;
  /** Sequential version number (1, 2, 3, etc.). */
  version_number: number;
  /** ISO 8601 timestamp when this version was created. */
  created_at: string;
  /** Optional note describing changes in this version. */
  change_note: string | null;
}

/**
 * Detailed prompt with version history.
 */
export interface PromptDetail {
  /** Unique identifier for the prompt. */
  id: string;
  /** Agent type this prompt belongs to (e.g., "architect", "developer"). Open string; see {@link PromptSummary}. */
  agent: string;
  /** Human-readable name of the prompt. */
  name: string;
  /** Optional description explaining the prompt's purpose. */
  description: string | null;
  /** ID of the currently active version, or null if using default. */
  current_version_id: string | null;
  /** List of all versions for this prompt, ordered by version number. */
  versions: VersionSummary[];
}

/**
 * Full version details including content.
 */
export interface VersionDetail {
  /** Unique identifier for this version. */
  id: string;
  /** ID of the parent prompt this version belongs to. */
  prompt_id: string;
  /** Sequential version number (1, 2, 3, etc.). */
  version_number: number;
  /** Full prompt content text. */
  content: string;
  /** ISO 8601 timestamp when this version was created. */
  created_at: string;
  /** Optional note describing changes in this version. */
  change_note: string | null;
}

/**
 * Default content for a prompt.
 */
export interface DefaultContent {
  /** ID of the prompt this default belongs to. */
  prompt_id: string;
  /** Default prompt content text (built-in, not customized). */
  content: string;
  /** Human-readable name of the prompt. */
  name: string;
  /** Description explaining the prompt's purpose. */
  description: string;
}
