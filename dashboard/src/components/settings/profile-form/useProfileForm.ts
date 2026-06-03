/**
 * Form-state hook for the profile detail page.
 *
 * Owns nested form state, validation, dirty tracking, and the API-payload
 * builders. The payload builders (`toCreatePayload`/`toUpdatePayload`) reproduce
 * the old profile modal's payloads byte-for-byte — including the
 * network-only-in-container and daytona-only-in-daytona omission logic, and the
 * create/update field sets. The only structural change from the modal is that
 * the eleven flat `sandbox_*` fields are grouped under `formData.sandbox`.
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import { z } from 'zod';
import { AGENT_DEFINITIONS } from '@/lib/constants';
import type {
  Profile,
  ProfileCreate,
  ProfileUpdate,
  SandboxConfig,
  PRAutoFixConfig,
} from '@/api/settings';
import type {
  AgentFormData,
  ProfileFormData,
  SandboxFormData,
  SectionId,
} from './types';

const PRIMARY_AGENTS = AGENT_DEFINITIONS.filter((a) => a.category === 'primary');
const UTILITY_AGENTS = AGENT_DEFINITIONS.filter((a) => a.category === 'utility');
const ALL_AGENT_KEYS = AGENT_DEFINITIONS.map((a) => a.key);

/** Default models (Claude CLI) */
const CLAUDE_MODELS = ['opus', 'sonnet', 'haiku'] as const;

/** Default models (Codex CLI) */
const CODEX_MODELS = [
  'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.3-codex', 'gpt-5.2-codex', 'gpt-5.2',
  'gpt-5.1-codex-max', 'gpt-5.1-codex-mini',
  'gpt-5.1-codex', 'gpt-5.1', 'gpt-5-codex', 'gpt-5-codex-mini', 'gpt-5',
] as const;

/** Model options by driver - API models fetched dynamically via ApiModelSelect */
const MODEL_OPTIONS_BY_DRIVER: Record<string, readonly string[]> = {
  claude: CLAUDE_MODELS,
  codex: CODEX_MODELS,
};

/** Get available models for a driver, with fallback */
const getModelsForDriver = (driver: string): readonly string[] => {
  return MODEL_OPTIONS_BY_DRIVER[driver] ?? CLAUDE_MODELS;
};

/** Build default agent configuration */
const buildDefaultAgents = (): Record<string, AgentFormData> => {
  const agents: Record<string, AgentFormData> = {};
  for (const agent of AGENT_DEFINITIONS) {
    agents[agent.key] = {
      driver: 'claude',
      model: agent.defaultModel,
    };
  }
  return agents;
};

const ABSOLUTE_PATH_ERROR = 'Repository root must be an absolute path';
const isAbsolutePath = (v: string) => v.startsWith('/');

const buildDefaultSandbox = (): SandboxFormData => ({
  mode: 'none',
  image: 'amelia-sandbox:latest',
  network_allowlist_enabled: false,
  network_allowed_hosts: [],
  repo_url: '',
  daytona_api_url: 'https://app.daytona.io/api',
  daytona_target: 'us',
  daytona_cpu: 2,
  daytona_memory: 4,
  daytona_disk: 10,
  daytona_image: 'ghcr.io/existential-birds/amelia-sandbox:latest',
});

const buildDefaultFormData = (): ProfileFormData => ({
  id: '',
  tracker: 'noop',
  repo_root: '',
  plan_output_dir: 'docs/plans',
  plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
  agents: buildDefaultAgents(),
  sandbox: buildDefaultSandbox(),
  pr_autofix: null,
});

/** Zod schema for agent form validation */
const agentFormSchema = z
  .object({
    driver: z.string().min(1),
    model: z.string(),
  })
  .refine((data) => data.driver === 'claude' || data.model !== '', {
    message: 'Model is required',
    path: ['model'],
  });

