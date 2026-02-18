/**
 * Modal for creating and editing profiles.
 *
 * Features a "Mission Control" aesthetic with progressive disclosure for agent configuration.
 * Primary agents (architect, developer, reviewer) are always visible.
 * Utility agents are collapsed by default but easily accessible.
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion } from 'motion/react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import {
  ChevronDown,
  Copy,
  Check,
  Cpu,
  Brain,
  Code,
  Search,
  ClipboardCheck,
  Scale,
  Lightbulb,
  FileCheck,
  Wand2,
  Terminal,
  Cloud,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { createProfile, updateProfile } from '@/api/settings';
import type { Profile, ProfileCreate, ProfileUpdate, SandboxConfig } from '@/api/settings';
import { Switch } from '@/components/ui/switch';
import * as toast from '@/components/Toast';
import { ApiModelSelect } from '@/components/model-picker';

// =============================================================================
// Agent Definitions
// =============================================================================

interface AgentDefinition {
  key: string;
  label: string;
  description: string;
  icon: typeof Cpu;
  defaultModel: string;
  category: 'primary' | 'utility';
}

/** All agents in the system with their metadata */
const AGENT_DEFINITIONS: AgentDefinition[] = [
  // Primary agents - always visible
  {
    key: 'architect',
    label: 'Architect',
    description: 'Plans implementation strategy',
    icon: Brain,
    defaultModel: 'opus',
    category: 'primary',
  },
  {
    key: 'developer',
    label: 'Developer',
    description: 'Writes and modifies code',
    icon: Code,
    defaultModel: 'opus',
    category: 'primary',
  },
  {
    key: 'reviewer',
    label: 'Reviewer',
    description: 'Reviews code changes',
    icon: Search,
    defaultModel: 'sonnet',
    category: 'primary',
  },
  // Utility agents - collapsed by default
  {
    key: 'plan_validator',
    label: 'Plan Validator',
    description: 'Validates plan structure',
    icon: FileCheck,
    defaultModel: 'haiku',
    category: 'utility',
  },
  {
    key: 'task_reviewer',
    label: 'Task Reviewer',
    description: 'Reviews individual tasks',
    icon: ClipboardCheck,
    defaultModel: 'haiku',
    category: 'utility',
  },
  {
    key: 'evaluator',
    label: 'Evaluator',
    description: 'Evaluates review quality',
    icon: Scale,
    defaultModel: 'haiku',
    category: 'utility',
  },
  {
    key: 'brainstormer',
    label: 'Brainstormer',
    description: 'Generates creative ideas',
    icon: Lightbulb,
    defaultModel: 'haiku',
    category: 'utility',
  },
];

const PRIMARY_AGENTS = AGENT_DEFINITIONS.filter(a => a.category === 'primary');
const UTILITY_AGENTS = AGENT_DEFINITIONS.filter(a => a.category === 'utility');
const ALL_AGENT_KEYS = AGENT_DEFINITIONS.map(a => a.key);

