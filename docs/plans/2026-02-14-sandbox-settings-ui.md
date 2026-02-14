# Sandbox Settings UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add sandbox mode configuration to the profile settings UI, restructuring the modal into tabs.

**Architecture:** The profile edit modal is restructured from a single scrollable form into three tabs (General, Agents, Sandbox). The Sandbox tab provides progressive disclosure: mode dropdown, then container-specific settings (image, network allowlist with chip-style host input). Frontend types are extended to include `SandboxConfig`. The backend already fully supports sandbox config — no backend changes needed.

**Tech Stack:** React, TypeScript, Radix UI Tabs, shadcn/ui components, Vitest, Testing Library

---

## Tasks

### Task 1: Install Radix Tabs and add Tabs UI component

**Files:**
- Create: `dashboard/src/components/ui/tabs.tsx`
- Modify: `dashboard/package.json`

**Step 1: Install `@radix-ui/react-tabs`**

Run: `cd dashboard && pnpm add @radix-ui/react-tabs`

**Step 2: Create the Tabs component**

Create `dashboard/src/components/ui/tabs.tsx`:

```tsx
"use client"

import * as React from "react"
import * as TabsPrimitive from "@radix-ui/react-tabs"

import { cn } from "@/lib/utils"

function Tabs({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function TabsList({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "inline-flex h-9 w-fit items-center justify-center rounded-lg bg-muted p-[3px] text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap transition-all",
        "text-foreground/60 hover:text-foreground",
        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:outline-ring focus-visible:ring-[3px] focus-visible:outline-1",
        "disabled:pointer-events-none disabled:opacity-50",
        "data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("flex-1 outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
```

**Step 3: Commit**

```bash
git add dashboard/package.json dashboard/pnpm-lock.yaml dashboard/src/components/ui/tabs.tsx
git commit -m "feat(dashboard): add Tabs component from shadcn/ui"
```

---

### Task 2: Add `SandboxConfig` type and extend Profile interfaces

**Files:**
- Modify: `dashboard/src/api/settings.ts`
- Modify: `dashboard/src/__tests__/fixtures.ts`

**Step 1: Write the failing test**

Add to `dashboard/src/__tests__/fixtures.ts` — update `createMockProfile` to include sandbox and verify the type compiles. First, update the imports and the factory:

Actually, this is a type-level change. We add the interface and update usages. The "test" is that `pnpm type-check` passes.

**Step 2: Add `SandboxConfig` interface**

In `dashboard/src/api/settings.ts`, add above the `Profile` interface:

```typescript
/**
 * Sandbox execution configuration for a profile.
 */
export interface SandboxConfig {
  mode: 'none' | 'container';
  image: string;
  network_allowlist_enabled: boolean;
  network_allowed_hosts: string[];
}
```

**Step 3: Add `sandbox` field to `Profile`, `ProfileCreate`, `ProfileUpdate`**

In `Profile`:
```typescript
export interface Profile {
  id: string;
  tracker: string;
  working_dir: string;
  plan_output_dir: string;
  plan_path_pattern: string;
  agents: Record<string, AgentConfig>;
  sandbox?: SandboxConfig;
  is_active: boolean;
}
```

In `ProfileCreate`:
```typescript
export interface ProfileCreate {
  id: string;
  tracker?: string;
  working_dir: string;
  plan_output_dir?: string;
  plan_path_pattern?: string;
  agents: Record<string, AgentConfigInput>;
  sandbox?: SandboxConfig;
}
```

In `ProfileUpdate`:
```typescript
export interface ProfileUpdate {
  tracker?: string;
  working_dir?: string;
  plan_output_dir?: string;
  plan_path_pattern?: string;
  agents?: Record<string, AgentConfigInput>;
  sandbox?: SandboxConfig;
}
```

**Step 4: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: PASS (sandbox is optional so existing code compiles)

**Step 5: Commit**

```bash
git add dashboard/src/api/settings.ts
git commit -m "feat(dashboard): add SandboxConfig type to profile interfaces"
```

---

### Task 3: Add sandbox badge to ProfileCard

**Files:**
- Modify: `dashboard/src/components/settings/ProfileCard.tsx`
- Create: `dashboard/src/components/settings/__tests__/ProfileCard.test.tsx`

**Step 1: Write the failing tests**

