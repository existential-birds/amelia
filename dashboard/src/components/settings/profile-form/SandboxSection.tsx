/**
 * Sandbox section of the profile detail page.
 *
 * Renders the sandbox mode select and the mode-specific blocks:
 * - container: Docker image, network allowlist Switch, and HostChipInput when enabled.
 * - daytona: image, repo URL (with inline error), API URL, target region, and
 *   a responsive resource grid (CPU / Memory / Disk).
 *
 * Extracted from the modal's Sandbox tab. The only behavior change vs. the modal
 * is the Daytona resources grid (now `grid-cols-1 sm:grid-cols-3` so labels never
 * wrap on narrow viewports) and importing the extracted HostChipInput.
 */
import { useState, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { HostChipInput } from './HostChipInput';
import type { SandboxFormData } from './types';

interface SandboxSectionProps {
  sandbox: SandboxFormData;
  errors: Record<string, string>;
  onField: <K extends keyof SandboxFormData>(key: K, value: SandboxFormData[K]) => void;
  onHosts: (hosts: string[]) => void;
}

export function SandboxSection({ sandbox, errors, onField, onHosts }: SandboxSectionProps) {
  // Local string state lets the user clear or partially type a number without
  // immediately snapping to the default. The parent form state is updated with
  // a validated number only on blur.
  const [cpuStr, setCpuStr] = useState(String(sandbox.daytona_cpu));
  const [memStr, setMemStr] = useState(String(sandbox.daytona_memory));
  const [diskStr, setDiskStr] = useState(String(sandbox.daytona_disk));

  // Sync local strings when the parent value changes from outside (e.g. profile switch).
  useEffect(() => { setCpuStr(String(sandbox.daytona_cpu)); }, [sandbox.daytona_cpu]);
  useEffect(() => { setMemStr(String(sandbox.daytona_memory)); }, [sandbox.daytona_memory]);
  useEffect(() => { setDiskStr(String(sandbox.daytona_disk)); }, [sandbox.daytona_disk]);

  return (
    <div className="space-y-4">
      {/* Sandbox Mode */}
      <div className="space-y-2">
        <Label className="text-xs uppercase tracking-wider text-muted-foreground">
          Sandbox Mode
        </Label>
        <Select value={sandbox.mode} onValueChange={(v) => onField('mode', v as SandboxFormData['mode'])}>
          <SelectTrigger className="bg-background/50">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">None</SelectItem>
            <SelectItem value="container">Container</SelectItem>
            <SelectItem value="daytona">Daytona</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          {sandbox.mode === 'none'
            ? 'Code runs directly on the host machine.'
            : sandbox.mode === 'container'
              ? 'Code runs in an isolated Docker container.'
              : 'Code runs in an ephemeral Daytona cloud sandbox.'}
        </p>
      </div>

      {/* Container-specific settings */}
      {sandbox.mode === 'container' && (
        <div className="space-y-2">
          <Label htmlFor="sandbox_image" className="text-xs uppercase tracking-wider text-muted-foreground">
            Docker Image
          </Label>
          <Input
            id="sandbox_image"
            value={sandbox.image}
            onChange={(e) => onField('image', e.target.value)}
            placeholder="amelia-sandbox:latest"
            className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
          />
        </div>
      )}

      {/* Network settings for container mode only */}
      {sandbox.mode === 'container' && (
        <>
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
              checked={sandbox.network_allowlist_enabled}
              onCheckedChange={(checked) => onField('network_allowlist_enabled', checked)}
            />
          </div>

          {/* Allowed Hosts */}
          {sandbox.network_allowlist_enabled && (
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                Allowed Hosts
              </Label>
              <HostChipInput hosts={sandbox.network_allowed_hosts} onChange={onHosts} />
            </div>
          )}
        </>
      )}

      {sandbox.mode === 'daytona' && (
        <>
          {/* Daytona Image */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Daytona Image
            </Label>
            <Input
              value={sandbox.daytona_image}
              onChange={(e) => onField('daytona_image', e.target.value)}
              placeholder="ghcr.io/existential-birds/amelia-sandbox:latest"
              className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
            />
          </div>

          {/* Repo URL */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Repository URL
            </Label>
            <Input
              value={sandbox.repo_url}
              onChange={(e) => onField('repo_url', e.target.value)}
              placeholder="https://github.com/org/repo.git"
              className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
            />
            {errors.sandbox_repo_url && (
              <p className="text-xs text-destructive">{errors.sandbox_repo_url}</p>
            )}
          </div>

          {/* API URL */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Daytona API URL
            </Label>
            <Input
              value={sandbox.daytona_api_url}
              onChange={(e) => onField('daytona_api_url', e.target.value)}
              placeholder="https://app.daytona.io/api"
              className="bg-background/50 hover:border-muted-foreground/30 transition-colors font-mono text-sm"
            />
          </div>

          {/* Target Region */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Target Region
            </Label>
            <Select
              value={sandbox.daytona_target}
              onValueChange={(v) => onField('daytona_target', v)}
            >
              <SelectTrigger className="bg-background/50">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="us">US</SelectItem>
                <SelectItem value="eu">EU</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Resources */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Resources
            </Label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">CPU Cores</Label>
                <Input
                  type="number" min={1} max={16}
                  value={cpuStr}
                  onChange={(e) => setCpuStr(e.target.value)}
                  onBlur={() => {
                    const n = parseInt(cpuStr);
                    const v = (isNaN(n) || n < 1) ? 2 : n;
                    setCpuStr(String(v));
                    onField('daytona_cpu', v);
                  }}
                  className="bg-background/50"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Memory (GB)</Label>
                <Input
                  type="number" min={1} max={64}
                  value={memStr}
                  onChange={(e) => setMemStr(e.target.value)}
                  onBlur={() => {
                    const n = parseInt(memStr);
                    const v = (isNaN(n) || n < 1) ? 4 : n;
                    setMemStr(String(v));
                    onField('daytona_memory', v);
                  }}
                  className="bg-background/50"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Disk (GB)</Label>
                <Input
                  type="number" min={1} max={100}
                  value={diskStr}
                  onChange={(e) => setDiskStr(e.target.value)}
                  onBlur={() => {
                    const n = parseInt(diskStr);
                    const v = (isNaN(n) || n < 1) ? 10 : n;
                    setDiskStr(String(v));
                    onField('daytona_disk', v);
                  }}
                  className="bg-background/50"
                />
              </div>
            </div>
          </div>

          {/* API Key note */}
          <p className="text-xs text-muted-foreground">
            Set the <code className="rounded bg-muted px-1">DAYTONA_API_KEY</code> environment variable before starting Amelia.
          </p>
        </>
      )}
    </div>
  );
}
