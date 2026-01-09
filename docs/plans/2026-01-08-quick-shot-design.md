# Quick Shot Feature Design

## Overview

Add a "Quick Shot" modal to the dashboard for starting noop tracker workflows directly from the UI. Replaces the "Roundtable" placeholder in the sidebar.

---

## Design Direction: High-Voltage Command Console

**Concept**: The Quick Shot modal is a power-user command console for launching workflows instantly. The design leans into the "lightning strike" metaphor with an industrial, high-voltage terminal aesthetic that feels fast, precise, and slightly dangerous.

**Core aesthetic principles**:
- **High-voltage industrial** - Warning stripe accents, terminal-style data entry
- **Precision power** - Sharp edges, deliberate animations, gold electrical glow
- **Command terminal** - Monospace input styling, structured field layout
- **Instant action** - Staggered reveals, charging animations, satisfying launch feedback

**What makes it memorable**: The modal opens with a staggered cascade reveal like a power-up sequence. The "Start Workflow" button has an electric charge animation that builds as you fill required fields. On launch, a gold lightning ripple emanates from the button.

---

## User Flow

1. User clicks "Quick Shot" (lightning icon) in sidebar under TOOLS
2. Modal opens with staggered field reveal animation (50ms cascade)
3. User fills required fields - validation feedback is immediate
4. "Start Workflow" button charges with gold glow as fields complete
5. On click, lightning ripple animation + haptic-style pulse
6. API creates workflow, modal closes with fast fade
7. Toast notification confirms with workflow ID link

---

## Visual Design

### Modal Structure

```
╔═══════════════════════════════════════════════════════════╗
║  ⚡ QUICK SHOT                                       [×]  ║
║═══════════════════════════════════════════════════════════║
║                                                           ║
║  ┌─ TASK IDENTIFIER ─────────────────────────────────┐   ║
║  │ TASK-001                                    [✓]   │   ║
║  └───────────────────────────────────────────────────┘   ║
║                                                           ║
║  ┌─ WORKTREE PATH ───────────────────────────────────┐   ║
║  │ /Users/me/projects/my-repo                        │   ║
║  └───────────────────────────────────────────────────┘   ║
║                                                           ║
║  ┌─ PROFILE ─────────────────────────────────────────┐   ║
║  │ noop-local                               [OPT]    │   ║
║  └───────────────────────────────────────────────────┘   ║
║                                                           ║
║  ┌─ TASK TITLE ──────────────────────────────────────┐   ║
║  │ Add logout button to navbar                       │   ║
║  └───────────────────────────────────────────────────┘   ║
║                                                           ║
║  ┌─ DESCRIPTION ─────────────────────────────────────┐   ║
║  │ Add a logout button to the top navigation bar     │   ║
║  │ that clears the session and redirects to login... │   ║
║  │                                                   │   ║
║  └───────────────────────────────────────────────────┘   ║
║                                                           ║
║      ┌─────────┐    ┌═══════════════════════════════┐   ║
║      │ CANCEL  │    ║ ⚡ START WORKFLOW             ║   ║
║      └─────────┘    └═══════════════════════════════┘   ║
║                          ▔▔▔▔▔▔ gold charge bar         ║
╚═══════════════════════════════════════════════════════════╝
```

### Color Palette (using existing tokens)

| Element | Token | Purpose |
|---------|-------|---------|
| Modal background | `--card` | Elevated dark surface |
| Modal border | `--border` + gold accent | Industrial frame |
| Title text | `--primary` (gold) | High-voltage header |
| Field labels | `--muted-foreground` | Subdued terminal labels |
| Input background | `--background` | Sunken data entry |
| Input border | `--input` → `--primary` on focus | Electric focus state |
| Input text | `--foreground` | Clear monospace data |
| Validation success | `--status-completed` (green) | Field verified |
| Validation error | `--destructive` (red) | Entry error |
| Cancel button | `--secondary` | Subdued action |
| Start button | `--primary` with glow | Power action |

### Typography