/** Agent-specific colors matching canvas node styling */
const AGENT_COLORS: Record<string, { line: string; icon: string }> = {
  architect: { line: 'bg-agent-architect', icon: 'text-agent-architect' },
  developer: { line: 'bg-agent-developer', icon: 'text-agent-developer' },
  reviewer: { line: 'bg-agent-reviewer', icon: 'text-agent-reviewer' },
  // Utility agents use muted styling
  plan_validator: { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' },
  task_reviewer: { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' },
  evaluator: { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' },
  brainstormer: { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' },
};

// =============================================================================
// Form Types
// =============================================================================

interface AgentFormData {
  driver: string;
  model: string;
}

interface FormData {
  id: string;
  tracker: string;
  working_dir: string;
  plan_output_dir: string;
  plan_path_pattern: string;
  agents: Record<string, AgentFormData>;
  sandbox_mode: 'none' | 'container';
  sandbox_image: string;
  sandbox_network_allowlist_enabled: boolean;
  sandbox_network_allowed_hosts: string[];
}

// =============================================================================
// Configuration Options
// =============================================================================

const DRIVER_OPTIONS = [
  { value: 'cli', label: 'Claude CLI', icon: Terminal },
  { value: 'api', label: 'OpenRouter API', icon: Cloud },
];

const TRACKER_OPTIONS = [
  { value: 'noop', label: 'None' },
  { value: 'jira', label: 'Jira' },
  { value: 'github', label: 'GitHub' },
];

/** Default models (Claude CLI) */
const CLAUDE_MODELS = ['opus', 'sonnet', 'haiku'] as const;

/** Model options by driver - API models fetched dynamically via ApiModelSelect */
const MODEL_OPTIONS_BY_DRIVER: Record<string, readonly string[]> = {
  'cli': CLAUDE_MODELS,
};

// =============================================================================
// Helper Functions
// =============================================================================

/** Get available models for a driver, with fallback */
const getModelsForDriver = (driver: string): readonly string[] => {
  return MODEL_OPTIONS_BY_DRIVER[driver] ?? CLAUDE_MODELS;
};

/** Build default agent configuration */
const buildDefaultAgents = (): Record<string, AgentFormData> => {
  const agents: Record<string, AgentFormData> = {};
  for (const agent of AGENT_DEFINITIONS) {
    agents[agent.key] = {
      driver: 'cli',
      model: agent.defaultModel,
    };
  }
  return agents;
};

const DEFAULT_FORM_DATA: FormData = {
  id: '',
  tracker: 'noop',
  working_dir: '',
  plan_output_dir: 'docs/plans',
  plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
  agents: buildDefaultAgents(),
  sandbox_mode: 'none',
  sandbox_image: 'amelia-sandbox:latest',
  sandbox_network_allowlist_enabled: false,
  sandbox_network_allowed_hosts: [],
};

/** Validation rules for profile fields */
const validateField = (field: string, value: string): string | null => {
  switch (field) {
    case 'id':
      if (!value.trim()) return 'Profile name is required';
      if (/\s/.test(value)) return 'Profile name cannot contain spaces';
      if (!/^[a-zA-Z0-9_-]+$/.test(value)) {
        return 'Profile name can only contain letters, numbers, underscores, and hyphens';
      }
      return null;
    case 'working_dir':
      if (!value.trim()) return 'Working directory is required';
      return null;
    default:
      return null;
  }
};

/** Convert Profile to FormData for comparison */
const profileToFormData = (profile: Profile): FormData => {
  const agents: Record<string, AgentFormData> = {};

  for (const agent of AGENT_DEFINITIONS) {
    agents[agent.key] = {
      driver: profile.agents?.[agent.key]?.driver ?? 'cli',
      model: profile.agents?.[agent.key]?.model ?? agent.defaultModel,
    };
  }

  return {
    id: profile.id,
    tracker: profile.tracker,
    working_dir: profile.working_dir,
    plan_output_dir: profile.plan_output_dir,
    plan_path_pattern: profile.plan_path_pattern,
    agents,
    sandbox_mode: profile.sandbox?.mode ?? 'none',
    sandbox_image: profile.sandbox?.image ?? 'amelia-sandbox:latest',
    sandbox_network_allowlist_enabled: profile.sandbox?.network_allowlist_enabled ?? false,
    sandbox_network_allowed_hosts: profile.sandbox?.network_allowed_hosts ?? [],
  };
};

// =============================================================================
// Agent Configuration Card Component
// =============================================================================

interface AgentCardProps {
  agent: AgentDefinition;
  config: AgentFormData;
  onChange: (field: 'driver' | 'model', value: string) => void;
}

function AgentCard({ agent, config, onChange }: AgentCardProps) {
  const Icon = agent.icon;
  const availableModels = getModelsForDriver(config.driver);
  const colors = AGENT_COLORS[agent.key] ?? { line: 'bg-muted-foreground/40', icon: 'text-muted-foreground' };

  return (
    <div className="group relative flex flex-wrap items-center gap-2 rounded-md border border-border/40 bg-card/30 px-3 py-2 transition-all duration-200 hover:border-border/60 hover:bg-card/50">
      {/* Status indicator line */}
      <div className={cn('w-0.5 h-6 rounded-full shrink-0', colors.line)} />

      {/* Agent icon + name */}
      <div className="flex items-center gap-2 min-w-[110px] flex-1 sm:flex-none">
        <Icon className={cn('h-4 w-4 shrink-0', colors.icon)} />
        <span className="font-heading text-sm font-medium tracking-wide">{agent.label}</span>
      </div>

      {/* Driver select */}
      <Select value={config.driver} onValueChange={(v) => onChange('driver', v)}>
        <SelectTrigger className="h-7 w-full sm:w-[130px] text-xs bg-background/50">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {DRIVER_OPTIONS.map((opt) => {
            const OptIcon = opt.icon;
            return (
              <SelectItem key={opt.value} value={opt.value}>
                <div className="flex items-center gap-2">
                  <OptIcon className="h-3 w-3" />
                  {opt.label}
                </div>
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>

      {/* Model select - ApiModelSelect for api driver, simple Select for cli */}
      {config.driver === 'api' ? (
        <ApiModelSelect
          agentKey={agent.key}
          value={config.model}
          onChange={(v) => onChange('model', v)}
        />
      ) : (
        <Select
          key={`${agent.key}-model-${config.driver}`}
          value={config.model}
          onValueChange={(v) => onChange('model', v)}
        >
          <SelectTrigger className="h-7 w-full sm:w-[90px] text-xs bg-background/50">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {availableModels.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}

// =============================================================================
// Bulk Apply Component
// =============================================================================

interface BulkApplyProps {
  onApply: (driver: string, model: string, targets: 'all' | 'primary' | 'utility') => void;
}

function BulkApply({ onApply }: BulkApplyProps) {
  const [driver, setDriver] = useState('cli');
  const [model, setModel] = useState('sonnet');
  const [showSuccess, setShowSuccess] = useState(false);

  const availableModels = useMemo(() => getModelsForDriver(driver), [driver]);

  // Reset model when driver changes if current model isn't available
  useEffect(() => {
    if (!availableModels.includes(model)) {
      setModel(availableModels[0] ?? 'sonnet');
    }
  }, [availableModels, model]);

  const handleApply = (targets: 'all' | 'primary' | 'utility') => {
    onApply(driver, model, targets);
    setShowSuccess(true);
    setTimeout(() => setShowSuccess(false), 1500);
  };

  return (
    <Collapsible>
      <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md border border-border/30 bg-background/30 px-3 py-2 text-xs font-medium hover:bg-muted/30 hover:border-border/50 transition-all">
        <div className="flex items-center gap-2">
          <Copy className="h-3.5 w-3.5 text-muted-foreground" />
          <span>Bulk Configuration</span>
        </div>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground transition-transform duration-200 [[data-state=open]>&]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-3">
        <div className="rounded-lg border border-border/30 bg-card/20 p-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                Driver
              </Label>
              <Select value={driver} onValueChange={setDriver}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DRIVER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                Model
              </Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="flex-1 h-7 text-xs"
              onClick={() => handleApply('all')}
            >
              {showSuccess ? <Check className="h-3 w-3 mr-1" /> : <Wand2 className="h-3 w-3 mr-1" />}
              Apply to All
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2"
              onClick={() => handleApply('primary')}
            >
              Primary Only
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2"
              onClick={() => handleApply('utility')}
            >
              Utility Only
            </Button>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

// =============================================================================
// Host Chip Input Component
// =============================================================================

interface HostChipInputProps {
  hosts: string[];
  onChange: (hosts: string[]) => void;
}

function HostChipInput({ hosts, onChange }: HostChipInputProps) {
  const [inputValue, setInputValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const isValidHostname = (host: string): boolean => {
    return /^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$/.test(host);
  };

  const addHost = () => {
    const trimmed = inputValue.trim().toLowerCase();
    if (!trimmed) return;

    if (!isValidHostname(trimmed)) {
      setError('Invalid hostname');
      return;
    }
    if (hosts.includes(trimmed)) {
      setError('Host already added');
      return;
    }

    onChange([...hosts, trimmed]);
    setInputValue('');
    setError(null);
  };

  const removeHost = (host: string) => {
    onChange(hosts.filter((h) => h !== host));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addHost();
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5 min-h-[32px]">
        {hosts.map((host) => (
          <Badge
            key={host}
            variant="secondary"
            className="text-xs font-mono gap-1 pl-2 pr-1"
          >
            {host}
            <button
              type="button"
              onClick={() => removeHost(host)}
              className="ml-0.5 rounded-sm hover:bg-muted-foreground/20 p-0.5"
              aria-label={`Remove ${host}`}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={handleKeyDown}
          placeholder="api.example.com"
          className={cn(
            'bg-background/50 font-mono text-sm flex-1',
            error && 'border-destructive focus-visible:ring-destructive'
          )}
        />
        <Button type="button" variant="outline" size="sm" onClick={addHost}>
          Add
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

interface ProfileEditModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profile: Profile | null;  // null = create mode, Profile = edit mode
  onSaved: () => void;
}

export function ProfileEditModal({ open, onOpenChange, profile, onSaved }: ProfileEditModalProps) {
  const isEditMode = profile !== null;
  const [isSaving, setIsSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const [utilityAgentsOpen, setUtilityAgentsOpen] = useState(false);

  const [formData, setFormData] = useState<FormData>({ ...DEFAULT_FORM_DATA });

  // Track the original state when modal opens for comparison
  const originalFormDataRef = useRef<FormData>({ ...DEFAULT_FORM_DATA });

  useEffect(() => {
    const newFormData = profile ? profileToFormData(profile) : { ...DEFAULT_FORM_DATA };
    setFormData(newFormData);
    originalFormDataRef.current = newFormData;
    setErrors({});
    // Reset collapsible states when profile changes
    setUtilityAgentsOpen(false);
  }, [profile, open]);

  /**
   * Check if the form has unsaved changes
   */
  const hasUnsavedChanges = useCallback((): boolean => {
    const original = originalFormDataRef.current;
    if (
      formData.id !== original.id ||
      formData.tracker !== original.tracker ||
      formData.working_dir !== original.working_dir ||
      formData.plan_output_dir !== original.plan_output_dir ||
      formData.plan_path_pattern !== original.plan_path_pattern
    ) {
      return true;
    }
    for (const key of ALL_AGENT_KEYS) {
      if (
        formData.agents[key]?.driver !== original.agents[key]?.driver ||
        formData.agents[key]?.model !== original.agents[key]?.model
      ) {
        return true;
      }
    }
    if (
      formData.sandbox_mode !== original.sandbox_mode ||
      formData.sandbox_image !== original.sandbox_image ||
      formData.sandbox_network_allowlist_enabled !== original.sandbox_network_allowlist_enabled ||
      JSON.stringify(formData.sandbox_network_allowed_hosts) !== JSON.stringify(original.sandbox_network_allowed_hosts)
    ) {
      return true;
    }
    return false;
  }, [formData]);

  const handleClose = useCallback(() => {
    if (hasUnsavedChanges()) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to close?'
      );
      if (!confirmed) return;
    }
    onOpenChange(false);
  }, [hasUnsavedChanges, onOpenChange]);

  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (!newOpen) {
      handleClose();
    } else {
      onOpenChange(newOpen);
    }
  }, [handleClose, onOpenChange]);

  const handleChange = (key: string, value: string | number | boolean) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const handleAgentChange = (agentKey: string, field: 'driver' | 'model', value: string) => {
    setFormData((prev) => {
      const nextAgents = { ...prev.agents };
      const currentAgent = nextAgents[agentKey] ?? { driver: 'cli', model: 'opus' };
      nextAgents[agentKey] = { ...currentAgent, [field]: value };

      // When driver changes, reset model to appropriate default
      if (field === 'driver') {
        const updatedAgent = nextAgents[agentKey]!;
        if (value === 'api') {
          // API models are selected dynamically via the model picker
          // Set to empty string until user selects from picker
          updatedAgent.model = '';
        } else {
          // CLI driver: reset to first available CLI model if current model is invalid
          const availableModels = getModelsForDriver(value);
          if (!availableModels.includes(updatedAgent.model)) {
            updatedAgent.model = availableModels[0] ?? '';
          }
        }
      }

      return { ...prev, agents: nextAgents };
    });
  };

  const handleBulkApply = (driver: string, model: string, targets: 'all' | 'primary' | 'utility') => {
    setFormData((prev) => {
      const nextAgents = { ...prev.agents };
      const targetAgents = targets === 'all'
        ? AGENT_DEFINITIONS
        : targets === 'primary'
          ? PRIMARY_AGENTS
          : UTILITY_AGENTS;

      for (const agent of targetAgents) {
        nextAgents[agent.key] = { driver, model };
      }
      return { ...prev, agents: nextAgents };
    });
  };

  const handleBlur = (field: string, value: string) => {
    const error = validateField(field, value);
    if (error) {
      setErrors((prev) => ({ ...prev, [field]: error }));
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!isEditMode) {
      const idError = validateField('id', formData.id);
      if (idError) newErrors.id = idError;
    }

    const workingDirError = validateField('working_dir', formData.working_dir);
    if (workingDirError) newErrors.working_dir = workingDirError;

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const formAgentsToApi = () => {
    const agents: Record<string, { driver: string; model: string }> = {};
    for (const key of ALL_AGENT_KEYS) {
      const agentConfig = formData.agents[key];
      agents[key] = {
        driver: agentConfig?.driver ?? 'cli',
        // Defensive: Use || to coerce empty strings to default. Backend bug allows empty strings but they cause runtime failures.
        model: agentConfig?.model || 'opus',
      };
    }
    return agents;
  };

  const formSandboxToApi = (): SandboxConfig => ({
    mode: formData.sandbox_mode,
    image: formData.sandbox_image,
    network_allowlist_enabled: formData.sandbox_network_allowlist_enabled,
    network_allowed_hosts: formData.sandbox_network_allowed_hosts,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    setIsSaving(true);

    try {
      if (isEditMode) {
        const updates: ProfileUpdate = {
          tracker: formData.tracker,
          working_dir: formData.working_dir,
          plan_output_dir: formData.plan_output_dir,
          plan_path_pattern: formData.plan_path_pattern,
          agents: formAgentsToApi(),
          sandbox: formSandboxToApi(),
        };
        await updateProfile(profile!.id, updates);
        toast.success('Profile updated');
      } else {
        const newProfile: ProfileCreate = {
          id: formData.id,
          tracker: formData.tracker,
          working_dir: formData.working_dir,
          plan_output_dir: formData.plan_output_dir,
          plan_path_pattern: formData.plan_path_pattern,
          agents: formAgentsToApi(),
          sandbox: formSandboxToApi(),
        };
        await createProfile(newProfile);
        toast.success('Profile created');
      }
      onSaved();
      onOpenChange(false);
    } catch {
      toast.error(isEditMode ? 'Failed to update profile' : 'Failed to create profile');
    } finally {
      setIsSaving(false);
    }
  };

  // Count configured utility agents for badge
  const utilityConfigCount = UTILITY_AGENTS.filter(
    a => formData.agents[a.key]?.driver && formData.agents[a.key]?.model
  ).length;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto p-0">
        {/* Header */}
        <div className="relative border-b border-border/30">
          <DialogHeader className="p-6 pb-4">
            <DialogTitle className="font-heading text-xl tracking-wide flex items-center gap-2">
              <Cpu className="h-5 w-5 text-muted-foreground" />
              {isEditMode ? 'Edit Profile' : 'Create Profile'}
            </DialogTitle>
            <DialogDescription>
              {isEditMode
                ? 'Update the profile configuration for your agents.'
                : 'Configure a new profile with driver and model settings for each agent.'}
            </DialogDescription>
          </DialogHeader>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col h-full">
          <Tabs defaultValue="general" className="flex-1 px-6 pt-4">
            <TabsList className="w-full justify-start">
              <TabsTrigger value="general">General</TabsTrigger>
              <TabsTrigger value="agents">Agents</TabsTrigger>
              <TabsTrigger value="sandbox">Sandbox</TabsTrigger>
            </TabsList>

            {/* General Tab */}
            <TabsContent value="general" className="space-y-4 pt-4">
              {/* Profile Name + Tracker */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="id" className="text-xs uppercase tracking-wider text-muted-foreground">
                    Profile Name
                  </Label>
                  <Input
                    id="id"
                    value={formData.id}
                    onChange={(e) => handleChange('id', e.target.value)}
                    onBlur={(e) => !isEditMode && handleBlur('id', e.target.value)}
                    disabled={isEditMode}
                    placeholder="e.g., dev, prod"
                    aria-invalid={!!errors.id}
                    className={cn(
                      'bg-background/50 hover:border-muted-foreground/30 transition-colors',
                      errors.id && 'border-destructive focus-visible:ring-destructive'
                    )}
                  />
                  {errors.id && (
                    <p className="text-xs text-destructive">{errors.id}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                    Issue Tracker
                  </Label>
                  <Select value={formData.tracker} onValueChange={(v) => handleChange('tracker', v)}>
                    <SelectTrigger className="bg-background/50">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TRACKER_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Working Directory */}
              <div className="space-y-2">
                <Label htmlFor="working_dir" className="text-xs uppercase tracking-wider text-muted-foreground">
                  Working Directory
                </Label>
                <Input
                  id="working_dir"
                  value={formData.working_dir}
                  onChange={(e) => handleChange('working_dir', e.target.value)}
                  onBlur={(e) => handleBlur('working_dir', e.target.value)}
                  placeholder="/path/to/repo"
                  aria-invalid={!!errors.working_dir}
                  className={cn(
                    'bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm',
                    errors.working_dir && 'border-destructive focus-visible:ring-destructive'
                  )}
                />
                {errors.working_dir && (
                  <p className="text-xs text-destructive">{errors.working_dir}</p>
                )}
              </div>

              {/* Plan Output Directory */}
              <div className="space-y-2">
                <Label htmlFor="plan_output_dir" className="text-xs uppercase tracking-wider text-muted-foreground">
                  Plan Output Directory
                </Label>
                <Input
                  id="plan_output_dir"
                  value={formData.plan_output_dir}
                  onChange={(e) => handleChange('plan_output_dir', e.target.value)}
                  placeholder="docs/plans"
                  className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
                />
              </div>

              {/* Plan Path Pattern */}
              <div className="space-y-2">
                <Label htmlFor="plan_path_pattern" className="text-xs uppercase tracking-wider text-muted-foreground">
                  Plan Path Pattern
                </Label>
                <Input
                  id="plan_path_pattern"
                  value={formData.plan_path_pattern}
                  onChange={(e) => handleChange('plan_path_pattern', e.target.value)}
                  placeholder="docs/plans/{date}-{issue_key}.md"
                  className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
                />
              </div>
            </TabsContent>

            {/* Agents Tab */}
            <TabsContent value="agents" className="space-y-4 pt-4">
              {/* Bulk Apply */}
              <BulkApply onApply={handleBulkApply} />

              {/* Primary Agents */}
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                    Primary Agents
                  </Label>
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                    Core workflow
                  </Badge>
                </div>
                <div className="grid gap-2 grid-cols-1">
                  {PRIMARY_AGENTS.map((agent) => {
                    const config = formData.agents[agent.key] ?? { driver: 'cli', model: agent.defaultModel };
                    return (
                      <AgentCard
                        key={agent.key}
                        agent={agent}
                        config={config}
                        onChange={(field, value) => handleAgentChange(agent.key, field, value)}
                      />
                    );
                  })}
                </div>
              </div>

              {/* Utility Agents (Collapsible) */}
              <Collapsible open={utilityAgentsOpen} onOpenChange={setUtilityAgentsOpen}>
                <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border border-border/30 bg-background/30 px-4 py-3 text-sm font-medium hover:bg-muted/30 hover:border-border/50 transition-all">
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase tracking-wider">Utility Agents</span>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4">
                      {utilityConfigCount} configured
                    </Badge>
                  </div>
                  <ChevronDown
                    className={cn(
                      'size-4 text-muted-foreground transition-transform duration-200',
                      utilityAgentsOpen && 'rotate-180'
                    )}
                  />
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-3">
                  <div className="grid gap-2 grid-cols-1">
                    {UTILITY_AGENTS.map((agent) => {
                      const config = formData.agents[agent.key] ?? { driver: 'cli', model: agent.defaultModel };
                      return (
                        <AgentCard
                          key={agent.key}
                          agent={agent}
                          config={config}
                          onChange={(field, value) => handleAgentChange(agent.key, field, value)}
                        />
                      );
                    })}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            </TabsContent>

            {/* Sandbox Tab */}
            <TabsContent value="sandbox" className="space-y-4 pt-4">
              {/* Sandbox Mode */}
              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Sandbox Mode
                </Label>
                <Select
                  value={formData.sandbox_mode}
                  onValueChange={(v) => handleChange('sandbox_mode', v)}
                >
                  <SelectTrigger className="bg-background/50">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="container">Container</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {formData.sandbox_mode === 'none'
                    ? 'Code runs directly on the host machine.'
                    : 'Code runs in an isolated Docker container.'}
                </p>
              </div>

              {/* Container-specific settings */}
              {formData.sandbox_mode === 'container' && (
                <>
                  {/* Docker Image */}
                  <div className="space-y-2">
                    <Label htmlFor="sandbox_image" className="text-xs uppercase tracking-wider text-muted-foreground">
                      Docker Image
                    </Label>
                    <Input
                      id="sandbox_image"
                      value={formData.sandbox_image}
                      onChange={(e) => handleChange('sandbox_image', e.target.value)}
                      placeholder="amelia-sandbox:latest"
                      className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
                    />
                  </div>

                  {/* Network Allowlist Toggle */}
                  <div className="flex items-center justify-between rounded-lg border border-border/40 p-4">
                    <div className="space-y-0.5">
                      <Label htmlFor="sandbox_network_allowlist" className="text-sm font-medium">
                        Network Allowlist
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        Restrict outbound network to allowed hosts only.
                      </p>
                    </div>
                    <Switch
                      id="sandbox_network_allowlist"
                      checked={formData.sandbox_network_allowlist_enabled}
                      onCheckedChange={(checked) => handleChange('sandbox_network_allowlist_enabled', checked)}
                    />
                  </div>

                  {/* Allowed Hosts */}
                  {formData.sandbox_network_allowlist_enabled && (
                    <div className="space-y-2">
                      <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                        Allowed Hosts
                      </Label>
                      <HostChipInput
                        hosts={formData.sandbox_network_allowed_hosts}
                        onChange={(hosts) => setFormData((prev) => ({ ...prev, sandbox_network_allowed_hosts: hosts }))}
                      />
                    </div>
                  )}
                </>
              )}
            </TabsContent>
          </Tabs>

          <DialogFooter className="border-t border-border/30 px-6 py-4 gap-2">
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving} className="min-w-[120px]">
              {isSaving ? (
                <span className="flex items-center gap-2">
                  <motion.span
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  >
                    <Cpu className="h-4 w-4" />
                  </motion.span>
                  Saving...
                </span>
              ) : (
                isEditMode ? 'Save Changes' : 'Create Profile'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
