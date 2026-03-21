/**
 * PR Auto-Fix configuration section for the profile edit modal.
 *
 * Provides enable/disable toggle, aggressiveness level dropdown,
 * and poll label input for configuring automated PR review fixes.
 */
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { PRAutoFixConfig } from '@/api/settings';

const AGGRESSIVENESS_LEVELS = [
  { value: 'critical' as const, label: 'Critical', description: 'Only fix clear bugs and errors' },
  { value: 'standard' as const, label: 'Standard', description: 'Fix bugs plus style/convention issues' },
  { value: 'thorough' as const, label: 'Thorough', description: 'Address most actionable feedback' },
  { value: 'exemplary' as const, label: 'Exemplary', description: 'Fix everything including suggestions' },
] as const;

const DEFAULT_PR_AUTOFIX_CONFIG: PRAutoFixConfig = {
  aggressiveness: 'standard',
  poll_interval: 60,
  auto_resolve: true,
  resolve_no_changes: true,
  max_iterations: 3,
  commit_prefix: 'fix(review):',
  post_push_cooldown_seconds: 300,
  max_cooldown_seconds: 900,
  poll_label: 'amelia',
  ignore_authors: [],
  confidence_threshold: 0.7,
};

interface PRAutoFixSectionProps {
  enabled: boolean;
  config: PRAutoFixConfig | null;
  onChange: (config: PRAutoFixConfig | null) => void;
}

export function PRAutoFixSection({ enabled, config, onChange }: PRAutoFixSectionProps) {
  const handleToggle = (checked: boolean) => {
    if (checked) {
      onChange({ ...DEFAULT_PR_AUTOFIX_CONFIG });
    } else {
      onChange(null);
    }
  };

  const handleAggressivenessChange = (value: string) => {
    if (config) {
      onChange({
        ...config,
        aggressiveness: value as PRAutoFixConfig['aggressiveness'],
      });
    }
  };

  const handlePollLabelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (config) {
      const val = e.target.value.trim();
      onChange({
        ...config,
        poll_label: val === '' ? null : val,
      });
    }
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-foreground tracking-wide uppercase">
        PR Auto-Fix
      </h3>

      <div className="flex items-center justify-between">
        <Label htmlFor="pr-autofix-toggle" className="text-sm font-medium">
          Enable PR Auto-Fix
        </Label>
        <Switch
          id="pr-autofix-toggle"
          checked={enabled}
          onCheckedChange={handleToggle}
        />
      </div>

      {enabled && config && (
        <div className="space-y-4 pl-1">
          <div className="space-y-2">
            <Label className="text-sm font-medium">Aggressiveness</Label>
            <Select
              value={config.aggressiveness}
              onValueChange={handleAggressivenessChange}
            >
              <SelectTrigger className="bg-background/50">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AGGRESSIVENESS_LEVELS.map((level) => (
                  <SelectItem key={level.value} value={level.value}>
                    <div className="flex flex-col">
                      <span>{level.label}</span>
                      <span className="text-xs text-muted-foreground">
                        {level.description}
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="pr-autofix-poll-label" className="text-sm font-medium">
              Poll Label
            </Label>
            <Input
              id="pr-autofix-poll-label"
              value={config.poll_label ?? ''}
              onChange={handlePollLabelChange}
              placeholder="e.g., auto-fix"
              className="bg-background/50"
            />
          </div>
        </div>
      )}
    </div>
  );
}