Create `dashboard/src/components/settings/__tests__/ProfileCard.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProfileCard } from '../ProfileCard';
import { createMockProfile } from '@/__tests__/fixtures';

describe('ProfileCard sandbox indicator', () => {
  const defaultProps = {
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onActivate: vi.fn(),
  };

  it('should not show sandbox badge when sandbox mode is none', () => {
    const profile = createMockProfile({
      sandbox: { mode: 'none', image: 'amelia-sandbox:latest', network_allowlist_enabled: false, network_allowed_hosts: [] },
    });

    render(<ProfileCard profile={profile} {...defaultProps} />);
    expect(screen.queryByText('Sandbox')).not.toBeInTheDocument();
  });

  it('should not show sandbox badge when sandbox is undefined', () => {
    const profile = createMockProfile();

    render(<ProfileCard profile={profile} {...defaultProps} />);
    expect(screen.queryByText('Sandbox')).not.toBeInTheDocument();
  });

  it('should show sandbox badge when sandbox mode is container', () => {
    const profile = createMockProfile({
      sandbox: { mode: 'container', image: 'amelia-sandbox:latest', network_allowlist_enabled: true, network_allowed_hosts: ['api.anthropic.com'] },
    });

    render(<ProfileCard profile={profile} {...defaultProps} />);
    expect(screen.getByText('Sandbox')).toBeInTheDocument();
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm vitest run src/components/settings/__tests__/ProfileCard.test.tsx`
Expected: FAIL — ProfileCard doesn't render a "Sandbox" badge yet.

**Step 3: Add sandbox badge to ProfileCard**

In `ProfileCard.tsx`, add the `Shield` import from lucide-react:

```typescript
import {
  Pencil,
  Trash2,
  Star,
  Folder,
  Terminal,
  Cloud,
  Brain,
  Code,
  Search,
  MoreHorizontal,
  Shield,
} from 'lucide-react';
```

Then in the `CardContent`, after the driver badge `<div>` (around line 206), add:

```tsx
{/* Sandbox indicator */}
{profile.sandbox?.mode === 'container' && (
  <Badge
    variant="outline"
    className="text-xs bg-emerald-500/10 text-emerald-500 border-emerald-500/30"
  >
    <Shield className="mr-1 h-3 w-3" />
    Sandbox
  </Badge>
)}
```

Insert this badge inside the existing `<div className="flex items-center gap-2">` that contains the driver badge, so both badges sit on the same row.

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm vitest run src/components/settings/__tests__/ProfileCard.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/settings/ProfileCard.tsx dashboard/src/components/settings/__tests__/ProfileCard.test.tsx
git commit -m "feat(dashboard): add sandbox badge to ProfileCard"
```

---

### Task 4: Restructure ProfileEditModal into tabs

This is the largest task. It restructures the existing form into three tabs without changing behavior.

**Files:**
- Modify: `dashboard/src/components/settings/ProfileEditModal.tsx`

**Step 1: Add imports**

Add to the imports at the top of `ProfileEditModal.tsx`:

```typescript
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Shield } from 'lucide-react';
```

**Step 2: Restructure the form body into tabs**

Replace the form body (the `<form>` contents between the header and the `<DialogFooter>`) with a tabbed layout. The structure is:

```tsx
<form onSubmit={handleSubmit} className="flex flex-col h-full">
  <Tabs defaultValue="general" className="flex-1 px-6 pt-4">
    <TabsList className="w-full justify-start">
      <TabsTrigger value="general">General</TabsTrigger>
      <TabsTrigger value="agents">Agents</TabsTrigger>
      <TabsTrigger value="sandbox">Sandbox</TabsTrigger>
    </TabsList>

    {/* General Tab */}
    <TabsContent value="general" className="space-y-4 pt-4">
      {/* Profile Name + Tracker (2-col grid) — moved from top of old form */}
      {/* Working Directory — moved from old form */}
      {/* Plan Output Directory — promoted from Advanced Settings */}
      {/* Plan Path Pattern — promoted from Advanced Settings */}
    </TabsContent>

    {/* Agents Tab */}
    <TabsContent value="agents" className="space-y-4 pt-4">
      {/* Divider "Agent Configuration" — removed, tab title is sufficient */}
      {/* BulkApply — moved here */}
      {/* Primary Agents — moved here */}
      {/* Utility Agents collapsible — moved here */}
    </TabsContent>

    {/* Sandbox Tab */}
    <TabsContent value="sandbox" className="space-y-4 pt-4">
      {/* Placeholder: "Coming soon" or empty for now — filled in Task 5 */}
      <p className="text-sm text-muted-foreground">No sandbox configuration.</p>
    </TabsContent>
  </Tabs>

  <DialogFooter className="border-t border-border/30 px-6 py-4 gap-2">
    {/* Cancel + Save buttons — unchanged */}
  </DialogFooter>