/** Zod schema for profile form validation */
const profileFormSchema = z.object({
  id: z
    .string()
    .min(1, 'Profile name is required')
    .regex(/^\S+$/, 'Profile name cannot contain spaces')
    .regex(
      /^[a-zA-Z0-9_-]+$/,
      'Only letters, numbers, underscores, and hyphens allowed'
    ),
  tracker: z.string(),
  repo_root: z
    .string()
    .min(1, 'Repository root is required')
    .refine(isAbsolutePath, ABSOLUTE_PATH_ERROR),
  plan_output_dir: z.string(),
  plan_path_pattern: z.string(),
  agents: z.record(agentFormSchema),
  sandbox: z.object({
    mode: z.enum(['none', 'container', 'daytona']),
    image: z.string(),
    network_allowlist_enabled: z.boolean(),
    network_allowed_hosts: z.array(z.string()),
  }),
});

/** Fields that accept string values and can be validated individually */
type ValidatableField = 'id' | 'repo_root';

/** Validate individual field using Zod schema */
const validateField = (field: ValidatableField, value: string): string | null => {
  const fieldSchema = profileFormSchema.shape[field];
  const result = fieldSchema.safeParse(value);
  if (!result.success) {
    return result.error.issues[0]?.message ?? 'Invalid value';
  }
  // Additional refinements not captured by .shape extraction
  if (field === 'repo_root' && value && !isAbsolutePath(value)) {
    return ABSOLUTE_PATH_ERROR;
  }
  return null;
};

/** Convert Profile to ProfileFormData (nested sandbox). */
const profileToFormData = (profile: Profile): ProfileFormData => {
  const agents: Record<string, AgentFormData> = {};

  for (const agent of AGENT_DEFINITIONS) {
    agents[agent.key] = {
      driver: profile.agents?.[agent.key]?.driver ?? 'claude',
      model: profile.agents?.[agent.key]?.model ?? agent.defaultModel,
    };
  }

  return {
    id: profile.id,
    tracker: profile.tracker,
    repo_root: profile.repo_root,
    plan_output_dir: profile.plan_output_dir,
    plan_path_pattern: profile.plan_path_pattern,
    agents,
    sandbox: {
      mode: profile.sandbox?.mode ?? 'none',
      image: profile.sandbox?.image ?? 'amelia-sandbox:latest',
      network_allowlist_enabled: profile.sandbox?.network_allowlist_enabled ?? false,
      network_allowed_hosts: profile.sandbox?.network_allowed_hosts ?? [],
      repo_url: profile.sandbox?.repo_url ?? '',
      daytona_api_url: profile.sandbox?.daytona_api_url ?? 'https://app.daytona.io/api',
      daytona_target: profile.sandbox?.daytona_target ?? 'us',
      daytona_cpu: profile.sandbox?.daytona_resources?.cpu ?? 2,
      daytona_memory: profile.sandbox?.daytona_resources?.memory ?? 4,
      daytona_disk: profile.sandbox?.daytona_resources?.disk ?? 10,
      daytona_image:
        profile.sandbox?.daytona_image ?? 'ghcr.io/existential-birds/amelia-sandbox:latest',
    },
    pr_autofix: profile.pr_autofix ?? null,
  };
};

/** Derive section flags from validation error keys. */
const computeSectionErrors = (
  errors: Record<string, string>
): Record<SectionId, boolean> => {
  const sectionErrors: Record<SectionId, boolean> = {
    identity: false,
    agents: false,
    sandbox: false,
    autofix: false,
  };
  for (const key of Object.keys(errors)) {
    if (key.startsWith('agent_')) {
      sectionErrors.agents = true;
    } else if (key.startsWith('sandbox')) {
      sectionErrors.sandbox = true;
    } else if (key.startsWith('pr_autofix')) {
      sectionErrors.autofix = true;
    } else {
      sectionErrors.identity = true;
    }
  }
  return sectionErrors;
};

