/**
 * Form-state types for the profile detail page.
 *
 * Mirrors the modal's `ProfileFormData`, with the eleven flat `sandbox_*` fields
 * grouped under a nested `sandbox` object (`SandboxFormData`). The hook
 * (`useProfileForm`) maps this nested shape back to the flat API payload the
 * server expects, byte-for-byte with the old modal.
 */
import type { PRAutoFixConfig } from '@/api/settings';

/** Driver/model selection for a single agent. */
export interface AgentFormData {
  driver: string;
  model: string;
}

/** Nested sandbox configuration form state. */
export interface SandboxFormData {
  mode: 'none' | 'container' | 'daytona';
  image: string;
  network_allowlist_enabled: boolean;
  network_allowed_hosts: string[];
  // Daytona-specific
  repo_url: string;
  daytona_api_url: string;
  daytona_target: string;
  daytona_cpu: number;
  daytona_memory: number;
  daytona_disk: number;
  daytona_image: string;
}

/** Full profile form state. */
export interface ProfileFormData {
  id: string;
  tracker: string;
  repo_root: string;
  plan_output_dir: string;
  plan_path_pattern: string;
  agents: Record<string, AgentFormData>;
  sandbox: SandboxFormData;
  pr_autofix: PRAutoFixConfig | null;
}

/** Identifiers for the four configuration sections. */
export type SectionId = 'identity' | 'agents' | 'sandbox' | 'autofix';