</form>
```

The key changes:
- Remove the "Agent Configuration" divider (the tab name replaces it)
- Remove the "Advanced Settings" collapsible — plan fields go directly in General tab
- Move all agent-related JSX into the Agents tab
- Move basic profile fields into General tab
- Footer stays outside tabs so Save/Cancel are always visible

**Step 3: Run existing tests**

Run: `cd dashboard && pnpm vitest run src/components/settings/__tests__/ProfileEditModal.integration.test.tsx`
Expected: The existing tests should still pass — they look for text content that's now inside the Agents tab. Since Radix Tabs renders all tab content in the DOM (just hidden), queries should still find elements. If tests fail because agents content isn't visible by default, add `defaultValue="agents"` or click the Agents tab in test setup.

**Step 4: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/settings/ProfileEditModal.tsx
git commit -m "refactor(dashboard): restructure profile edit modal into tabs"
```

---

### Task 5: Implement the Sandbox tab content

**Files:**
- Modify: `dashboard/src/components/settings/ProfileEditModal.tsx`
- Create: `dashboard/src/components/settings/__tests__/SandboxTab.test.tsx`

**Step 1: Write the failing tests**

Create `dashboard/src/components/settings/__tests__/SandboxTab.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileEditModal } from '../ProfileEditModal';
import { useModelsStore } from '@/store/useModelsStore';

vi.mock('@/store/useModelsStore');
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: [],
    addRecentModel: vi.fn(),
  }),
}));

describe('Sandbox tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const state = {
      models: [],
      providers: [],
      isLoading: false,
      error: null,
      lastFetched: Date.now(),
      fetchModels: vi.fn().mockResolvedValue(undefined),
      refreshModels: vi.fn().mockResolvedValue(undefined),
      getModelsForAgent: vi.fn().mockReturnValue([]),
    };
    vi.mocked(useModelsStore).mockImplementation(
      (selector?: (s: typeof state) => unknown) => selector ? selector(state) : state
    );
  });

  const renderWithSandboxTab = async (profile: Parameters<typeof ProfileEditModal>[0]['profile'] = null) => {
    const user = userEvent.setup();
    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={profile}
        onSaved={vi.fn()}
      />
    );
    // Click the Sandbox tab
    await user.click(screen.getByRole('tab', { name: /sandbox/i }));
    return user;
  };

  it('should show sandbox mode dropdown defaulting to None', async () => {
    await renderWithSandboxTab();
    expect(screen.getByText('None')).toBeInTheDocument();
  });

  it('should not show container fields when mode is None', async () => {
    await renderWithSandboxTab();
    expect(screen.queryByLabelText(/docker image/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/network allowlist/i)).not.toBeInTheDocument();
  });

  it('should show container fields when mode is Container', async () => {
    const profile = {
      id: 'test',
      tracker: 'noop',
      working_dir: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {},
      sandbox: {
        mode: 'container' as const,
        image: 'amelia-sandbox:latest',
        network_allowlist_enabled: false,
        network_allowed_hosts: [],
      },
    };

    await renderWithSandboxTab(profile);
    expect(screen.getByDisplayValue('amelia-sandbox:latest')).toBeInTheDocument();
  });

  it('should show allowed hosts when network allowlist is enabled', async () => {
    const profile = {
      id: 'test',
      tracker: 'noop',
      working_dir: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {},
      sandbox: {
        mode: 'container' as const,
        image: 'amelia-sandbox:latest',
        network_allowlist_enabled: true,
        network_allowed_hosts: ['api.anthropic.com', 'github.com'],
      },
    };

    await renderWithSandboxTab(profile);
    expect(screen.getByText('api.anthropic.com')).toBeInTheDocument();
    expect(screen.getByText('github.com')).toBeInTheDocument();
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm vitest run src/components/settings/__tests__/SandboxTab.test.tsx`
Expected: FAIL