| Element | Font | Style |
|---------|------|-------|
| Modal title | `--font-display` (Bebas Neue) | 24px, tracking-wider, uppercase |
| Field labels | `--font-heading` (Barlow Condensed) | 11px, uppercase, letter-spacing: 0.1em |
| Input text | `--font-mono` (IBM Plex Mono) | 14px, normal weight |
| Helper text | `--font-body` (Source Sans 3) | 12px, muted-foreground |
| Button text | `--font-heading` (Barlow Condensed) | 14px, semibold, uppercase |

### Input Field Styling

```css
/* Terminal-style input with inset shadow */
.quick-shot-input {
  background: var(--background);
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  padding: 0.75rem 1rem;

  /* Subtle inner shadow for depth */
  box-shadow: inset 0 2px 4px oklch(from var(--background) calc(l - 0.05) c h);

  transition: border-color var(--duration-fast),
              box-shadow var(--duration-fast);
}

.quick-shot-input:focus {
  border-color: var(--primary);
  box-shadow:
    inset 0 2px 4px oklch(from var(--background) calc(l - 0.05) c h),
    0 0 0 3px oklch(from var(--primary) l c h / 0.15);
  outline: none;
}

/* Floating label effect */
.quick-shot-label {
  font-family: var(--font-heading);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--muted-foreground);
  position: absolute;
  top: -8px;
  left: 12px;
  background: var(--card);
  padding: 0 4px;
}
```

---

## Animations & Micro-interactions

### Modal Open - Cascade Reveal

Fields appear in a staggered cascade, top to bottom, creating a "power-up sequence" effect.

```css
@keyframes field-reveal {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.quick-shot-field {
  animation: field-reveal 200ms ease-out both;
}

.quick-shot-field:nth-child(1) { animation-delay: 0ms; }
.quick-shot-field:nth-child(2) { animation-delay: 50ms; }
.quick-shot-field:nth-child(3) { animation-delay: 100ms; }
.quick-shot-field:nth-child(4) { animation-delay: 150ms; }
.quick-shot-field:nth-child(5) { animation-delay: 200ms; }
```

### Button Charge State

As required fields are filled, the Start Workflow button "charges" with increasing glow intensity.

```css
@keyframes charge-pulse {
  0%, 100% {
    box-shadow: 0 0 8px oklch(from var(--primary) l c h / 0.4);
  }
  50% {
    box-shadow: 0 0 16px oklch(from var(--primary) l c h / 0.6);
  }
}

.quick-shot-submit {
  transition: all var(--duration-normal);
}

.quick-shot-submit:disabled {
  opacity: 0.5;
  box-shadow: none;
}

.quick-shot-submit:not(:disabled) {
  animation: charge-pulse 2s ease-in-out infinite;
}

.quick-shot-submit:not(:disabled):hover {
  box-shadow: 0 0 24px oklch(from var(--primary) l c h / 0.8);
  transform: scale(1.02);
}
```

### Submit - Lightning Ripple

On click, a gold ripple emanates from the button center.

```css
@keyframes lightning-ripple {
  0% {
    transform: scale(0);
    opacity: 1;
  }
  100% {
    transform: scale(2.5);
    opacity: 0;
  }
}

.quick-shot-submit::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: radial-gradient(
    circle at center,
    oklch(from var(--primary) l c h / 0.4) 0%,
    transparent 70%
  );
  transform: scale(0);
  opacity: 0;
  pointer-events: none;
}

.quick-shot-submit.launching::after {
  animation: lightning-ripple 400ms ease-out;
}
```

### Loading State - Electric Pulse

During API submission, the button shows an electric pulse with scanning line.

```css
@keyframes scan-line {
  0% { left: -100%; }
  100% { left: 100%; }
}

.quick-shot-submit.loading {
  position: relative;
  overflow: hidden;
}

.quick-shot-submit.loading::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent 0%,
    oklch(from var(--primary-foreground) l c h / 0.3) 50%,
    transparent 100%
  );
  animation: scan-line 1s ease-in-out infinite;
}
```

---

## Form Fields

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| Task ID | Input | Yes | Non-empty, alphanumeric + hyphens |
| Worktree Path | Input | Yes | Absolute path (starts with `/`) |
| Profile | Input | No | Optional, from settings.amelia.yaml |
| Title | Input | Yes | Non-empty, max 500 chars |
| Description | Textarea | No | Defaults to title if empty, max 5000 chars |

### Validation Behavior

