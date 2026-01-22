/**
 * Form component for editing server settings.
 */
import { useState, useEffect } from 'react';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { ToggleField } from './ToggleField';
import type { ServerSettings } from '@/api/settings';

interface ServerSettingsFormProps {
  settings: ServerSettings;
  onSave: (updates: Partial<ServerSettings>) => Promise<void>;
  isSaving: boolean;
}

const RETENTION_OPTIONS = [7, 14, 30, 60, 90];
const CONCURRENT_OPTIONS = [1, 3, 5, 10, 20];

export function ServerSettingsForm({ settings, onSave, isSaving }: ServerSettingsFormProps) {
  const [formData, setFormData] = useState(settings);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setFormData(settings);
    setHasChanges(false);
  }, [settings]);

  const handleChange = <K extends keyof ServerSettings>(key: K, value: ServerSettings[K]) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleReset = () => {
    setFormData(settings);
    setHasChanges(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const updates: Partial<ServerSettings> = {};
    for (const key of Object.keys(formData) as (keyof ServerSettings)[]) {
      if (formData[key] !== settings[key]) {
        (updates as Record<string, unknown>)[key] = formData[key];
      }
    }
    await onSave(updates);
    setHasChanges(false);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {/* Retention Policies */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Retention Policies</h3>
          <p className="text-sm text-muted-foreground">
            Configure how long to keep logs, traces, and checkpoints.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="log_retention_days">Log Retention</Label>
            <Select
              value={String(formData.log_retention_days)}
              onValueChange={(v) => handleChange('log_retention_days', Number(v))}
            >
              <SelectTrigger id="log_retention_days">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RETENTION_OPTIONS.map((days) => (
                  <SelectItem key={days} value={String(days)}>
                    {days} days
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="trace_retention_days">Trace Retention</Label>
            <Select
              value={String(formData.trace_retention_days)}
              onValueChange={(v) => handleChange('trace_retention_days', Number(v))}
            >
              <SelectTrigger id="trace_retention_days">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">Disabled</SelectItem>
                {RETENTION_OPTIONS.map((days) => (
                  <SelectItem key={days} value={String(days)}>
                    {days} days
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </section>

      {/* Execution Limits */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Execution Limits</h3>
          <p className="text-sm text-muted-foreground">
            Control concurrent workflow execution.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="max_concurrent">Max Concurrent Workflows</Label>
          <Select
            value={String(formData.max_concurrent)}
            onValueChange={(v) => handleChange('max_concurrent', Number(v))}
          >
            <SelectTrigger id="max_concurrent" className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CONCURRENT_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </section>

      {/* Debugging */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Debugging</h3>
          <p className="text-sm text-muted-foreground">
            Options for debugging workflow execution.
          </p>
        </div>

        <ToggleField
          id="stream_tool_results"
          label="Stream Tool Results"
          description="Enable streaming of tool results to dashboard WebSocket."
          checked={formData.stream_tool_results}
          onCheckedChange={(checked) => handleChange('stream_tool_results', checked)}
        />
      </section>

      {/* Footer */}
      {hasChanges && (
        <div className="sticky bottom-0 flex items-center justify-between border-t bg-background pt-4">
          <p className="text-sm text-muted-foreground">You have unsaved changes</p>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={handleReset}>
              Reset
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </div>
      )}
    </form>
  );
}