**Step 3: Add sandbox fields to FormData and form state**

In `ProfileEditModal.tsx`, update `FormData`:

```typescript
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
```

Update `DEFAULT_FORM_DATA`:

```typescript
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
```

Update `profileToFormData`:

```typescript
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
```

Update `hasUnsavedChanges` to include sandbox fields:

```typescript
if (
  formData.sandbox_mode !== original.sandbox_mode ||
  formData.sandbox_image !== original.sandbox_image ||
  formData.sandbox_network_allowlist_enabled !== original.sandbox_network_allowlist_enabled ||
  JSON.stringify(formData.sandbox_network_allowed_hosts) !== JSON.stringify(original.sandbox_network_allowed_hosts)
) {
  return true;
}
```

Update `handleSubmit` to serialize sandbox into the API payload. In the `formAgentsToApi` area, add a helper:

```typescript
const formSandboxToApi = (): SandboxConfig => ({
  mode: formData.sandbox_mode,
  image: formData.sandbox_image,
  network_allowlist_enabled: formData.sandbox_network_allowlist_enabled,
  network_allowed_hosts: formData.sandbox_network_allowed_hosts,
});
```

Then include `sandbox: formSandboxToApi()` in both the `ProfileCreate` and `ProfileUpdate` objects in `handleSubmit`.

Import `SandboxConfig` type:

```typescript
import type { Profile, ProfileCreate, ProfileUpdate, SandboxConfig } from '@/api/settings';
```

**Step 4: Implement the Sandbox tab JSX**

Replace the placeholder in the Sandbox `TabsContent` with:

```tsx
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
```

Add the `Switch` import:

```typescript
import { Switch } from '@/components/ui/switch';
```

**Step 5: Implement the `HostChipInput` component**

Add this component inside `ProfileEditModal.tsx` (above the main component, after the helper functions):

```tsx
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
```

Add `X` to the lucide-react imports:

```typescript
import { ..., X } from 'lucide-react';
```

**Step 6: Run tests to verify they pass**

Run: `cd dashboard && pnpm vitest run src/components/settings/__tests__/SandboxTab.test.tsx`
Expected: PASS

**Step 7: Run all settings tests**

Run: `cd dashboard && pnpm vitest run src/components/settings/__tests__/`
Expected: PASS (both SandboxTab and ProfileEditModal integration tests)

**Step 8: Commit**

```bash
git add dashboard/src/components/settings/ProfileEditModal.tsx dashboard/src/components/settings/__tests__/SandboxTab.test.tsx
git commit -m "feat(dashboard): implement sandbox tab in profile edit modal"
```

---

### Task 6: Add HostChipInput tests

**Files:**
- Create: `dashboard/src/components/settings/__tests__/HostChipInput.test.tsx`

**Step 1: Write the tests**