- **Real-time validation** on blur and on change (debounced 300ms)
- **Error state**: Red border + inline error message below field
- **Success state**: Subtle green checkmark indicator inside input
- **Required indicator**: Gold asterisk (*) after label text

---

## API Integration

**New API client method:**
```typescript
async createWorkflow(request: {
  issue_id: string;
  worktree_path: string;
  profile?: string;
  task_title: string;
  task_description?: string;
}): Promise<{ workflow_id: string }>
```

**Request:** `POST /api/workflows`
```json
{
  "issue_id": "TASK-001",
  "worktree_path": "/Users/me/projects/repo",
  "profile": "noop-local",
  "task_title": "Add logout button",
  "task_description": "Add a logout button..."
}
```

**Response:** `{ "workflow_id": "wf-abc123" }`

---

## Error Handling

| Scenario | UI Response |
|----------|-------------|
| Validation error | Inline red text below field, field border turns red |
| API error (4xx) | Toast notification with error message |
| API error (5xx) | Toast with "Server error. Please try again." |
| Network error | Toast with "Connection failed. Check your network." |
| Loading state | Button text → "LAUNCHING...", scan-line animation |
| Success | Toast with "Workflow started" + link to `/workflows/{id}` |

---

## Components

**shadcn/ui components used:**
- `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogFooter`
- `Input`, `Textarea`, `Label`
- `Button`

**Custom styling via Tailwind classes + CSS variables** (no new CSS files needed).

---

## Files to Change

**New files:**
| File | Purpose |
|------|---------|
| `dashboard/src/components/QuickShotModal.tsx` | Modal dialog with form and animations |
| `dashboard/src/components/QuickShotModal.test.tsx` | Unit tests for form validation |

**Modified files:**
| File | Changes |
|------|---------|
| `dashboard/src/components/DashboardSidebar.tsx` | Replace Roundtable with Quick Shot trigger |
| `dashboard/src/api/client.ts` | Add `createWorkflow()` method |
| `dashboard/src/api/client.test.ts` | Add tests for `createWorkflow()` |
| `dashboard/src/types/index.ts` | Add `task_title`, `task_description` to `StartWorkflowRequest` |
| `dashboard/src/styles/globals.css` | Add Quick Shot keyframe animations |

---

## Accessibility

- **Focus management**: Focus moves to first input on open, returns to trigger on close
- **Keyboard navigation**: Tab through fields, Escape closes modal
- **ARIA labels**: All inputs properly labeled, error messages linked via `aria-describedby`
- **Reduced motion**: Animations respect `prefers-reduced-motion` (already in globals.css)
- **Color contrast**: All text meets WCAG AA contrast requirements

---

## Testing

**Unit tests:**
- Form validation for all fields (empty, invalid format, max length)
- Submit button disabled until required fields valid
- Error message display on validation failure
- API error handling and toast display

**Integration tests:**
- Modal open/close behavior
- Form submission flow
- Navigation to workflow page on success

---

## Implementation Notes

### Staggered Animation in React

```tsx
// Use CSS animation-delay via inline style or dynamic classes
{fields.map((field, index) => (
  <div
    key={field.name}
    className="quick-shot-field"
    style={{ animationDelay: `${index * 50}ms` }}
  >
    {/* field content */}
  </div>
))}
```

### Button State Management

```tsx
const [isSubmitting, setIsSubmitting] = useState(false);
const [isLaunching, setIsLaunching] = useState(false);

const handleSubmit = async () => {
  setIsLaunching(true);
  // Brief ripple animation
  await new Promise(r => setTimeout(r, 400));
  setIsLaunching(false);
  setIsSubmitting(true);

  try {
    const result = await api.createWorkflow(formData);
    toast.success(`Workflow started: ${result.workflow_id}`);
    onClose();
  } catch (error) {
    toast.error(error.message);
  } finally {
    setIsSubmitting(false);
  }
};
```

### Form Validation with react-hook-form

```tsx
const schema = z.object({
  issue_id: z.string().min(1, "Task ID is required"),
  worktree_path: z.string().regex(/^\//, "Must be absolute path"),
  profile: z.string().optional(),
  task_title: z.string().min(1).max(500),
  task_description: z.string().max(5000).optional(),
});
```
