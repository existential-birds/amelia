/**
 * Identity section of the profile detail page.
 *
 * Presentational: renders the profile's identity fields (name, tracker,
 * repository root, plan output directory, plan path pattern) driven entirely
 * by props. State lives in `useProfileForm`; this component only wires it.
 */
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import type { ProfileFormData } from './types';
import type { ValidatableField } from './useProfileForm';

const TRACKER_OPTIONS = [
  { value: 'noop', label: 'None' },
  { value: 'jira', label: 'Jira' },
  { value: 'github', label: 'GitHub' },
];

interface IdentitySectionProps {
  formData: ProfileFormData;
  errors: Record<string, string>;
  isEditMode: boolean;
  onField: (key: keyof ProfileFormData, value: string) => void;
  onBlur: (field: ValidatableField) => void;
}

export function IdentitySection({ formData, errors, isEditMode, onField, onBlur }: IdentitySectionProps) {
  return (
    <div className="space-y-4">
      {/* Profile Name + Tracker */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="id" className="text-xs uppercase tracking-wider text-muted-foreground">
            Profile Name
          </Label>
          <Input
            id="id"
            value={formData.id}
            onChange={(e) => onField('id', e.target.value)}
            onBlur={() => !isEditMode && onBlur('id')}
            disabled={isEditMode}
            placeholder="e.g., dev, prod"
            aria-invalid={!!errors.id}
            className={cn(
              'bg-background/50 hover:border-muted-foreground/30 transition-colors',
              errors.id && 'border-destructive focus-visible:ring-destructive'
            )}
          />
          {errors.id && <p className="text-xs text-destructive">{errors.id}</p>}
        </div>

        <div className="space-y-2">
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">Issue Tracker</Label>
          <Select value={formData.tracker} onValueChange={(v) => onField('tracker', v)}>
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

      {/* Repository Root */}
      <div className="space-y-2">
        <Label htmlFor="repo_root" className="text-xs uppercase tracking-wider text-muted-foreground">
          Repository Root
        </Label>
        <Input
          id="repo_root"
          aria-label="Repository Root"
          value={formData.repo_root}
          onChange={(e) => onField('repo_root', e.target.value)}
          onBlur={() => onBlur('repo_root')}
          placeholder="/path/to/repo"
          aria-invalid={!!errors.repo_root}
          className={cn(
            'bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm',
            errors.repo_root && 'border-destructive focus-visible:ring-destructive'
          )}
        />
        {errors.repo_root && <p className="text-xs text-destructive">{errors.repo_root}</p>}
      </div>

      {/* Plan Output Directory */}
      <div className="space-y-2">
        <Label htmlFor="plan_output_dir" className="text-xs uppercase tracking-wider text-muted-foreground">
          Plan Output Directory
        </Label>
        <Input
          id="plan_output_dir"
          value={formData.plan_output_dir}
          onChange={(e) => onField('plan_output_dir', e.target.value)}
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
          onChange={(e) => onField('plan_path_pattern', e.target.value)}
          placeholder="docs/plans/{date}-{issue_key}.md"
          className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
        />
      </div>
    </div>
  );
}
