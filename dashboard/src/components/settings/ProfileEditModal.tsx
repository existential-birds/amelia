/**
 * Modal for creating and editing profiles.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
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
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { createProfile, updateProfile } from '@/api/settings';
import { ToggleField } from './ToggleField';
import type { Profile, ProfileCreate, ProfileUpdate } from '@/api/settings';
import * as toast from '@/components/Toast';

interface FormData {
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
}

const DEFAULT_FORM_DATA: FormData = {
  id: '',
  driver: 'cli:claude',
  model: 'opus',
  validator_model: 'haiku',
  tracker: 'noop',
  working_dir: '',
  plan_output_dir: 'docs/plans',
  plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
  max_review_iterations: 3,
  max_task_review_iterations: 5,
  auto_approve_reviews: false,
};

interface ProfileEditModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profile: Profile | null;  // null = create mode, Profile = edit mode
  onSaved: () => void;
}

const DRIVER_OPTIONS = [
  { value: 'cli:claude', label: 'Claude CLI' },
  { value: 'api:openrouter', label: 'OpenRouter API' },
];

const TRACKER_OPTIONS = [
  { value: 'noop', label: 'None' },
  { value: 'jira', label: 'Jira' },
  { value: 'github', label: 'GitHub' },
];

/** Default models (Claude CLI) */
const CLAUDE_MODELS = ['opus', 'sonnet', 'haiku'] as const;

/** Model options vary by driver */
const MODEL_OPTIONS_BY_DRIVER: Record<string, readonly string[]> = {
  'cli:claude': CLAUDE_MODELS,
  'api:openrouter': [
    'qwen/qwen3-coder-flash',
    'minimax/minimax-m2',
    'google/gemini-3-flash-preview',
  ],
};

/** Get available models for a driver, with fallback */
const getModelsForDriver = (driver: string): readonly string[] => {
  return MODEL_OPTIONS_BY_DRIVER[driver] ?? CLAUDE_MODELS;
};

/** Validation rules for profile fields */
const validateField = (field: string, value: string): string | null => {
  switch (field) {
    case 'id':
      if (!value.trim()) {
        return 'Profile name is required';
      }
      if (/\s/.test(value)) {
        return 'Profile name cannot contain spaces';
      }
      if (!/^[a-zA-Z0-9_-]+$/.test(value)) {
        return 'Profile name can only contain letters, numbers, underscores, and hyphens';
      }
      return null;
    case 'working_dir':
      if (!value.trim()) {
        return 'Working directory is required';
      }
      return null;
    default:
      return null;
  }
};

/** Convert Profile to FormData for comparison */
const profileToFormData = (profile: Profile): FormData => ({
  id: profile.id,
  driver: profile.driver,
  model: profile.model,
  validator_model: profile.validator_model,
  tracker: profile.tracker,
  working_dir: profile.working_dir,
  plan_output_dir: profile.plan_output_dir,
  plan_path_pattern: profile.plan_path_pattern,
  max_review_iterations: profile.max_review_iterations,
  max_task_review_iterations: profile.max_task_review_iterations,
  auto_approve_reviews: profile.auto_approve_reviews,
});