Create `dashboard/src/components/settings/__tests__/HostChipInput.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileEditModal } from '../ProfileEditModal';
import { useModelsStore } from '@/store/useModelsStore';

vi.mock('@/store/useModelsStore');
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: [],
    addRecentModel: vi.fn(),
  }),
}));

describe('HostChipInput via Sandbox tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const state = {
      models: [],
      providers: [],
      isLoading: false,
      error: null,
      lastFetched: Date.now(),
      fetchModels: vi.fn().mockResolvedValue(undefined),
      refreshModels: vi.fn().mockResolvedValue(undefined),
      getModelsForAgent: vi.fn().mockReturnValue([]),
    };
    vi.mocked(useModelsStore).mockImplementation(
      (selector?: (s: typeof state) => unknown) => selector ? selector(state) : state
    );
  });

  const renderSandboxTab = async () => {
    const user = userEvent.setup();
    const profile = {
      id: 'test',
      tracker: 'noop',
      working_dir: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {},
      sandbox: {
        mode: 'container' as const,
        image: 'amelia-sandbox:latest',
        network_allowlist_enabled: true,
        network_allowed_hosts: ['api.anthropic.com'],
      },
    };
    render(
      <ProfileEditModal open={true} onOpenChange={vi.fn()} profile={profile} onSaved={vi.fn()} />
    );
    await user.click(screen.getByRole('tab', { name: /sandbox/i }));
    return user;
  };

  it('should add a host when pressing Enter', async () => {
    const user = await renderSandboxTab();
    const input = screen.getByPlaceholderText('api.example.com');
    await user.type(input, 'openrouter.ai{Enter}');
    expect(screen.getByText('openrouter.ai')).toBeInTheDocument();
  });

  it('should add a host when clicking Add button', async () => {
    const user = await renderSandboxTab();
    const input = screen.getByPlaceholderText('api.example.com');
    await user.type(input, 'github.com');
    await user.click(screen.getByRole('button', { name: /^add$/i }));
    expect(screen.getByText('github.com')).toBeInTheDocument();
  });

  it('should remove a host when clicking the remove button', async () => {
    const user = await renderSandboxTab();
    expect(screen.getByText('api.anthropic.com')).toBeInTheDocument();
    await user.click(screen.getByLabelText('Remove api.anthropic.com'));
    expect(screen.queryByText('api.anthropic.com')).not.toBeInTheDocument();
  });

  it('should show error for invalid hostname', async () => {
    const user = await renderSandboxTab();
    const input = screen.getByPlaceholderText('api.example.com');
    await user.type(input, 'not a valid host!{Enter}');
    expect(screen.getByText('Invalid hostname')).toBeInTheDocument();
  });

  it('should show error for duplicate hostname', async () => {
    const user = await renderSandboxTab();
    const input = screen.getByPlaceholderText('api.example.com');
    await user.type(input, 'api.anthropic.com{Enter}');
    expect(screen.getByText('Host already added')).toBeInTheDocument();
  });
});
```

**Step 2: Run tests**

Run: `cd dashboard && pnpm vitest run src/components/settings/__tests__/HostChipInput.test.tsx`
Expected: PASS

**Step 3: Commit**

```bash
git add dashboard/src/components/settings/__tests__/HostChipInput.test.tsx
git commit -m "test(dashboard): add HostChipInput tests for sandbox tab"
```

---

### Task 7: Full integration test and cleanup

**Files:**
- Modify: `dashboard/src/__tests__/fixtures.ts` (add sandbox to mock profile)

**Step 1: Update fixtures to include sandbox**

In `dashboard/src/__tests__/fixtures.ts`, update the `createMockProfile` function. Import `SandboxConfig`:

```typescript
import { type Profile, type SandboxConfig } from '../api/settings';
```

No changes needed to the factory — `sandbox` is optional on Profile so existing calls still work. But add a convenience factory:

```typescript
export function createMockSandboxConfig(overrides?: Partial<SandboxConfig>): SandboxConfig {
  return {
    mode: 'none',
    image: 'amelia-sandbox:latest',
    network_allowlist_enabled: false,
    network_allowed_hosts: [],
    ...overrides,
  };
}
```

**Step 2: Run the full dashboard test suite**

Run: `cd dashboard && pnpm test:run`
Expected: All tests PASS

**Step 3: Run lint and type-check**

Run: `cd dashboard && pnpm lint && pnpm type-check`
Expected: PASS

**Step 4: Build the dashboard**

Run: `cd dashboard && pnpm build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add dashboard/src/__tests__/fixtures.ts
git commit -m "test(dashboard): add sandbox fixture factory"
```

---

### Task 8: Visual verification

**Files:** None (manual verification)

**Step 1: Start the backend and dashboard dev server**

Run (in separate terminals):
- `uv run amelia dev` (backend on 8420)
- `cd dashboard && pnpm dev` (frontend on 8421)

**Step 2: Verify General tab**

Navigate to `http://localhost:8421/settings`. Edit a profile. Confirm:
- Three tabs visible: General, Agents, Sandbox
- General tab shows: Profile name, tracker, working dir, plan output dir, plan path pattern
- No "Advanced Settings" collapsible

**Step 3: Verify Agents tab**

Click the Agents tab. Confirm:
- Bulk apply, primary agents, utility agents all present and working
- Agent driver/model changes work

**Step 4: Verify Sandbox tab**

Click the Sandbox tab. Confirm:
- Mode dropdown defaults to "None"
- Selecting "Container" reveals image field and network allowlist toggle
- Enabling network allowlist reveals host chip input
- Adding/removing hosts works
- Saving persists sandbox config

**Step 5: Verify ProfileCard badge**

After saving a profile with Container mode, confirm the card shows the "Sandbox" badge.

---
