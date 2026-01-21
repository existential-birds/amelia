/**
 * Modal for creating and editing profiles.
 */
import { useState, useEffect } from 'react';
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
import { Switch } from '@/components/ui/switch';
import { createProfile, updateProfile } from '@/api/settings';
import type { Profile, ProfileCreate, ProfileUpdate } from '@/api/settings';
import * as toast from '@/components/Toast';

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

const MODEL_OPTIONS = ['opus', 'sonnet', 'haiku', 'gpt-4', 'gpt-4o'];

export function ProfileEditModal({ open, onOpenChange, profile, onSaved }: ProfileEditModalProps) {
  const isEditMode = profile !== null;
  const [isSaving, setIsSaving] = useState(false);

  const [formData, setFormData] = useState({
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
  });

  useEffect(() => {
    if (profile) {
      setFormData({
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
    } else {
      // Reset to defaults for create mode
      setFormData({
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
      });
    }
  }, [profile, open]);

  const handleChange = (key: string, value: string | number | boolean) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
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
      onOpenChange(false);
    } catch (err) {
      toast.error(isEditMode ? 'Failed to update profile' : 'Failed to create profile');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Edit Profile' : 'Create Profile'}</DialogTitle>
          <DialogDescription>
            {isEditMode
              ? 'Update the profile configuration.'
              : 'Create a new profile for running workflows.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Profile ID - only editable in create mode */}
          <div className="space-y-2">
            <Label htmlFor="id">Profile Name</Label>
            <Input
              id="id"
              value={formData.id}
              onChange={(e) => handleChange('id', e.target.value)}
              disabled={isEditMode}
              placeholder="e.g., dev, prod"
              required
            />
          </div>

          {/* Driver */}
          <div className="space-y-2">
            <Label>Driver</Label>
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
              <Label>Model</Label>
              <Select value={formData.model} onValueChange={(v) => handleChange('model', v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_OPTIONS.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Validator Model</Label>
              <Select value={formData.validator_model} onValueChange={(v) => handleChange('validator_model', v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_OPTIONS.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Tracker */}
          <div className="space-y-2">
            <Label>Issue Tracker</Label>
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
            <Label htmlFor="working_dir">Working Directory</Label>
            <Input
              id="working_dir"
              value={formData.working_dir}
              onChange={(e) => handleChange('working_dir', e.target.value)}
              placeholder="/path/to/repo"
              required
            />
          </div>

          {/* Auto-approve toggle */}
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="auto_approve">Auto-approve Reviews</Label>
              <p className="text-xs text-muted-foreground">
                Automatically approve all review iterations
              </p>
            </div>
            <Switch
              id="auto_approve"
              checked={formData.auto_approve_reviews}
              onCheckedChange={(checked) => handleChange('auto_approve_reviews', checked)}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
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
