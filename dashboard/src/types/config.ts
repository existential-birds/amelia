/**
 * Config API types.
 */

/**
 * Profile information for display in UI.
 * Contains driver and model configuration.
 */
export interface ConfigProfileInfo {
  /** Profile name. */
  name: string;

  /** Driver type ('api', 'claude', or 'codex'). */
  driver: string;

  /** Model name. */
  model: string;
}

/**
 * Response from GET /api/config endpoint.
 * Provides server configuration for dashboard.
 */
export interface ConfigResponse {
  /** Repository root directory for file access. */
  repo_root: string;

  /** Maximum concurrent workflows. */
  max_concurrent: number;

  /** Active profile name from settings.amelia.yaml. */
  active_profile: string;

  /** Full profile info for the active profile. */
  active_profile_info: ConfigProfileInfo | null;

  /** Character count threshold above which the condense button appears. */
  condense_threshold_chars: number;
}