export interface UseProfileForm {
  formData: ProfileFormData;
  errors: Record<string, string>;
  isEditMode: boolean;
  isDirty: boolean;
  sectionErrors: Record<SectionId, boolean>;
  setField: (key: keyof ProfileFormData, value: string | number | boolean) => void;
  setAgent: (key: string, field: 'driver' | 'model', value: string) => void;
  bulkApplyAgents: (
    driver: string,
    model: string,
    targets: 'all' | 'primary' | 'utility'
  ) => void;
  setSandboxField: (
    key: keyof SandboxFormData,
    value: string | number | boolean | string[]
  ) => void;
  setHosts: (hosts: string[]) => void;
  setPrAutofix: (config: PRAutoFixConfig | null) => void;
  handleBlur: (field: ValidatableField, value: string) => void;
  validate: () => boolean;
  toCreatePayload: () => ProfileCreate;
  toUpdatePayload: () => ProfileUpdate;
}

/**
 * Manages profile form state for the detail page.
 *
 * @param profile - Existing profile (edit mode) or `null` (create mode).
 */
export function useProfileForm(profile: Profile | null): UseProfileForm {
  const isEditMode = profile !== null;

  const initial = useMemo(
    () => (profile ? profileToFormData(profile) : buildDefaultFormData()),
    [profile]
  );

  const [formData, setFormData] = useState<ProfileFormData>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Snapshot of the original state for dirty comparison.
  const originalFormDataRef = useRef<ProfileFormData>(initial);

  const isDirty = useMemo(
    () => JSON.stringify(formData) !== JSON.stringify(originalFormDataRef.current),
    [formData]
  );

  const setField = useCallback(
    (key: keyof ProfileFormData, value: string | number | boolean) => {
      setFormData((prev) => ({ ...prev, [key]: value }));
      setErrors((prev) => {
        if (!prev[key as string]) return prev;
        const next = { ...prev };
        delete next[key as string];
        return next;
      });
    },
    []
  );

  const setAgent = useCallback(
    (agentKey: string, field: 'driver' | 'model', value: string) => {
      setFormData((prev) => {
        const nextAgents = { ...prev.agents };
        const currentAgent = nextAgents[agentKey] ?? { driver: 'claude', model: 'opus' };

        if (field === 'driver') {
          // Reset model on driver change (same logic as the modal).
          let newModel: string;
          if (value === 'api') {
            newModel = '';
          } else {
            const models = getModelsForDriver(value);
            newModel = models.includes(currentAgent.model)
              ? currentAgent.model
              : models[0] ?? '';
          }
          nextAgents[agentKey] = { driver: value, model: newModel };
        } else {
          nextAgents[agentKey] = { ...currentAgent, model: value };
        }

        return { ...prev, agents: nextAgents };
      });
    },
    []
  );

  const bulkApplyAgents = useCallback(
    (driver: string, model: string, targets: 'all' | 'primary' | 'utility') => {
      setFormData((prev) => {
        const nextAgents = { ...prev.agents };
        const targetAgents =
          targets === 'all'
            ? AGENT_DEFINITIONS
            : targets === 'primary'
              ? PRIMARY_AGENTS
              : UTILITY_AGENTS;

        for (const agent of targetAgents) {
          nextAgents[agent.key] = { driver, model };
        }
        return { ...prev, agents: nextAgents };
      });
    },
    []
  );

  const setSandboxField = useCallback(
    (key: keyof SandboxFormData, value: string | number | boolean | string[]) => {
      setFormData((prev) => ({
        ...prev,
        sandbox: { ...prev.sandbox, [key]: value },
      }));
      // Sandbox errors are keyed without the nested path (e.g. sandbox_repo_url).
      const errorKey = `sandbox_${key}`;
      setErrors((prev) => {
        if (!prev[errorKey]) return prev;
        const next = { ...prev };
        delete next[errorKey];
        return next;
      });
    },
    []
  );

  const setHosts = useCallback((hosts: string[]) => {
    setFormData((prev) => ({
      ...prev,
      sandbox: { ...prev.sandbox, network_allowed_hosts: hosts },
    }));
  }, []);

  const setPrAutofix = useCallback((config: PRAutoFixConfig | null) => {
    setFormData((prev) => ({ ...prev, pr_autofix: config }));
  }, []);

  const handleBlur = useCallback((field: ValidatableField, value: string) => {
    const error = validateField(field, value);
    if (error) {
      setErrors((prev) => ({ ...prev, [field]: error }));
    }
  }, []);

  const validate = useCallback((): boolean => {
    const newErrors: Record<string, string> = {};

    // Schema validation (skip id validation in edit mode).
    const dataToValidate = isEditMode ? { ...formData, id: 'placeholder' } : formData;
    const result = profileFormSchema.safeParse(dataToValidate);

    if (!result.success) {
      for (const issue of result.error.issues) {
        // Normalize agent field paths: agents.<key>.model -> agent_model_<key>
        let key: string;
        if (issue.path[0] === 'agents' && issue.path.length === 3) {
          const agentKey = issue.path[1];
          const field = issue.path[2];
          key = `agent_${field}_${agentKey}`;
        } else if (issue.path[0] === 'sandbox' && issue.path.length === 2) {
          // sandbox.<field> -> sandbox_<field>
          key = `sandbox_${issue.path[1]}`;
        } else {
          key = issue.path.join('_') || 'general';
        }
        newErrors[key] = issue.message;
      }
    }

    if (formData.sandbox.mode === 'daytona' && !formData.sandbox.repo_url.trim()) {
      newErrors.sandbox_repo_url = 'Repository URL is required for Daytona mode';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formData, isEditMode]);

  const formAgentsToApi = useCallback(() => {
    const agents: Record<string, { driver: string; model: string }> = {};
    for (const key of ALL_AGENT_KEYS) {
      const agentConfig = formData.agents[key];
      agents[key] = {
        driver: agentConfig?.driver ?? 'claude',
        model: agentConfig?.model ?? '',
      };
    }
    return agents;
  }, [formData.agents]);

  const formSandboxToApi = useCallback((): SandboxConfig => {
    const sb = formData.sandbox;
    const isContainer = sb.mode === 'container';
    return {
      mode: sb.mode,
      image: sb.image,
      network_allowlist_enabled: isContainer ? sb.network_allowlist_enabled : false,
      network_allowed_hosts: isContainer ? sb.network_allowed_hosts : [],
      ...(sb.mode === 'daytona' && {
        repo_url: sb.repo_url,
        daytona_api_url: sb.daytona_api_url,
        daytona_target: sb.daytona_target,
        daytona_image: sb.daytona_image,
        daytona_resources: {
          cpu: sb.daytona_cpu,
          memory: sb.daytona_memory,
          disk: sb.daytona_disk,
        },
      }),
    };
  }, [formData.sandbox]);

  const toCreatePayload = useCallback(
    (): ProfileCreate => ({
      id: formData.id,
      tracker: formData.tracker,
      repo_root: formData.repo_root,
      plan_output_dir: formData.plan_output_dir,
      plan_path_pattern: formData.plan_path_pattern,
      agents: formAgentsToApi(),
      sandbox: formSandboxToApi(),
      pr_autofix: formData.pr_autofix,
    }),
    [formData, formAgentsToApi, formSandboxToApi]
  );

  const toUpdatePayload = useCallback(
    (): ProfileUpdate => ({
      tracker: formData.tracker,
      repo_root: formData.repo_root,
      plan_output_dir: formData.plan_output_dir,
      plan_path_pattern: formData.plan_path_pattern,
      agents: formAgentsToApi(),
      sandbox: formSandboxToApi(),
      pr_autofix: formData.pr_autofix,
    }),
    [formData, formAgentsToApi, formSandboxToApi]
  );

  const sectionErrors = useMemo(() => computeSectionErrors(errors), [errors]);

  return {
    formData,
    errors,
    isEditMode,
    isDirty,
    sectionErrors,
    setField,
    setAgent,
    bulkApplyAgents,
    setSandboxField,
    setHosts,
    setPrAutofix,
    handleBlur,
    validate,
    toCreatePayload,
    toUpdatePayload,
  };
}