export function ProfileEditModal({ open, onOpenChange, profile, onSaved }: ProfileEditModalProps) {
  const isEditMode = profile !== null;
  const [isSaving, setIsSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const [formData, setFormData] = useState<FormData>({ ...DEFAULT_FORM_DATA });

  // Track the original state when modal opens for comparison
  const originalFormDataRef = useRef<FormData>({ ...DEFAULT_FORM_DATA });

  useEffect(() => {
    const newFormData = profile ? profileToFormData(profile) : { ...DEFAULT_FORM_DATA };
    setFormData(newFormData);
    originalFormDataRef.current = newFormData;
    // Clear errors when modal opens/closes or profile changes
    setErrors({});
  }, [profile, open]);

  /**
   * Check if the form has unsaved changes by comparing current formData
   * to the original state (profile values for edit mode, defaults for create mode)
   */
  const hasUnsavedChanges = useCallback((): boolean => {
    const original = originalFormDataRef.current;
    return (
      formData.id !== original.id ||
      formData.driver !== original.driver ||
      formData.model !== original.model ||
      formData.validator_model !== original.validator_model ||
      formData.tracker !== original.tracker ||
      formData.working_dir !== original.working_dir ||
      formData.plan_output_dir !== original.plan_output_dir ||
      formData.plan_path_pattern !== original.plan_path_pattern ||
      formData.max_review_iterations !== original.max_review_iterations ||
      formData.max_task_review_iterations !== original.max_task_review_iterations ||
      formData.auto_approve_reviews !== original.auto_approve_reviews
    );
  }, [formData]);

  /**
   * Handle modal close attempt. If there are unsaved changes, prompt user for confirmation.
   */
  const handleClose = useCallback(() => {
    if (hasUnsavedChanges()) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to close?'
      );
      if (!confirmed) {
        return;
      }
    }
    onOpenChange(false);
  }, [hasUnsavedChanges, onOpenChange]);

  /**
   * Handle Dialog onOpenChange - intercept close attempts to check for unsaved changes
   */
  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (!newOpen) {
      // User is trying to close the modal
      handleClose();
    } else {
      onOpenChange(newOpen);
    }
  }, [handleClose, onOpenChange]);

  const handleChange = (key: string, value: string | number | boolean) => {
    setFormData((prev) => {
      const next = { ...prev, [key]: value };
      // When driver changes, reset model/validator_model if not supported
      if (key === 'driver' && typeof value === 'string') {
        const availableModels = getModelsForDriver(value);
        if (!availableModels.includes(prev.model)) {
          next.model = availableModels[0] ?? 'opus';
        }
        if (!availableModels.includes(prev.validator_model)) {
          next.validator_model = availableModels[availableModels.length - 1] ?? 'haiku';
        }
      }
      return next;
    });
    // Clear error for this field when user starts typing
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const handleBlur = (field: string, value: string) => {
    const error = validateField(field, value);
    if (error) {
      setErrors((prev) => ({ ...prev, [field]: error }));
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    // Validate id only in create mode
    if (!isEditMode) {
      const idError = validateField('id', formData.id);
      if (idError) newErrors.id = idError;
    }

    // Validate working_dir always
    const workingDirError = validateField('working_dir', formData.working_dir);
    if (workingDirError) newErrors.working_dir = workingDirError;

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsSaving(true);

    try {
      if (isEditMode) {
        const updates: ProfileUpdate = {
          driver: formData.driver,
          model: formData.model,
          validator_model: formData.validator_model,
          tracker: formData.tracker,
          working_dir: formData.working_dir,
          plan_output_dir: formData.plan_output_dir,
          plan_path_pattern: formData.plan_path_pattern,
          max_review_iterations: formData.max_review_iterations,
          max_task_review_iterations: formData.max_task_review_iterations,
          auto_approve_reviews: formData.auto_approve_reviews,
        };
        await updateProfile(profile!.id, updates);
        toast.success('Profile updated');
      } else {
        const newProfile: ProfileCreate = {
          id: formData.id,
          driver: formData.driver,
          model: formData.model,
          validator_model: formData.validator_model,
          tracker: formData.tracker,
          working_dir: formData.working_dir,
          plan_output_dir: formData.plan_output_dir,
          plan_path_pattern: formData.plan_path_pattern,
          max_review_iterations: formData.max_review_iterations,
          max_task_review_iterations: formData.max_task_review_iterations,
          auto_approve_reviews: formData.auto_approve_reviews,
        };
        await createProfile(newProfile);
        toast.success('Profile created');
      }
      onSaved();
      // Close without checking for unsaved changes since we just saved
      onOpenChange(false);
    } catch {
      toast.error(isEditMode ? 'Failed to update profile' : 'Failed to create profile');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading text-xl tracking-wide">{isEditMode ? 'Edit Profile' : 'Create Profile'}</DialogTitle>
          <DialogDescription>
            {isEditMode
              ? 'Update the profile configuration.'
              : 'Create a new profile for running workflows.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Profile ID - only editable in create mode */}
          <div className="space-y-2">
            <Label htmlFor="id" className="text-xs uppercase tracking-wider text-muted-foreground">Profile Name</Label>
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

          {/* Driver */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">Driver</Label>
            <Select value={formData.driver} onValueChange={(v) => handleChange('driver', v)}>
              <SelectTrigger>
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

          {/* Model */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">Model</Label>
              <Select key={`model-${formData.driver}`} value={formData.model} onValueChange={(v) => handleChange('model', v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {getModelsForDriver(formData.driver).map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">Validator Model</Label>
              <Select key={`validator-${formData.driver}`} value={formData.validator_model} onValueChange={(v) => handleChange('validator_model', v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {getModelsForDriver(formData.driver).map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Tracker */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">Issue Tracker</Label>
            <Select value={formData.tracker} onValueChange={(v) => handleChange('tracker', v)}>
              <SelectTrigger>
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

          {/* Working Directory */}
          <div className="space-y-2">
            <Label htmlFor="working_dir" className="text-xs uppercase tracking-wider text-muted-foreground">Working Directory</Label>
            <Input
              id="working_dir"
              value={formData.working_dir}
              onChange={(e) => handleChange('working_dir', e.target.value)}
              onBlur={(e) => handleBlur('working_dir', e.target.value)}
              placeholder="/path/to/repo"
              aria-invalid={!!errors.working_dir}
              className={cn(
                'bg-background/50 hover:border-muted-foreground/30 transition-colors',
                errors.working_dir && 'border-destructive focus-visible:ring-destructive'
              )}
            />
            {errors.working_dir && (
              <p className="text-xs text-destructive">{errors.working_dir}</p>
            )}
          </div>

          {/* Auto-approve toggle */}
          <ToggleField
            id="auto_approve"
            label="Auto-approve Reviews"
            description="Automatically approve all review iterations"
            checked={formData.auto_approve_reviews}
            onCheckedChange={(checked) => handleChange('auto_approve_reviews', checked)}
          />

          {/* Advanced Settings */}
          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md border border-border/30 bg-background/30 px-4 py-3 text-sm font-medium hover:bg-muted/30 hover:border-border/50 transition-all">
              <span>Advanced Settings</span>
              <ChevronDown
                className={cn(
                  'size-4 transition-transform duration-200',
                  advancedOpen && 'rotate-180'
                )}
              />
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 pt-4">
              {/* Plan Output Directory */}
              <div className="space-y-2">
                <Label htmlFor="plan_output_dir" className="text-xs uppercase tracking-wider text-muted-foreground">Plan Output Directory</Label>
                <Input
                  id="plan_output_dir"
                  value={formData.plan_output_dir}
                  onChange={(e) => handleChange('plan_output_dir', e.target.value)}
                  placeholder="docs/plans"
                  className="bg-background/50 hover:border-muted-foreground/30 transition-colors"
                />
              </div>

              {/* Plan Path Pattern */}
              <div className="space-y-2">
                <Label htmlFor="plan_path_pattern" className="text-xs uppercase tracking-wider text-muted-foreground">Plan Path Pattern</Label>
                <Input
                  id="plan_path_pattern"
                  value={formData.plan_path_pattern}
                  onChange={(e) => handleChange('plan_path_pattern', e.target.value)}
                  placeholder="docs/plans/{date}-{issue_key}.md"
                  className="bg-background/50 hover:border-muted-foreground/30 transition-colors"
                />
              </div>

              {/* Review Iterations */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="max_review_iterations" className="text-xs uppercase tracking-wider text-muted-foreground">Max Review Iterations</Label>
                  <Input
                    id="max_review_iterations"
                    type="number"
                    min={1}
                    value={formData.max_review_iterations}
                    onChange={(e) => handleChange('max_review_iterations', parseInt(e.target.value) || 1)}
                    className="bg-background/50 hover:border-muted-foreground/30 transition-colors"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="max_task_review_iterations" className="text-xs uppercase tracking-wider text-muted-foreground">Max Task Review Iterations</Label>
                  <Input
                    id="max_task_review_iterations"
                    type="number"
                    min={1}
                    value={formData.max_task_review_iterations}
                    onChange={(e) => handleChange('max_task_review_iterations', parseInt(e.target.value) || 1)}
                    className="bg-background/50 hover:border-muted-foreground/30 transition-colors"
                  />
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>

          <DialogFooter className="border-t border-border/30 pt-4 mt-2">
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? 'Saving...' : isEditMode ? 'Save Changes' : 'Create Profile'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
