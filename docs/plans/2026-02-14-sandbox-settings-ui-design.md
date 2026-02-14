# Sandbox Settings UI Design

**Issue:** #432 — Add sandbox mode configuration to profile settings UI
**Date:** 2026-02-14

## Problem

Sandbox configuration (container mode, network allowlist) can only be set via direct SQL or API calls. The dashboard profile edit dialog doesn't expose these options.

## Approach: Tabbed Profile Modal

The existing profile edit modal is crowded. Rather than adding more fields to the scroll, restructure the modal into three tabs.

### Tab Layout

```
┌──────────────────────────────────────────┐
│ ⚙ Edit Profile                           │
│ Update the profile configuration...      │
├──────────────────────────────────────────┤
│  General   Agents   Sandbox              │
│  ─────────                               │
│  (active tab content)                    │
├──────────────────────────────────────────┤
│                    [Cancel] [Save Changes]│
└──────────────────────────────────────────┘
```

**General tab:** Profile name, issue tracker, working directory, plan output dir, plan path pattern. The "Advanced Settings" collapsible is removed — plan fields are promoted to always-visible since the tab has room.

**Agents tab:** Bulk apply, primary agents (always visible), utility agents (collapsible). Unchanged from current behavior.

**Sandbox tab:** New sandbox configuration fields with progressive disclosure.

### Sandbox Tab Detail

```
Sandbox Mode
[None              ▾]

── visible when mode = "container" ──

Docker Image
[amelia-sandbox:latest          ]

Network Allowlist    ────── [toggle]

── visible when toggle on ──

Allowed Hosts
┌──────────────────────────────────┐
│ [api.anthropic.com ×]            │
│ [openrouter.ai ×]               │
│ [github.com ×]                   │
│ [type to add... ]               │
└──────────────────────────────────┘
```

Progressive disclosure:
1. Mode = "None" → only the dropdown is shown
2. Mode = "Container" → image field + network allowlist toggle appear
3. Allowlist enabled → hosts chip input appears

Hostname chip input: an `Input` field with "press Enter to add" behavior, rendering `Badge` components with X buttons for existing hosts. Validated on add (alphanumeric, dots, hyphens).

### ProfileCard Indicator

When sandbox mode is "container", the ProfileCard shows a badge next to the driver badge:

```
[cli]  [🔒 Sandbox]
```

`Badge` with `variant="outline"` in green/teal styling.

## Data Flow

### Frontend Types

Add to `dashboard/src/api/settings.ts`:

```typescript
interface SandboxConfig {
  mode: 'none' | 'container';
  image: string;
  network_allowlist_enabled: boolean;
  network_allowed_hosts: string[];
}
```

Add `sandbox?: SandboxConfig` to `Profile`, `ProfileCreate`, `ProfileUpdate`.

### Form State

Flat sandbox fields in `FormData` (not nested):

```typescript
interface FormData {
  // ...existing fields...
  sandbox_mode: 'none' | 'container';
  sandbox_image: string;
  sandbox_network_allowlist_enabled: boolean;
  sandbox_network_allowed_hosts: string[];
}
```

Serialized to `SandboxConfig` on submit; deserialized from `Profile.sandbox` on load.

### Backend

Already complete — `SandboxConfig` type, API routes, and database migration all exist. No backend changes needed.

## New Dependencies

- `@radix-ui/react-tabs` — for the shadcn/ui Tabs component
- Tabs component added via shadcn CLI or manual copy from `/Users/ka/github/ui`

## Files Changed

| File | Change |
|------|--------|
| `dashboard/src/api/settings.ts` | Add `SandboxConfig` interface, add `sandbox` to Profile/ProfileCreate/ProfileUpdate |
| `dashboard/src/components/settings/ProfileEditModal.tsx` | Restructure form into tabs, add sandbox tab content |
| `dashboard/src/components/settings/ProfileCard.tsx` | Add sandbox badge indicator |
| `dashboard/src/components/ui/tabs.tsx` | New file — shadcn Tabs component |
| `dashboard/package.json` | Add `@radix-ui/react-tabs` dependency |

## Testing

- Unit tests for sandbox form validation (hostname pattern)
- Unit tests for ProfileCard sandbox badge rendering
- Existing ProfileEditModal tests updated for tab structure
