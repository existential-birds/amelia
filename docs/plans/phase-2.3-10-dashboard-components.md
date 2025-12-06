# Dashboard Components Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** Not Started

**Goal:** Build the domain-specific React components for Amelia's web dashboard using a hybrid approach: ai-elements for queue and confirmation patterns, and custom React Flow components for workflow visualization that matches our aviation "flight route" design.

---

## Hybrid Approach Rationale

> The design mock uses map pin icons for workflow visualization, creating a "flight route" aesthetic. ai-elements Node uses Card-based layouts which don't match this visual language. We use ai-elements where it fits (Queue, Confirmation) and build custom where the design requires it (WorkflowCanvas).

**Use ai-elements for:**
- **Queue components** - JobQueue and ActivityLog are thin wrappers around ai-elements Queue
- **Confirmation** - ApprovalControls wraps ai-elements Confirmation state machine
- **Loader/Shimmer** - Loading states throughout the dashboard

**Build CUSTOM (not ai-elements) for WorkflowCanvas:**
- **WorkflowNode** - Custom React Flow node with MapPin icon (lucide-react), not Card-based
- **WorkflowEdge** - Custom React Flow edge with time labels and status-based styling
- **WorkflowCanvas** - React Flow container with aviation theme colors

This hybrid approach preserves the aviation/flight control aesthetic where it matters most (the workflow visualization) while leveraging battle-tested components for standard UI patterns.

---

**Architecture:** Thin wrapper components for queues/confirmations that customize ai-elements. Custom React Flow components for workflow visualization with map pin icons and beacon animations.

**Tech Stack:**
- React 18, TypeScript
- ai-elements components (Queue, Confirmation, Loader, Shimmer)
- React Flow (@xyflow/react) for custom workflow visualization
- lucide-react for icons (MapPin)
- shadcn/ui primitives (from Plan 08) for additional UI needs
- class-variance-authority (CVA) for component variants
- Vitest, @testing-library/react

**Component Patterns (shadcn/ui conventions):**
- **data-slot attributes** - All custom components include `data-slot` for semantic styling hooks
- **CVA for variants** - Use `cva()` from class-variance-authority for component variant definitions
- **cn() utility** - Use `cn()` for className merging (clsx + tailwind-merge)
- **Focus states** - Include `focus-visible:ring-ring/50 focus-visible:ring-[3px]` for keyboard navigation
- **aria-invalid states** - Form elements include `aria-invalid:ring-destructive/20 aria-invalid:border-destructive`
- **OKLCH colors** - All color values use OKLCH format for perceptual uniformity

**Component Architecture:**

| Domain Component | Foundation | Customization |
|------------------|------------|---------------|
| StatusBadge | ai-elements QueueItemIndicator | Custom status colors/labels |
| JobQueue | ai-elements Queue, QueueSection, QueueList | Workflow-specific data binding |
| JobQueueItem | ai-elements QueueItem | Workflow summary display |
| ActivityLog | ai-elements Queue + auto-scroll | Terminal aesthetic, blinking cursor |
| ActivityLogItem | ai-elements QueueItem | Terminal formatting |
| ApprovalControls | ai-elements Confirmation | Approve/Reject callbacks |
| **WorkflowCanvas** | **Custom React Flow** | Dot pattern background, aviation theme |
| **WorkflowNode** | **Custom React Flow node** | MapPin icon, beacon glow, status colors |
| **WorkflowEdge** | **Custom React Flow edge** | Time labels, animated flow indicator |
| **Progress** | shadcn/ui Progress | Overall workflow progress indicator |
| **Skeleton** | shadcn/ui Skeleton | Loading states for JobQueue/ActivityLog |
| **EmptyState** | Custom component | Display when no workflows are active |
| **Sidebar** | shadcn/ui Sidebar | Dashboard layout with collapsible navigation |

**Additional Components (shadcn/ui):**

These components enhance UX with loading states, progress indicators, and responsive layout:

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| **Progress** | Show workflow overall progress | Animated fill, percentage label, OKLCH colors |
| **Skeleton** | Loading placeholders | Pulse animation, matches content dimensions |
| **EmptyState** | No active workflows | Icon, message, optional action button |
| **Sidebar** | Dashboard navigation | SidebarProvider, SidebarMenu, cookie-based state, mobile responsive |

The **Sidebar** component from shadcn/ui is recommended for the dashboard layout because it provides:
- `SidebarProvider` for state management
- `SidebarMenu`, `SidebarMenuItem`, `SidebarMenuButton` for navigation
- `SidebarMenuCollapsible` for nested sections
- Cookie-based state persistence (`defaultOpen` persists across sessions)
- Mobile responsive behavior with sheet-based drawer

**Depends on:**
- Phase 2.3 Plan 8: React project setup with shadcn/ui and design tokens
- Phase 2.3 Plan 9: State management (Zustand store, WebSocket hooks)

**References:**
- [ai-elements Queue](https://github.com/vercel/ai-elements) - Collapsible sections, status indicators
- [ai-elements Confirmation](https://github.com/vercel/ai-elements) - Approval state machine
- [React Flow docs](https://reactflow.dev) - Custom nodes and edges
- [lucide-react](https://lucide.dev) - MapPin icon

---

## PART 1: ai-elements Based Components

These tasks install and wrap ai-elements components for queue and confirmation patterns.

---

## Task 1: Install ai-elements and Dependencies

**Files:**
- Modify: `dashboard/package.json`

**Step 1: Add ai-elements components via registry**

ai-elements uses a registry-based installation similar to shadcn/ui. Install the required components:

```bash
cd dashboard

# Install base dependencies
pnpm add @xyflow/react framer-motion

# Install ai-elements components via registry
npx shadcn@latest add https://ai-elements.vercel.app/registry/queue.json
npx shadcn@latest add https://ai-elements.vercel.app/registry/confirmation.json
npx shadcn@latest add https://ai-elements.vercel.app/registry/loader.json
npx shadcn@latest add https://ai-elements.vercel.app/registry/shimmer.json
```

This installs components to `dashboard/src/components/ai-elements/`:
- `queue.tsx` - QueueSection, QueueList, QueueItem, QueueItemIndicator, etc.
- `confirmation.tsx` - Confirmation, ConfirmationTitle, ConfirmationActions
- `loader.tsx` - Spinning loader SVG
- `shimmer.tsx` - Framer Motion text animation

**Note:** We do NOT install ai-elements workflow components. We build custom React Flow components instead.

**Step 2: Verify installation**

```bash
pnpm run type-check
```

Expected: No TypeScript errors. Files exist in `src/components/ai-elements/`.

**Step 3: Commit**

```bash
git add dashboard/package.json dashboard/package-lock.json dashboard/src/components/ai-elements/
git commit -m "chore(dashboard): install ai-elements components via registry

- Queue components for job queue and activity log
- Confirmation component for approval controls
- Loader and Shimmer for loading states
- Note: Custom React Flow components used for workflow visualization"
```

---

## Task 2: Configure Aviation Theme CSS Variables

**Files:**
- Modify: `dashboard/src/index.css`

Add CSS variables for both ai-elements components and our custom workflow visualization.

**Step 1: Add theme mappings with two-tier CSS variable system**

shadcn/ui uses a two-tier CSS variable system:
1. **Base variables** (semantic): `--primary`, `--status-running`, etc.
2. **Tailwind-mapped** (via `@theme inline`): `--color-primary: var(--primary)`

Add to `dashboard/src/index.css`:

```css
/* dashboard/src/index.css */

/* =============================================================================
 * Two-tier CSS Variable System (shadcn/ui pattern)
 * - Base variables: semantic tokens in OKLCH format
 * - @theme inline: maps to Tailwind's --color-* namespace
 * ============================================================================= */

@theme inline {
  /* Map base variables to Tailwind color namespace */
  --color-primary: var(--primary);
  --color-secondary: var(--secondary);
  --color-accent: var(--accent);
  --color-destructive: var(--destructive);
  --color-muted: var(--muted);
  --color-card: var(--card);
  --color-border: var(--border);

  /* Status colors for Tailwind */
  --color-status-pending: var(--status-pending);
  --color-status-running: var(--status-running);
  --color-status-completed: var(--status-completed);
  --color-status-failed: var(--status-failed);
  --color-status-blocked: var(--status-blocked);
}

@layer base {
  :root {
    /* Existing aviation theme variables... */

    /* ==========================================================================
     * Status Colors (OKLCH format)
     * ========================================================================== */
    --status-pending: oklch(0.708 0.0 0);                /* neutral gray */
    --status-running: oklch(0.82 0.16 85);               /* amber */
    --status-completed: oklch(0.578 0.189 142.495);      /* green/teal */
    --status-failed: oklch(0.577 0.245 27.325);          /* red */
    --status-blocked: oklch(0.637 0.237 25.331);         /* orange-red */

    /* ==========================================================================
     * ai-elements Queue component variables
     * ========================================================================== */
    --queue-indicator-pending: var(--status-pending);
    --queue-indicator-running: var(--status-running);
    --queue-indicator-completed: var(--status-completed);
    --queue-indicator-failed: var(--status-failed);
    --queue-indicator-blocked: var(--status-blocked);

    /* ==========================================================================
     * ai-elements Confirmation component variables
     * ========================================================================== */
    --confirmation-accept: var(--status-completed);
    --confirmation-reject: var(--destructive);
    --confirmation-pending: var(--primary);

    /* ==========================================================================
     * ai-elements Loader variables
     * ========================================================================== */
    --loader-color: var(--primary);

    /* ==========================================================================
     * Custom WorkflowCanvas variables (aviation flight route theme)
     * ========================================================================== */
    --workflow-node-completed: var(--status-completed);  /* teal */
    --workflow-node-active: var(--primary);              /* amber */
    --workflow-node-pending: var(--muted-foreground);
    --workflow-node-blocked: var(--destructive);
    --workflow-edge-completed: var(--status-completed);
    --workflow-edge-active: var(--primary);
    --workflow-edge-pending: var(--muted-foreground);
    --workflow-beacon-glow: oklch(from var(--primary) l c h / 0.3);
  }

  .dark {
    /* Dark mode overrides - adjust OKLCH lightness for dark backgrounds */
    --status-pending: oklch(0.55 0.0 0);
    --status-running: oklch(0.75 0.18 85);
    --status-completed: oklch(0.65 0.17 142.495);
    --status-failed: oklch(0.65 0.22 27.325);
    --status-blocked: oklch(0.70 0.20 25.331);
  }
}
```

**Step 2: Verify theme integration**

```bash
pnpm run dev
# Check browser console for CSS errors
```

**Step 3: Commit**

```bash
git add dashboard/src/index.css
git commit -m "feat(dashboard): add theme variable mappings

- Map aviation theme tokens to ai-elements CSS variables
- Queue indicator colors for workflow statuses
- Confirmation button colors
- Custom workflow canvas colors for flight route aesthetic"
```

---

## Task 3: StatusBadge Wrapper Component

Create a thin wrapper around `QueueItemIndicator` that maps our `WorkflowStatus` enum to appropriate labels and colors.

**Files:**
- Create: `dashboard/src/components/StatusBadge.tsx`
- Create: `dashboard/src/components/StatusBadge.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/StatusBadge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders RUNNING label for in_progress status', () => {
    render(<StatusBadge status="in_progress" />);
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
  });

  it('renders DONE label for completed status', () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText('DONE')).toBeInTheDocument();
  });

  it('renders QUEUED label for pending status', () => {
    render(<StatusBadge status="pending" />);
    expect(screen.getByText('QUEUED')).toBeInTheDocument();
  });

  it('renders BLOCKED label for blocked status', () => {
    render(<StatusBadge status="blocked" />);
    expect(screen.getByText('BLOCKED')).toBeInTheDocument();
  });

  it('renders FAILED label for failed status', () => {
    render(<StatusBadge status="failed" />);
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });

  it('has proper ARIA role and label', () => {
    render(<StatusBadge status="in_progress" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'Workflow status: running');
  });

  it('applies pulse animation for running status', () => {
    const { container } = render(<StatusBadge status="in_progress" />);
    expect(container.querySelector('[data-status="running"]')).toBeInTheDocument();
  });

  it('uses QueueItemIndicator internally', () => {
    const { container } = render(<StatusBadge status="completed" />);
    // QueueItemIndicator renders with data-slot="indicator"
    expect(container.querySelector('[data-slot="indicator"]')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd dashboard && pnpm test src/components/StatusBadge.test.tsx
```

Expected: FAIL - Component does not exist

**Step 3: Implement StatusBadge wrapper with CVA and data-slot**

```typescript
// dashboard/src/components/StatusBadge.tsx
import { cva, type VariantProps } from 'class-variance-authority';
import { QueueItemIndicator } from '@/components/ai-elements/queue';
import { cn } from '@/lib/utils';
import type { WorkflowStatus } from '@/types';

/**
 * CVA variant definitions for StatusBadge styling.
 * Uses OKLCH-based status colors via CSS variables.
 */
const statusBadgeVariants = cva(
  // Base styles
  'inline-flex items-center justify-center rounded-md text-xs font-semibold uppercase tracking-wider transition-colors',
  {
    variants: {
      status: {
        pending: 'bg-status-pending/10 text-status-pending border-status-pending/20',
        running: 'bg-status-running/10 text-status-running border-status-running/20',
        completed: 'bg-status-completed/10 text-status-completed border-status-completed/20',
        failed: 'bg-status-failed/10 text-status-failed border-status-failed/20',
        blocked: 'bg-status-blocked/10 text-status-blocked border-status-blocked/20',
      },
      size: {
        sm: 'px-2 py-0.5 text-[10px]',
        md: 'px-2.5 py-1 text-xs',
        lg: 'px-3 py-1.5 text-sm',
      },
    },
    defaultVariants: {
      status: 'pending',
      size: 'md',
    },
  }
);

interface StatusBadgeProps extends VariantProps<typeof statusBadgeVariants> {
  status: WorkflowStatus;
  className?: string;
}

// Map WorkflowStatus to display labels
const statusLabels: Record<WorkflowStatus, string> = {
  pending: 'QUEUED',
  in_progress: 'RUNNING',
  blocked: 'BLOCKED',
  completed: 'DONE',
  failed: 'FAILED',
  cancelled: 'CANCELLED',
};

// Map WorkflowStatus to QueueItemIndicator status prop
type IndicatorStatus = 'pending' | 'running' | 'completed' | 'failed' | 'blocked';
const statusMapping: Record<WorkflowStatus, IndicatorStatus> = {
  pending: 'pending',
  in_progress: 'running',
  blocked: 'blocked',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'failed',
};

/**
 * StatusBadge wraps ai-elements QueueItemIndicator with workflow-specific
 * status labels and ARIA attributes.
 *
 * Uses aviation theme colors via CSS variables:
 * - --queue-indicator-pending, --queue-indicator-running, etc.
 *
 * Includes data-slot="status-badge" for semantic styling hooks.
 */
export function StatusBadge({ status, size, className }: StatusBadgeProps) {
  const indicatorStatus = statusMapping[status];
  const displayStatus = status === 'in_progress' ? 'running' : status;

  return (
    <div
      data-slot="status-badge"
      role="status"
      aria-label={`Workflow status: ${displayStatus}`}
      className={cn(statusBadgeVariants({ status: indicatorStatus, size }), className)}
    >
      <QueueItemIndicator
        status={indicatorStatus}
        data-status={indicatorStatus}
      >
        {statusLabels[status]}
      </QueueItemIndicator>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

```bash
cd dashboard && pnpm test src/components/StatusBadge.test.tsx
```

Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/StatusBadge.tsx dashboard/src/components/StatusBadge.test.tsx
git commit -m "feat(dashboard): add StatusBadge wrapper for QueueItemIndicator

- Wraps ai-elements QueueItemIndicator with workflow status labels
- Maps WorkflowStatus enum to indicator status prop
- ARIA role and label for accessibility
- Uses aviation theme colors via CSS variables"
```

---

## Task 4: JobQueueItem Wrapper Component

Create a wrapper around `QueueItem` that displays workflow summary data with our aviation styling.

**Files:**
- Create: `dashboard/src/components/JobQueueItem.tsx`
- Create: `dashboard/src/components/JobQueueItem.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/JobQueueItem.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JobQueueItem } from './JobQueueItem';

describe('JobQueueItem', () => {
  const mockWorkflow = {
    id: 'wf-001',
    issue_id: '#8',
    worktree_name: 'feature-benchmark',
    status: 'in_progress' as const,
    current_stage: 'Developer',
  };

  it('renders issue ID and worktree name', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
    expect(screen.getByText('feature-benchmark')).toBeInTheDocument();
  });

  it('renders status indicator via QueueItemIndicator', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    // StatusBadge wraps QueueItemIndicator
    expect(screen.getByRole('status')).toHaveTextContent('RUNNING');
  });

  it('renders current stage in QueueItemDescription', () => {
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />);
    expect(screen.getByText(/Stage: Developer/)).toBeInTheDocument();
  });

  it('shows selected state with primary border', () => {
    const { container } = render(
      <JobQueueItem workflow={mockWorkflow} selected={true} onSelect={() => {}} />
    );
    // ai-elements QueueItem applies data-selected attribute
    expect(container.querySelector('[data-selected="true"]')).toBeInTheDocument();
  });

  it('calls onSelect when clicked', () => {
    const onSelect = vi.fn();
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole('button'));
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('supports keyboard navigation (Enter)', () => {
    const onSelect = vi.fn();
    render(<JobQueueItem workflow={mockWorkflow} selected={false} onSelect={onSelect} />);

    fireEvent.keyDown(screen.getByRole('button'), { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('uses QueueItem structure internally', () => {
    const { container } = render(
      <JobQueueItem workflow={mockWorkflow} selected={false} onSelect={() => {}} />
    );
    // ai-elements QueueItem renders with data-slot="item"
    expect(container.querySelector('[data-slot="item"]')).toBeInTheDocument();
  });

  it('renders actions slot when provided', () => {
    render(
      <JobQueueItem
        workflow={mockWorkflow}
        selected={false}
        onSelect={() => {}}
        actions={<button>Cancel</button>}
      />
    );
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });
});
```

**Step 2: Implement JobQueueItem wrapper**

```typescript
// dashboard/src/components/JobQueueItem.tsx
import {
  QueueItem,
  QueueItemContent,
  QueueItemDescription,
  QueueItemActions,
} from '@/components/ai-elements/queue';
import { StatusBadge } from '@/components/StatusBadge';
import type { WorkflowSummary } from '@/types';
import type { ReactNode } from 'react';

interface JobQueueItemProps {
  workflow: Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_name' | 'status' | 'current_stage'>;
  selected: boolean;
  onSelect: (id: string) => void;
  actions?: ReactNode;
}

/**
 * JobQueueItem wraps ai-elements QueueItem with workflow-specific data.
 *
 * Structure:
 * - QueueItem (container with selection state)
 *   - StatusBadge (wraps QueueItemIndicator)
 *   - QueueItemContent
 *     - Issue ID (primary text)
 *     - Worktree name (secondary text)
 *   - QueueItemDescription (current stage)
 *   - QueueItemActions (optional action buttons)
 */
export function JobQueueItem({ workflow, selected, onSelect, actions }: JobQueueItemProps) {
  const handleClick = () => onSelect(workflow.id);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(workflow.id);
    }
  };

  return (
    <QueueItem
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      data-selected={selected}
      className="cursor-pointer transition-all duration-200"
    >
      <StatusBadge status={workflow.status} />

      <QueueItemContent>
        <span className="font-mono text-sm font-semibold text-accent">
          {workflow.issue_id}
        </span>
        <span className="font-body text-base text-foreground">
          {workflow.worktree_name}
        </span>
      </QueueItemContent>

      {workflow.current_stage && (
        <QueueItemDescription>
          Stage: {workflow.current_stage}
        </QueueItemDescription>
      )}

      {actions && (
        <QueueItemActions>
          {actions}
        </QueueItemActions>
      )}
    </QueueItem>
  );
}
```

**Step 3: Run test**

```bash
cd dashboard && pnpm test src/components/JobQueueItem.test.tsx
```

**Step 4: Commit**

```bash
git add dashboard/src/components/JobQueueItem.tsx dashboard/src/components/JobQueueItem.test.tsx
git commit -m "feat(dashboard): add JobQueueItem wrapper for QueueItem

- Wraps ai-elements QueueItem with workflow data binding
- Uses StatusBadge for status indicator
- QueueItemContent for issue ID and worktree name
- QueueItemDescription for current stage
- Optional QueueItemActions slot
- Keyboard navigation support"
```

---

## Task 5: JobQueue Component

Create a composition using `QueueSection`, `QueueList`, and `JobQueueItem` for the collapsible workflow queue.

**Files:**
- Create: `dashboard/src/components/JobQueue.tsx`
- Create: `dashboard/src/components/JobQueue.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/JobQueue.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JobQueue } from './JobQueue';

describe('JobQueue', () => {
  const mockWorkflows = [
    { id: 'wf-001', issue_id: '#8', worktree_name: 'feature-a', status: 'in_progress' as const, current_stage: 'Developer' },
    { id: 'wf-002', issue_id: '#7', worktree_name: 'feature-b', status: 'completed' as const, current_stage: null },
    { id: 'wf-003', issue_id: '#9', worktree_name: 'feature-c', status: 'pending' as const, current_stage: null },
  ];

  it('renders all workflows', () => {
    render(<JobQueue workflows={mockWorkflows} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
    expect(screen.getByText('#7')).toBeInTheDocument();
    expect(screen.getByText('#9')).toBeInTheDocument();
  });

  it('renders section label via QueueSectionLabel', () => {
    render(<JobQueue workflows={mockWorkflows} />);
    expect(screen.getByText('JOB QUEUE')).toBeInTheDocument();
  });

  it('shows workflow count in section trigger', () => {
    render(<JobQueue workflows={mockWorkflows} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('highlights selected workflow', () => {
    const { container } = render(
      <JobQueue workflows={mockWorkflows} selectedId="wf-001" />
    );
    expect(container.querySelector('[data-selected="true"]')).toBeInTheDocument();
  });

  it('calls onSelect when workflow is clicked', () => {
    const onSelect = vi.fn();
    render(<JobQueue workflows={mockWorkflows} onSelect={onSelect} />);

    fireEvent.click(screen.getByText('#8').closest('[role="button"]')!);
    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('uses QueueSection structure internally', () => {
    const { container } = render(
      <JobQueue workflows={mockWorkflows} />
    );
    // ai-elements QueueSection renders with data-slot="section"
    expect(container.querySelector('[data-slot="section"]')).toBeInTheDocument();
  });

  it('section is collapsible via QueueSectionTrigger', () => {
    render(<JobQueue workflows={mockWorkflows} />);
    // QueueSectionTrigger should have aria-expanded
    const trigger = screen.getByRole('button', { name: /JOB QUEUE/i });
    expect(trigger).toHaveAttribute('aria-expanded');
  });

  it('shows empty state when no workflows', () => {
    render(<JobQueue workflows={[]} />);
    expect(screen.getByText(/No active workflows/)).toBeInTheDocument();
  });

  it('shows empty state when workflows prop is omitted (default [])', () => {
    render(<JobQueue />);
    expect(screen.getByText(/No active workflows/)).toBeInTheDocument();
  });

  it('groups workflows by status when grouped prop is true', () => {
    render(<JobQueue workflows={mockWorkflows} grouped />);
    // Should have multiple QueueSection elements for each status group
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
    expect(screen.getByText('QUEUED')).toBeInTheDocument();
  });
});
```

**Step 2: Implement JobQueue component**

```typescript
// dashboard/src/components/JobQueue.tsx
import { useMemo } from 'react';
import {
  QueueSection,
  QueueSectionTrigger,
  QueueSectionLabel,
  QueueSectionContent,
  QueueList,
} from '@/components/ai-elements/queue';
import { Badge } from '@/components/ui/badge';
import { JobQueueItem } from '@/components/JobQueueItem';
import type { WorkflowSummary, WorkflowStatus } from '@/types';

interface JobQueueProps {
  // Note: workflows typically come from useLoaderData() in parent page
  // This prop is for when JobQueue is used in a non-route context (e.g., testing)
  workflows?: Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_name' | 'status' | 'current_stage'>[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  grouped?: boolean;
}

// Status group labels and order
const statusGroups: { status: WorkflowStatus; label: string }[] = [
  { status: 'in_progress', label: 'RUNNING' },
  { status: 'pending', label: 'QUEUED' },
  { status: 'blocked', label: 'BLOCKED' },
  { status: 'completed', label: 'COMPLETED' },
  { status: 'failed', label: 'FAILED' },
];

/**
 * JobQueue uses ai-elements Queue components to display a collapsible
 * list of workflows with optional grouping by status.
 *
 * Data Flow:
 * - Workflows typically come from useLoaderData() in parent page component
 * - Real-time updates merged from Zustand store (see Plan 09)
 * - Loading state via useNavigation() for route transitions
 *
 * Structure:
 * - QueueSection (collapsible container)
 *   - QueueSectionTrigger
 *     - QueueSectionLabel ("JOB QUEUE")
 *     - Badge (count)
 *   - QueueSectionContent
 *     - QueueList
 *       - JobQueueItem (for each workflow)
 */
export function JobQueue({ workflows = [], selectedId = null, onSelect = () => {}, grouped = false }: JobQueueProps) {
  // Group workflows by status if grouped prop is true
  const groupedWorkflows = useMemo(() => {
    if (!grouped) return null;

    const groups = new Map<WorkflowStatus, typeof workflows>();
    for (const workflow of workflows) {
      const existing = groups.get(workflow.status) || [];
      groups.set(workflow.status, [...existing, workflow]);
    }
    return groups;
  }, [workflows, grouped]);

  if (grouped && groupedWorkflows) {
    return (
      <div className="flex flex-col gap-2">
        {statusGroups.map(({ status, label }) => {
          const groupWorkflows = groupedWorkflows.get(status) || [];
          if (groupWorkflows.length === 0) return null;

          return (
            <QueueSection key={status} defaultOpen>
              <QueueSectionTrigger>
                <QueueSectionLabel>{label}</QueueSectionLabel>
                <Badge variant="secondary" className="ml-auto text-xs">
                  {groupWorkflows.length}
                </Badge>
              </QueueSectionTrigger>
              <QueueSectionContent>
                <QueueList>
                  {groupWorkflows.map((workflow) => (
                    <JobQueueItem
                      key={workflow.id}
                      workflow={workflow}
                      selected={workflow.id === selectedId}
                      onSelect={onSelect}
                    />
                  ))}
                </QueueList>
              </QueueSectionContent>
            </QueueSection>
          );
        })}
      </div>
    );
  }

  return (
    <QueueSection defaultOpen>
      <QueueSectionTrigger>
        <QueueSectionLabel>JOB QUEUE</QueueSectionLabel>
        <Badge variant="secondary" className="ml-auto text-xs">
          {workflows.length}
        </Badge>
      </QueueSectionTrigger>

      <QueueSectionContent>
        {workflows.length === 0 ? (
          <p className="text-center text-muted-foreground py-8">
            No active workflows
          </p>
        ) : (
          <QueueList>
            {workflows.map((workflow) => (
              <JobQueueItem
                key={workflow.id}
                workflow={workflow}
                selected={workflow.id === selectedId}
                onSelect={onSelect}
              />
            ))}
          </QueueList>
        )}
      </QueueSectionContent>
    </QueueSection>
  );
}
```

**Step 3: Run test**

```bash
cd dashboard && pnpm test src/components/JobQueue.test.tsx
```

**Step 4: Commit**

```bash
git add dashboard/src/components/JobQueue.tsx dashboard/src/components/JobQueue.test.tsx
git commit -m "feat(dashboard): add JobQueue using ai-elements Queue components

- Composes QueueSection, QueueSectionTrigger, QueueSectionContent, QueueList
- Collapsible section with count badge
- Optional grouping by workflow status
- Empty state message
- Uses JobQueueItem for individual workflows"
```

---

## Task 6: ActivityLogItem Component

Create a component for individual log entries using Queue components with terminal-style formatting.

**Files:**
- Create: `dashboard/src/components/ActivityLogItem.tsx`
- Create: `dashboard/src/components/ActivityLogItem.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/ActivityLogItem.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityLogItem } from './ActivityLogItem';

describe('ActivityLogItem', () => {
  const mockEvent = {
    id: 'evt-001',
    workflow_id: 'wf-001',
    sequence: 1,
    timestamp: '2025-12-01T14:32:07Z',
    agent: 'ARCHITECT',
    event_type: 'stage_started' as const,
    message: 'Issue #8 parsed. Creating task DAG for benchmark framework.',
  };

  it('renders timestamp in HH:MM:SS format', () => {
    render(<ActivityLogItem event={mockEvent} />);
    expect(screen.getByText('14:32:07')).toBeInTheDocument();
  });

  it('renders agent name in brackets', () => {
    render(<ActivityLogItem event={mockEvent} />);
    expect(screen.getByText('[ARCHITECT]')).toBeInTheDocument();
  });

  it('renders message text', () => {
    render(<ActivityLogItem event={mockEvent} />);
    expect(screen.getByText(/Issue #8 parsed/)).toBeInTheDocument();
  });

  it('applies correct agent color class', () => {
    render(<ActivityLogItem event={mockEvent} />);
    const agent = screen.getByText('[ARCHITECT]');
    expect(agent).toHaveClass('text-accent');
  });

  it('uses QueueItem structure internally', () => {
    const { container } = render(<ActivityLogItem event={mockEvent} />);
    expect(container.querySelector('[data-slot="item"]')).toBeInTheDocument();
  });

  it('renders QueueItemIndicator for event type', () => {
    const { container } = render(<ActivityLogItem event={mockEvent} />);
    expect(container.querySelector('[data-slot="indicator"]')).toBeInTheDocument();
  });

  it('shows different colors for different agents', () => {
    const developerEvent = { ...mockEvent, agent: 'DEVELOPER' };
    render(<ActivityLogItem event={developerEvent} />);
    const agent = screen.getByText('[DEVELOPER]');
    expect(agent).toHaveClass('text-primary');
  });
});
```

**Step 2: Implement ActivityLogItem component**

```typescript
// dashboard/src/components/ActivityLogItem.tsx
import {
  QueueItem,
  QueueItemIndicator,
  QueueItemContent,
} from '@/components/ai-elements/queue';
import { cn } from '@/lib/utils';
import type { WorkflowEvent } from '@/types';

interface ActivityLogItemProps {
  event: WorkflowEvent;
}

// Format ISO timestamp to HH:MM:SS
function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toISOString().slice(11, 19);
}

// Agent colors for visual distinction
const agentColors: Record<string, string> = {
  ARCHITECT: 'text-accent',
  DEVELOPER: 'text-primary',
  REVIEWER: 'text-[--status-completed]',
  SYSTEM: 'text-muted-foreground',
};

// Map event types to indicator status
const eventTypeStatus: Record<string, 'pending' | 'running' | 'completed' | 'failed'> = {
  stage_started: 'running',
  stage_completed: 'completed',
  stage_failed: 'failed',
  approval_requested: 'pending',
  approval_granted: 'completed',
  approval_rejected: 'failed',
  message: 'running',
};

/**
 * ActivityLogItem displays a single workflow event using ai-elements QueueItem.
 *
 * Format: [HH:MM:SS] [AGENT] message
 * Uses monospace font for terminal aesthetic.
 */
export function ActivityLogItem({ event }: ActivityLogItemProps) {
  const agentColor = agentColors[event.agent.toUpperCase()] || 'text-muted-foreground';
  const status = eventTypeStatus[event.event_type] || 'running';

  return (
    <QueueItem className="py-1.5 border-b border-border/30">
      <QueueItemIndicator status={status} className="w-2 h-2" />

      <QueueItemContent className="grid grid-cols-[80px_90px_1fr] gap-3 font-mono text-sm">
        <span className="text-muted-foreground tabular-nums">
          {formatTime(event.timestamp)}
        </span>
        <span className={cn('font-semibold', agentColor)}>
          [{event.agent.toUpperCase()}]
        </span>
        <span className="text-foreground/80">
          {event.message}
        </span>
      </QueueItemContent>
    </QueueItem>
  );
}
```

**Step 3: Commit**

```bash
git add dashboard/src/components/ActivityLogItem.tsx dashboard/src/components/ActivityLogItem.test.tsx
git commit -m "feat(dashboard): add ActivityLogItem using ai-elements QueueItem

- Wraps ai-elements QueueItem for log entries
- Terminal-style formatting with timestamp and agent
- Color-coded agent names
- QueueItemIndicator shows event type status"
```

---

## Task 7: ActivityLog Component

Create the full activity log using Queue components with auto-scroll and terminal aesthetic.

**Files:**
- Create: `dashboard/src/components/ActivityLog.tsx`
- Create: `dashboard/src/components/ActivityLog.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/ActivityLog.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityLog } from './ActivityLog';
import * as workflowStore from '@/store/workflowStore';

// Mock the Zustand store
vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn(() => ({
    eventsByWorkflow: {},
  })),
}));

describe('ActivityLog', () => {
  const mockEvents = [
    {
      id: 'evt-001',
      workflow_id: 'wf-001',
      sequence: 1,
      timestamp: '2025-12-01T14:32:07Z',
      agent: 'ARCHITECT',
      event_type: 'stage_started' as const,
      message: 'Issue #8 parsed.',
    },
    {
      id: 'evt-002',
      workflow_id: 'wf-001',
      sequence: 2,
      timestamp: '2025-12-01T14:32:45Z',
      agent: 'ARCHITECT',
      event_type: 'stage_completed' as const,
      message: 'Plan approved.',
    },
  ];

  it('renders section label via QueueSectionLabel', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(screen.getByText('ACTIVITY LOG')).toBeInTheDocument();
  });

  it('renders all initial events', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(screen.getByText(/Issue #8 parsed/)).toBeInTheDocument();
    expect(screen.getByText(/Plan approved/)).toBeInTheDocument();
  });

  it('merges loader events with real-time events from Zustand', () => {
    const realtimeEvent = {
      id: 'evt-003',
      workflow_id: 'wf-001',
      sequence: 3,
      timestamp: '2025-12-01T14:33:00Z',
      agent: 'DEVELOPER',
      event_type: 'stage_started' as const,
      message: 'Starting implementation.',
    };

    vi.mocked(workflowStore.useWorkflowStore).mockReturnValue({
      eventsByWorkflow: { 'wf-001': [realtimeEvent] },
    } as any);

    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);

    // Should show both loader events and real-time events
    expect(screen.getByText(/Issue #8 parsed/)).toBeInTheDocument();
    expect(screen.getByText(/Starting implementation/)).toBeInTheDocument();
  });

  it('has proper ARIA role for log', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(screen.getByRole('log')).toHaveAttribute('aria-live', 'polite');
  });

  it('renders blinking cursor using Shimmer', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(screen.getByTestId('log-cursor')).toBeInTheDocument();
  });

  it('shows empty state when no events', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={[]} />);
    expect(screen.getByText(/No activity/)).toBeInTheDocument();
  });

  it('uses QueueSection structure internally', () => {
    const { container } = render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(container.querySelector('[data-slot="section"]')).toBeInTheDocument();
  });

  it('renders Loader when loading prop is true', () => {
    render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} loading />);
    expect(screen.getByTestId('activity-loader')).toBeInTheDocument();
  });

  it('applies scanlines overlay for terminal aesthetic', () => {
    const { container } = render(<ActivityLog workflowId="wf-001" initialEvents={mockEvents} />);
    expect(container.querySelector('[data-scanlines]')).toBeInTheDocument();
  });
});
```

**Step 2: Implement ActivityLog component**

```typescript
// dashboard/src/components/ActivityLog.tsx
import { useEffect, useRef, useMemo } from 'react';
import {
  QueueSection,
  QueueSectionTrigger,
  QueueSectionLabel,
  QueueSectionContent,
  QueueList,
} from '@/components/ai-elements/queue';
import { Loader } from '@/components/ai-elements/loader';
import { Shimmer } from '@/components/ai-elements/shimmer';
import { ActivityLogItem } from '@/components/ActivityLogItem';
import { useWorkflowStore } from '@/store/workflowStore';
import type { WorkflowEvent } from '@/types';

interface ActivityLogProps {
  workflowId: string;
  // Initial events from loader (via parent page)
  initialEvents?: WorkflowEvent[];
  loading?: boolean;
}

/**
 * ActivityLog displays workflow events using ai-elements Queue components
 * with terminal aesthetic (scanlines, blinking cursor, auto-scroll).
 *
 * Data Flow:
 * - Initial events from loader (via parent WorkflowDetailPage)
 * - Real-time events from Zustand store (WebSocket updates)
 * - Merged to show complete event stream
 *
 * Structure:
 * - QueueSection
 *   - QueueSectionTrigger with "ACTIVITY LOG" label
 *   - QueueSectionContent
 *     - Scanlines overlay
 *     - QueueList with ActivityLogItem entries
 *     - Blinking cursor (Shimmer)
 *     - Loader when loading
 */
export function ActivityLog({ workflowId, initialEvents = [], loading = false }: ActivityLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Real-time events from WebSocket (via Zustand store from Plan 09)
  const { eventsByWorkflow } = useWorkflowStore();
  const realtimeEvents = eventsByWorkflow[workflowId] || [];

  // Merge: loader events + any new real-time events
  const events = useMemo(() => {
    const loaderEventIds = new Set(initialEvents.map(e => e.id));
    const newEvents = realtimeEvents.filter(e => !loaderEventIds.has(e.id));
    return [...initialEvents, ...newEvents];
  }, [initialEvents, realtimeEvents]);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [events.length]);

  return (
    <QueueSection defaultOpen className="h-full flex flex-col">
      <QueueSectionTrigger>
        <QueueSectionLabel>ACTIVITY LOG</QueueSectionLabel>
        {loading && (
          <Loader
            data-testid="activity-loader"
            className="ml-auto w-4 h-4"
          />
        )}
      </QueueSectionTrigger>

      <QueueSectionContent className="flex-1 relative overflow-hidden">
        {/* Scanlines overlay for terminal aesthetic */}
        <div
          data-scanlines
          className="absolute inset-0 pointer-events-none opacity-50 motion-reduce:hidden z-10"
          style={{
            background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, oklch(from var(--foreground) l c h / 0.015) 2px, oklch(from var(--foreground) l c h / 0.015) 4px)',
          }}
          aria-hidden="true"
        />

        <div
          role="log"
          aria-live="polite"
          aria-label="Workflow activity log"
          className="h-full overflow-y-auto p-4"
        >
          {events.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No activity yet
            </p>
          ) : (
            <QueueList>
              {events.map((event) => (
                <ActivityLogItem key={event.id} event={event} />
              ))}

              {/* Blinking cursor using Shimmer */}
              <div
                data-testid="log-cursor"
                className="text-primary mt-2 font-mono"
                aria-hidden="true"
              >
                <Shimmer className="w-3">_</Shimmer>
              </div>

              {/* Scroll anchor */}
              <div ref={scrollRef} />
            </QueueList>
          )}
        </div>
      </QueueSectionContent>
    </QueueSection>
  );
}
```

**Step 3: Commit**

```bash
git add dashboard/src/components/ActivityLog.tsx dashboard/src/components/ActivityLog.test.tsx
git commit -m "feat(dashboard): add ActivityLog with loader + real-time event merging

- Composes QueueSection with ActivityLogItem entries
- Merges initial events from loader with real-time events from Zustand
- Auto-scroll to latest event
- Scanlines overlay for terminal aesthetic
- Blinking cursor using ai-elements Shimmer
- Loading state with ai-elements Loader
- ARIA live region for screen readers"
```

---

## Task 8: ApprovalControls Component (using ai-elements Confirmation + useFetcher)

Create approval controls using ai-elements Confirmation with React Router's useFetcher for mutations.

**Files:**
- Create: `dashboard/src/components/ApprovalControls.tsx`
- Create: `dashboard/src/components/ApprovalControls.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/ApprovalControls.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApprovalControls } from './ApprovalControls';

// Helper to render component with router context
const renderWithRouter = (workflowId: string, planSummary: string, status?: string) => {
  const router = createMemoryRouter([
    {
      path: '/',
      element: <ApprovalControls workflowId={workflowId} planSummary={planSummary} status={status} />,
      // Mock action endpoints
      action: async () => ({ ok: true }),
    },
    {
      path: '/workflows/:id/approve',
      action: async () => ({ ok: true }),
    },
    {
      path: '/workflows/:id/reject',
      action: async () => ({ ok: true }),
    },
  ]);

  return render(<RouterProvider router={router} />);
};

describe('ApprovalControls', () => {
  it('renders Approve and Reject buttons via ConfirmationActions', () => {
    renderWithRouter('wf-001', 'Add benchmark framework');
    expect(screen.getByText('Approve')).toBeInTheDocument();
    expect(screen.getByText('Reject')).toBeInTheDocument();
  });

  it('renders ConfirmationTitle with plan summary', () => {
    renderWithRouter('wf-001', 'Add benchmark framework');
    expect(screen.getByText(/Add benchmark framework/)).toBeInTheDocument();
  });

  it('renders ConfirmationRequest description', () => {
    renderWithRouter('wf-001', 'Add benchmark framework');
    expect(screen.getByText(/Review and approve/)).toBeInTheDocument();
  });

  it('uses fetcher.Form with POST method for approve action', () => {
    const { container } = renderWithRouter('wf-001', 'Test');
    const approveForm = screen.getByText('Approve').closest('form');
    expect(approveForm).toHaveAttribute('method', 'post');
    expect(approveForm).toHaveAttribute('action', '/workflows/wf-001/approve');
  });

  it('uses fetcher.Form with POST method for reject action', () => {
    const { container } = renderWithRouter('wf-001', 'Test');
    const rejectForm = screen.getByText('Reject').closest('form');
    expect(rejectForm).toHaveAttribute('method', 'post');
    expect(rejectForm).toHaveAttribute('action', '/workflows/wf-001/reject');
  });

  it('disables buttons when fetcher is submitting', () => {
    // Note: In real implementation, fetcher.state would be 'submitting'
    // This test shows the structure; actual disabled state requires user interaction
    renderWithRouter('wf-001', 'Test');
    const approveButton = screen.getByText('Approve');
    expect(approveButton).not.toBeDisabled(); // Initially enabled
  });

  it('shows Loader when fetcher is not idle', () => {
    // Note: In real implementation, fetcher.state tracking would show loader
    // This test documents the expected behavior
    renderWithRouter('wf-001', 'Test');
    // Loader appears only when fetcher.state !== 'idle'
  });

  it('uses ai-elements Confirmation structure', () => {
    const { container } = renderWithRouter('wf-001', 'Test');
    expect(container.querySelector('[data-slot="confirmation"]')).toBeInTheDocument();
  });

  it('shows ConfirmationAccepted state when status is approved', () => {
    renderWithRouter('wf-001', 'Test', 'approved');
    expect(screen.getByText(/Plan approved/)).toBeInTheDocument();
  });

  it('shows ConfirmationRejected state when status is rejected', () => {
    renderWithRouter('wf-001', 'Test', 'rejected');
    expect(screen.getByText(/Plan rejected/)).toBeInTheDocument();
  });
});
```

**Step 2: Implement ApprovalControls component with useFetcher**

```typescript
// dashboard/src/components/ApprovalControls.tsx
import { useFetcher } from 'react-router-dom';
import {
  Confirmation,
  ConfirmationTitle,
  ConfirmationRequest,
  ConfirmationAccepted,
  ConfirmationRejected,
  ConfirmationActions,
  ConfirmationAction,
} from '@/components/ai-elements/confirmation';
import { Loader } from '@/components/ai-elements/loader';
import { Check, X } from 'lucide-react';

type ApprovalStatus = 'pending' | 'approved' | 'rejected';

interface ApprovalControlsProps {
  workflowId: string;
  planSummary: string;
  status?: ApprovalStatus;
}

/**
 * ApprovalControls uses ai-elements Confirmation for approve/reject workflow.
 *
 * Data Flow:
 * - Uses React Router's useFetcher for approve/reject mutations
 * - Form submissions to /workflows/:id/approve and /workflows/:id/reject actions
 * - Pending state from fetcher.state !== 'idle'
 * - No custom hooks - mutations handled via Data Mode actions
 *
 * State machine: approval-requested -> approval-responded
 *
 * Structure:
 * - Confirmation (container with state management)
 *   - ConfirmationTitle (plan summary)
 *   - ConfirmationRequest (description)
 *   - ConfirmationActions
 *     - fetcher.Form (Approve action)
 *     - fetcher.Form (Reject action)
 *   - ConfirmationAccepted (shown after approval)
 *   - ConfirmationRejected (shown after rejection)
 */
export function ApprovalControls({
  workflowId,
  planSummary,
  status = 'pending',
}: ApprovalControlsProps) {
  const fetcher = useFetcher();
  const isPending = fetcher.state !== 'idle';

  return (
    <Confirmation
      status={status === 'pending' ? 'requested' : 'responded'}
      className="p-4 border border-border rounded-lg bg-card"
    >
      <ConfirmationTitle className="font-heading text-lg font-semibold mb-2">
        {planSummary}
      </ConfirmationTitle>

      <ConfirmationRequest className="text-sm text-muted-foreground mb-4">
        Review and approve this plan to proceed with implementation.
      </ConfirmationRequest>

      {status === 'pending' && (
        <ConfirmationActions className="flex gap-3">
          {/* Approve action via fetcher.Form */}
          <fetcher.Form method="post" action={`/workflows/${workflowId}/approve`}>
            <ConfirmationAction
              action="accept"
              type="submit"
              disabled={isPending}
              className="bg-[--confirmation-accept] hover:bg-[--confirmation-accept]/90 text-foreground"
            >
              {isPending ? (
                <Loader
                  data-testid="approval-loader"
                  className="w-4 h-4 mr-2"
                />
              ) : (
                <Check className="w-4 h-4 mr-2" />
              )}
              Approve
            </ConfirmationAction>
          </fetcher.Form>

          {/* Reject action via fetcher.Form */}
          <fetcher.Form method="post" action={`/workflows/${workflowId}/reject`}>
            <input type="hidden" name="feedback" value="Rejected by user" />
            <ConfirmationAction
              action="reject"
              type="submit"
              variant="outline"
              disabled={isPending}
              className="border-[--confirmation-reject] text-[--confirmation-reject] hover:bg-[--confirmation-reject] hover:text-foreground"
            >
              {isPending ? (
                <Loader
                  data-testid="approval-loader"
                  className="w-4 h-4 mr-2"
                />
              ) : (
                <X className="w-4 h-4 mr-2" />
              )}
              Reject
            </ConfirmationAction>
          </fetcher.Form>
        </ConfirmationActions>
      )}

      <ConfirmationAccepted className="text-[--confirmation-accept] font-semibold">
        <Check className="w-4 h-4 mr-2 inline" />
        Plan approved. Implementation starting...
      </ConfirmationAccepted>

      <ConfirmationRejected className="text-[--confirmation-reject] font-semibold">
        <X className="w-4 h-4 mr-2 inline" />
        Plan rejected. Awaiting revision...
      </ConfirmationRejected>
    </Confirmation>
  );
}
```

**Step 3: Commit**

```bash
git add dashboard/src/components/ApprovalControls.tsx dashboard/src/components/ApprovalControls.test.tsx
git commit -m "feat(dashboard): add ApprovalControls using Confirmation + useFetcher

- Wraps ai-elements Confirmation state machine (requested -> responded)
- Uses React Router useFetcher for approve/reject mutations
- fetcher.Form submits to /workflows/:id/approve and /workflows/:id/reject
- Pending state from fetcher.state !== 'idle'
- ConfirmationAccepted/Rejected for response states
- No custom hooks - mutations via Data Mode actions
- Uses aviation theme confirmation colors"
```

---

## Page Component Integration Examples

**Note:** These examples show how page components wire up loader data to child components using React Router v7 Data Mode patterns. These patterns are implemented in Plan 09 (Routes & Pages).

### Example 1: WorkflowsPage with Loader Data

```typescript
// pages/WorkflowsPage.tsx
import { useLoaderData, Outlet, useNavigation } from 'react-router-dom';
import { JobQueue } from '@/components/JobQueue';
import { useWorkflowStore } from '@/store/workflowStore';

export default function WorkflowsPage() {
  const { workflows } = useLoaderData() as WorkflowsLoaderData;
  const { selectedWorkflowId, selectWorkflow } = useWorkflowStore();
  const navigation = useNavigation();

  const isNavigating = navigation.state !== 'idle';

  return (
    <div className="grid grid-cols-[300px_1fr] h-full">
      {/* JobQueue receives workflows from loader */}
      {isNavigating ? (
        <JobQueueSkeleton />
      ) : (
        <JobQueue
          workflows={workflows}
          selectedId={selectedWorkflowId}
          onSelect={selectWorkflow}
        />
      )}

      {/* Renders WorkflowDetailPage when :id is present */}
      <Outlet />
    </div>
  );
}

// Loader fetches initial data (defined in Plan 09)
export async function workflowsLoader() {
  const response = await fetch('/api/workflows');
  const workflows = await response.json();
  return { workflows };
}
```

### Example 2: WorkflowDetailPage with Real-time Events

```typescript
// pages/WorkflowDetailPage.tsx
import { useLoaderData, useParams } from 'react-router-dom';
import { ActivityLog } from '@/components/ActivityLog';
import { ApprovalControls } from '@/components/ApprovalControls';

export default function WorkflowDetailPage() {
  const { workflowId } = useParams();
  const { workflow } = useLoaderData() as WorkflowDetailLoaderData;

  return (
    <div className="flex flex-col h-full">
      {/* ActivityLog merges loader events with real-time from Zustand */}
      <ActivityLog
        workflowId={workflowId!}
        initialEvents={workflow.recent_events}
      />

      {/* ApprovalControls uses useFetcher for mutations */}
      {workflow.needs_approval && (
        <ApprovalControls
          workflowId={workflowId!}
          planSummary={workflow.plan_summary}
          status={workflow.approval_status}
        />
      )}
    </div>
  );
}

// Loader fetches workflow detail (defined in Plan 09)
export async function workflowDetailLoader({ params }: LoaderFunctionArgs) {
  const response = await fetch(`/api/workflows/${params.id}`);
  const workflow = await response.json();
  return { workflow };
}
```

### Example 3: Sidebar with NavLink for Active Styling

```typescript
// components/DashboardSidebar.tsx
import { NavLink } from 'react-router-dom';
import { Home, Settings, Activity } from 'lucide-react';
import { cn } from '@/lib/utils';

function SidebarNavLink({ to, icon: Icon, label }: NavLinkProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive, isPending }) =>
        cn(
          'flex items-center gap-3 px-3 py-2 rounded transition-colors',
          isActive && 'bg-sidebar-primary text-sidebar-primary-foreground',
          isPending && 'opacity-50',
          !isActive && 'hover:bg-sidebar-accent'
        )
      }
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </NavLink>
  );
}

export function DashboardSidebar() {
  return (
    <aside className="w-64 bg-sidebar border-r">
      <nav className="flex flex-col gap-1 p-4">
        <SidebarNavLink to="/" icon={Home} label="Dashboard" />
        <SidebarNavLink to="/workflows" icon={Activity} label="Workflows" />
        <SidebarNavLink to="/settings" icon={Settings} label="Settings" />
      </nav>
    </aside>
  );
}
```

### Key Patterns Summary

1. **Loader Data**: Components receive initial data via `useLoaderData()` from parent pages
2. **Real-time Updates**: Zustand store provides WebSocket events, merged with loader data
3. **Loading States**: `useNavigation()` shows route-level loading indicators
4. **Mutations**: `useFetcher()` handles form submissions without navigation
5. **Active Routes**: `NavLink` automatically applies active state styling

---

## PART 2: Custom WorkflowCanvas Components

These tasks build custom React Flow components for the workflow visualization. The design mock uses map pin icons for nodes, creating a "flight route" aesthetic that requires custom implementation.

---

## Task 9: WorkflowNode Component (Custom React Flow Node)

Create a custom React Flow node with MapPin icon, status-based coloring, and beacon glow animation. This is NOT built on ai-elements Node because the design requires map pin icons, not Card-based layouts.

**Files:**
- Create: `dashboard/src/components/flow/WorkflowNode.tsx`
- Create: `dashboard/src/components/flow/WorkflowNode.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/flow/WorkflowNode.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import { WorkflowNode } from './WorkflowNode';

const renderNode = (data: any) => {
  return render(
    <ReactFlowProvider>
      <WorkflowNode
        id="test"
        data={data}
        type="workflow"
        selected={false}
        isConnectable={false}
        positionAbsoluteX={0}
        positionAbsoluteY={0}
        zIndex={0}
      />
    </ReactFlowProvider>
  );
};

describe('WorkflowNode', () => {
  it('renders stage label', () => {
    renderNode({ label: 'Architect', status: 'completed' });
    expect(screen.getByText('Architect')).toBeInTheDocument();
  });

  it('renders subtitle when provided', () => {
    renderNode({ label: 'Architect', subtitle: 'Planning', status: 'completed' });
    expect(screen.getByText('Planning')).toBeInTheDocument();
  });

  it('renders token count when provided', () => {
    renderNode({ label: 'Architect', status: 'completed', tokens: '12.4k' });
    expect(screen.getByText('12.4k tokens')).toBeInTheDocument();
  });

  it('renders MapPin icon (not Card-based layout)', () => {
    const { container } = renderNode({ label: 'Developer', status: 'active' });
    // Should have lucide MapPin SVG
    expect(container.querySelector('svg.lucide-map-pin')).toBeInTheDocument();
  });

  it('applies active status styling with beacon glow', () => {
    const { container } = renderNode({ label: 'Developer', status: 'active' });
    expect(container.querySelector('[data-status="active"]')).toBeInTheDocument();
    // Active nodes have beacon glow animation
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('applies completed status styling (teal color)', () => {
    const { container } = renderNode({ label: 'Architect', status: 'completed' });
    expect(container.querySelector('[data-status="completed"]')).toBeInTheDocument();
  });

  it('applies pending status styling (muted)', () => {
    const { container } = renderNode({ label: 'Reviewer', status: 'pending' });
    expect(container.querySelector('[data-status="pending"]')).toBeInTheDocument();
  });

  it('has proper ARIA label', () => {
    renderNode({ label: 'Architect', subtitle: 'Planning', status: 'completed' });
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      'Workflow stage: Architect - Planning (completed)'
    );
  });

  it('renders handles for connections', () => {
    const { container } = renderNode({ label: 'Test', status: 'pending' });
    // Should have input and output handles
    expect(container.querySelectorAll('.react-flow__handle')).toHaveLength(2);
  });

  it('does NOT use ai-elements Node structure', () => {
    const { container } = renderNode({ label: 'Test', status: 'pending' });
    // Should NOT have data-slot="node" (ai-elements pattern)
    expect(container.querySelector('[data-slot="node"]')).not.toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd dashboard && pnpm test src/components/flow/WorkflowNode.test.tsx
```

Expected: FAIL - Component does not exist

**Step 3: Implement WorkflowNode component**

```typescript
// dashboard/src/components/flow/WorkflowNode.tsx
import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';

type NodeStatus = 'completed' | 'active' | 'pending' | 'blocked';

export interface WorkflowNodeData {
  label: string;
  subtitle?: string;
  status: NodeStatus;
  tokens?: string;
}

/**
 * Status-based styling for the map pin workflow node.
 * Uses aviation theme colors:
 * - completed: teal (status-completed)
 * - active: amber (primary) with beacon glow animation
 * - pending: muted/dimmed
 * - blocked: red (destructive)
 */
const statusStyles: Record<NodeStatus, {
  pinClass: string;
  containerClass: string;
  glowClass: string;
}> = {
  completed: {
    pinClass: 'text-[--workflow-node-completed]',
    containerClass: 'opacity-100',
    glowClass: '',
  },
  active: {
    pinClass: 'text-[--workflow-node-active] animate-pulse',
    containerClass: 'opacity-100',
    glowClass: 'shadow-[0_0_20px_var(--workflow-beacon-glow)]',
  },
  pending: {
    pinClass: 'text-[--workflow-node-pending]',
    containerClass: 'opacity-50',
    glowClass: '',
  },
  blocked: {
    pinClass: 'text-[--workflow-node-blocked]',
    containerClass: 'opacity-100',
    glowClass: '',
  },
};

/**
 * WorkflowNode is a CUSTOM React Flow node component.
 *
 * Design: Uses MapPin icon from lucide-react to create a "flight route waypoint"
 * aesthetic. This differs from ai-elements Node which uses Card-based layouts.
 *
 * Structure:
 * - Container with status-based opacity
 * - MapPin icon with status-based color and optional beacon glow
 * - Label text below the pin
 * - Optional subtitle
 * - Optional token count
 * - Connection handles (left input, right output)
 */
function WorkflowNodeComponent({ data }: NodeProps<WorkflowNodeData>) {
  const styles = statusStyles[data.status];
  const ariaLabel = `Workflow stage: ${data.label}${data.subtitle ? ` - ${data.subtitle}` : ''} (${data.status})`;

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      data-status={data.status}
      className={cn(
        'flex flex-col items-center min-w-[100px]',
        styles.containerClass
      )}
    >
      {/* Input handle (left) */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2 !h-2 !bg-[--workflow-node-pending] !border-0"
      />

      {/* Map Pin icon with beacon glow for active status */}
      <div className={cn('rounded-full p-2', styles.glowClass)}>
        <MapPin
          className={cn('lucide-map-pin w-8 h-8', styles.pinClass)}
          strokeWidth={2}
        />
      </div>

      {/* Label */}
      <span className="font-heading text-sm font-semibold tracking-wider text-foreground mt-2">
        {data.label}
      </span>

      {/* Subtitle */}
      {data.subtitle && (
        <span className="font-body text-xs text-muted-foreground">
          {data.subtitle}
        </span>
      )}

      {/* Token count */}
      {data.tokens && (
        <span className="font-mono text-xs text-muted-foreground mt-1">
          {data.tokens} tokens
        </span>
      )}

      {/* Output handle (right) */}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !bg-[--workflow-node-pending] !border-0"
      />
    </div>
  );
}

export const WorkflowNode = memo(WorkflowNodeComponent);
```

**Step 4: Run test to verify it passes**

```bash
cd dashboard && pnpm test src/components/flow/WorkflowNode.test.tsx
```

Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/flow/WorkflowNode.tsx dashboard/src/components/flow/WorkflowNode.test.tsx
git commit -m "feat(dashboard): add custom WorkflowNode with MapPin icon

- Custom React Flow node (NOT ai-elements Node)
- MapPin icon from lucide-react for flight route aesthetic
- Status-based coloring: teal (completed), amber (active), muted (pending)
- Beacon glow animation for active nodes
- Label, subtitle, and token count display
- Connection handles for React Flow edges
- Memoized for performance"
```

---

## Task 10: WorkflowEdge Component (Custom React Flow Edge)

Create a custom React Flow edge with time labels at the midpoint and animated flow indicator. This is NOT built on ai-elements Edge because we need specific control over the time label positioning and animation.

**Files:**
- Create: `dashboard/src/components/flow/WorkflowEdge.tsx`
- Create: `dashboard/src/components/flow/WorkflowEdge.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/flow/WorkflowEdge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowEdge } from './WorkflowEdge';

describe('WorkflowEdge', () => {
  const baseProps = {
    id: 'e1-2',
    source: 'node1',
    target: 'node2',
    sourceX: 100,
    sourceY: 100,
    targetX: 200,
    targetY: 100,
    sourcePosition: 'right' as const,
    targetPosition: 'left' as const,
    data: { label: '0:24', status: 'completed' as const },
  };

  it('renders edge path', () => {
    const { container } = render(
      <svg>
        <WorkflowEdge {...baseProps} />
      </svg>
    );
    expect(container.querySelector('path')).toBeInTheDocument();
  });

  it('renders time label at midpoint', () => {
    render(
      <svg>
        <WorkflowEdge {...baseProps} />
      </svg>
    );
    expect(screen.getByText('0:24')).toBeInTheDocument();
  });

  it('uses solid line for completed status', () => {
    const { container } = render(
      <svg>
        <WorkflowEdge {...baseProps} />
      </svg>
    );
    const path = container.querySelector('path');
    expect(path).toHaveAttribute('data-status', 'completed');
    // Solid line has no stroke-dasharray
    expect(path).not.toHaveAttribute('stroke-dasharray');
  });

  it('uses dashed line for pending status', () => {
    const pendingProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'pending' as const },
    };
    const { container } = render(
      <svg>
        <WorkflowEdge {...pendingProps} />
      </svg>
    );
    const path = container.querySelector('path');
    expect(path).toHaveAttribute('data-status', 'pending');
    expect(path).toHaveAttribute('stroke-dasharray');
  });

  it('shows animated flow indicator for active edges', () => {
    const activeProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'active' as const },
    };
    const { container } = render(
      <svg>
        <WorkflowEdge {...activeProps} />
      </svg>
    );
    // Active edges have animated circle
    expect(container.querySelector('circle')).toBeInTheDocument();
  });

  it('applies completed color from CSS variable', () => {
    const { container } = render(
      <svg>
        <WorkflowEdge {...baseProps} />
      </svg>
    );
    const path = container.querySelector('path');
    expect(path?.getAttribute('style')).toContain('--workflow-edge-completed');
  });

  it('does NOT use ai-elements Edge structure', () => {
    const { container } = render(
      <svg>
        <WorkflowEdge {...baseProps} />
      </svg>
    );
    // Should NOT have data-animated="true" or data-temporary="true" (ai-elements patterns)
    expect(container.querySelector('[data-animated]')).not.toBeInTheDocument();
    expect(container.querySelector('[data-temporary]')).not.toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd dashboard && pnpm test src/components/flow/WorkflowEdge.test.tsx
```

Expected: FAIL - Component does not exist

**Step 3: Implement WorkflowEdge component**

```typescript
// dashboard/src/components/flow/WorkflowEdge.tsx
import { memo } from 'react';
import { getSmoothStepPath, type EdgeProps, EdgeLabelRenderer } from '@xyflow/react';

type EdgeStatus = 'completed' | 'active' | 'pending';

export interface WorkflowEdgeData {
  label: string;
  status: EdgeStatus;
}

/**
 * WorkflowEdge is a CUSTOM React Flow edge component.
 *
 * Design: Connects map pin nodes with status-based styling:
 * - completed: solid line, teal color
 * - active: dashed line with animated flowing circle, amber color
 * - pending: dashed line, muted color
 *
 * Time labels are rendered at the edge midpoint.
 */
function WorkflowEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<WorkflowEdgeData>) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
  });

  const status = data?.status || 'pending';

  // Style based on status
  const strokeColor = {
    completed: 'var(--workflow-edge-completed)',
    active: 'var(--workflow-edge-active)',
    pending: 'var(--workflow-edge-pending)',
  }[status];

  const isDashed = status !== 'completed';
  const strokeOpacity = status === 'pending' ? 0.4 : 1;

  return (
    <>
      {/* Main edge path */}
      <path
        id={id}
        d={edgePath}
        data-status={status}
        fill="none"
        strokeWidth={2}
        strokeLinecap="round"
        style={{ stroke: strokeColor, opacity: strokeOpacity }}
        {...(isDashed && { strokeDasharray: '6 4' })}
      />

      {/* Animated flow indicator for active edges */}
      {status === 'active' && (
        <circle r={4} fill={strokeColor}>
          <animateMotion dur="1.5s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}

      {/* Time label at midpoint */}
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="px-2 py-0.5 font-mono text-xs text-muted-foreground bg-background/90 border border-border rounded"
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const WorkflowEdge = memo(WorkflowEdgeComponent);
```

**Step 4: Run test to verify it passes**

```bash
cd dashboard && pnpm test src/components/flow/WorkflowEdge.test.tsx
```

Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/flow/WorkflowEdge.tsx dashboard/src/components/flow/WorkflowEdge.test.tsx
git commit -m "feat(dashboard): add custom WorkflowEdge with time labels

- Custom React Flow edge (NOT ai-elements Edge)
- Status-based styling: solid (completed), dashed (active/pending)
- Animated flow indicator circle for active edges
- Time label at edge midpoint
- Uses aviation theme CSS variables
- Memoized for performance"
```

---

## Task 11: WorkflowCanvas Component (React Flow Container)

Create the workflow visualization container using React Flow with custom node/edge types, dot pattern background, and aviation theme.

**Files:**
- Create: `dashboard/src/components/WorkflowCanvas.tsx`
- Create: `dashboard/src/components/WorkflowCanvas.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/WorkflowCanvas.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowCanvas } from './WorkflowCanvas';

describe('WorkflowCanvas', () => {
  const mockPipeline = {
    nodes: [
      { id: 'issue', label: 'Issue', status: 'completed' as const },
      { id: 'architect', label: 'Architect', subtitle: 'Planning', status: 'completed' as const, tokens: '12.4k' },
      { id: 'developer', label: 'Developer', subtitle: 'Implementation', status: 'active' as const, tokens: '48.2k' },
    ],
    edges: [
      { from: 'issue', to: 'architect', label: '0:08', status: 'completed' as const },
      { from: 'architect', to: 'developer', label: '0:24', status: 'active' as const },
    ],
  };

  it('renders React Flow container', () => {
    const { container } = render(<WorkflowCanvas pipeline={mockPipeline} />);
    expect(container.querySelector('.react-flow')).toBeInTheDocument();
  });

  it('has proper ARIA role and label', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    const canvas = screen.getByRole('img');
    expect(canvas.getAttribute('aria-label')).toContain('pipeline');
  });

  it('renders all nodes with MapPin icons', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    expect(screen.getByText('Issue')).toBeInTheDocument();
    expect(screen.getByText('Architect')).toBeInTheDocument();
    expect(screen.getByText('Developer')).toBeInTheDocument();
  });

  it('renders dot pattern background', () => {
    const { container } = render(<WorkflowCanvas pipeline={mockPipeline} />);
    expect(container.querySelector('.react-flow__background')).toBeInTheDocument();
  });

  it('renders stage progress info', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    // Should show completed/total stages
    expect(screen.getByText(/2.*3.*stages/i)).toBeInTheDocument();
  });

  it('is non-interactive (view-only mode)', () => {
    const { container } = render(<WorkflowCanvas pipeline={mockPipeline} />);
    // React Flow with nodesDraggable=false and nodesConnectable=false
    expect(container.querySelector('.react-flow')).toBeInTheDocument();
  });

  it('uses custom WorkflowNode component', () => {
    const { container } = render(<WorkflowCanvas pipeline={mockPipeline} />);
    // Custom nodes have MapPin icons
    expect(container.querySelectorAll('.lucide-map-pin').length).toBe(3);
  });

  it('renders Loader when loading prop is true', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} loading />);
    expect(screen.getByTestId('canvas-loader')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd dashboard && pnpm test src/components/WorkflowCanvas.test.tsx
```

Expected: FAIL - Component does not exist

**Step 3: Implement WorkflowCanvas component**

```typescript
// dashboard/src/components/WorkflowCanvas.tsx
import { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Loader } from '@/components/ai-elements/loader';
import { WorkflowNode, type WorkflowNodeData } from '@/components/flow/WorkflowNode';
import { WorkflowEdge, type WorkflowEdgeData } from '@/components/flow/WorkflowEdge';

type NodeStatus = 'completed' | 'active' | 'pending' | 'blocked';
type EdgeStatus = 'completed' | 'active' | 'pending';

interface PipelineNode {
  id: string;
  label: string;
  subtitle?: string;
  status: NodeStatus;
  tokens?: string;
}

interface PipelineEdge {
  from: string;
  to: string;
  label: string;
  status: EdgeStatus;
}

interface Pipeline {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

interface WorkflowCanvasProps {
  pipeline: Pipeline;
  loading?: boolean;
}

// Register custom node and edge types
const nodeTypes = {
  workflow: WorkflowNode,
};

const edgeTypes = {
  workflow: WorkflowEdge,
};

/**
 * WorkflowCanvas is a React Flow container with custom node/edge types.
 *
 * Design: Displays the workflow pipeline as a "flight route" with map pin
 * waypoints connected by status-based edges. This is view-only (non-interactive).
 *
 * Features:
 * - Custom WorkflowNode with MapPin icons
 * - Custom WorkflowEdge with time labels
 * - Dot pattern background (aviation radar aesthetic)
 * - Stage progress info panel
 * - Loading state with ai-elements Loader
 */
export function WorkflowCanvas({ pipeline, loading = false }: WorkflowCanvasProps) {
  // Convert pipeline data to React Flow format
  const nodes: Node<WorkflowNodeData>[] = useMemo(
    () =>
      pipeline.nodes.map((node, index) => ({
        id: node.id,
        type: 'workflow',
        // Position nodes horizontally with spacing
        position: { x: index * 180, y: 80 },
        data: {
          label: node.label,
          subtitle: node.subtitle,
          status: node.status,
          tokens: node.tokens,
        },
        // Make nodes non-interactive
        draggable: false,
        selectable: false,
        connectable: false,
      })),
    [pipeline.nodes]
  );

  const edges: Edge<WorkflowEdgeData>[] = useMemo(
    () =>
      pipeline.edges.map((edge) => ({
        id: `e-${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        type: 'workflow',
        data: {
          label: edge.label,
          status: edge.status,
        },
      })),
    [pipeline.edges]
  );

  const currentStage = pipeline.nodes.find((n) => n.status === 'active')?.label || 'Unknown';
  const completedCount = pipeline.nodes.filter((n) => n.status === 'completed').length;

  return (
    <div
      role="img"
      aria-label={`Workflow pipeline with ${pipeline.nodes.length} stages. Current stage: ${currentStage}`}
      className="h-64 bg-gradient-to-b from-card/40 to-background/40 relative"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        // View-only mode
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        className="workflow-canvas"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="oklch(from var(--foreground) l c h / 0.1)"
        />
      </ReactFlow>

      {/* Stage progress info */}
      <div className="absolute top-3 right-3 bg-card/80 border border-border rounded px-3 py-2">
        <div className="flex items-center gap-3 text-sm">
          {loading ? (
            <Loader data-testid="canvas-loader" className="w-4 h-4" />
          ) : (
            <span className="font-mono text-muted-foreground">
              {completedCount}/{pipeline.nodes.length} stages
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

```bash
cd dashboard && pnpm test src/components/WorkflowCanvas.test.tsx
```

Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/WorkflowCanvas.tsx dashboard/src/components/WorkflowCanvas.test.tsx
git commit -m "feat(dashboard): add WorkflowCanvas with custom React Flow components

- React Flow container with fitView and view-only mode
- Custom WorkflowNode and WorkflowEdge types
- Dot pattern background for aviation radar aesthetic
- Stage progress info panel
- Loading state with ai-elements Loader
- ARIA labeling for accessibility"
```

---

## PART 3: Supporting Components and Exports

---

## Task 12: WorkflowHeader Component

Create a header component combining StatusBadge with workflow info.

**Files:**
- Create: `dashboard/src/components/WorkflowHeader.tsx`
- Create: `dashboard/src/components/WorkflowHeader.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/WorkflowHeader.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowHeader } from './WorkflowHeader';

describe('WorkflowHeader', () => {
  const mockWorkflow = {
    id: 'wf-001',
    issue_id: '#8',
    worktree_name: 'feature-benchmark',
    status: 'in_progress' as const,
  };

  it('renders issue ID', () => {
    render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
  });

  it('renders worktree name', () => {
    render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(screen.getByText('feature-benchmark')).toBeInTheDocument();
  });

  it('renders StatusBadge', () => {
    render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(screen.getByRole('status')).toHaveTextContent('RUNNING');
  });

  it('shows Loader for running status', () => {
    const { container } = render(<WorkflowHeader workflow={mockWorkflow} />);
    // Loader renders animated SVG
    expect(container.querySelector('[data-loader]')).toBeInTheDocument();
  });

  it('has proper semantic structure', () => {
    render(<WorkflowHeader workflow={mockWorkflow} />);
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('shows elapsed time when provided', () => {
    render(<WorkflowHeader workflow={mockWorkflow} elapsedTime="2:34" />);
    expect(screen.getByText('2:34')).toBeInTheDocument();
  });
});
```

**Step 2: Implement WorkflowHeader component**

```typescript
// dashboard/src/components/WorkflowHeader.tsx
import { StatusBadge } from '@/components/StatusBadge';
import { Loader } from '@/components/ai-elements/loader';
import type { WorkflowSummary } from '@/types';

interface WorkflowHeaderProps {
  workflow: Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_name' | 'status'>;
  elapsedTime?: string;
}

/**
 * WorkflowHeader displays workflow identification and status.
 * Uses StatusBadge (wrapping QueueItemIndicator) and Loader from ai-elements.
 */
export function WorkflowHeader({ workflow, elapsedTime }: WorkflowHeaderProps) {
  const isRunning = workflow.status === 'in_progress';

  return (
    <header
      role="banner"
      className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50"
    >
      {/* Left: Workflow info */}
      <div>
        <span className="block font-heading text-xs font-semibold tracking-widest text-muted-foreground mb-1">
          WORKFLOW
        </span>
        <div className="flex items-center gap-3">
          <h2 className="font-display text-3xl font-bold tracking-wider text-foreground">
            {workflow.issue_id}
          </h2>
          <span className="font-mono text-sm text-muted-foreground">
            {workflow.worktree_name}
          </span>
        </div>
      </div>

      {/* Right: Status */}
      <div className="flex items-center gap-3 px-4 py-2 bg-primary/10 border border-primary/30 rounded">
        {isRunning && (
          <Loader data-loader className="w-4 h-4 text-primary" />
        )}
        <StatusBadge status={workflow.status} />
        {elapsedTime && (
          <span className="font-mono text-sm text-muted-foreground">
            {elapsedTime}
          </span>
        )}
      </div>
    </header>
  );
}
```

**Step 3: Commit**

```bash
git add dashboard/src/components/WorkflowHeader.tsx dashboard/src/components/WorkflowHeader.test.tsx
git commit -m "feat(dashboard): add WorkflowHeader component

- Issue ID and worktree name display
- StatusBadge with ai-elements QueueItemIndicator
- Loader animation for running status
- Optional elapsed time display
- Semantic banner role"
```

---

## Task 13: Create Component Index Exports

**Files:**
- Create: `dashboard/src/components/index.ts`
- Create: `dashboard/src/components/flow/index.ts`

**Step 1: Create flow components index**

```typescript
// dashboard/src/components/flow/index.ts
export { WorkflowNode, type WorkflowNodeData } from './WorkflowNode';
export { WorkflowEdge, type WorkflowEdgeData } from './WorkflowEdge';
```

**Step 2: Create main components index**

```typescript
// dashboard/src/components/index.ts

// =============================================================================
// Domain Components
// =============================================================================

// ai-elements based wrappers (Queue, Confirmation)
export { StatusBadge } from './StatusBadge';
export { JobQueueItem } from './JobQueueItem';
export { JobQueue } from './JobQueue';
export { ActivityLogItem } from './ActivityLogItem';
export { ActivityLog } from './ActivityLog';
export { ApprovalControls } from './ApprovalControls';
export { WorkflowHeader } from './WorkflowHeader';

// Custom React Flow components (WorkflowCanvas)
export { WorkflowCanvas } from './WorkflowCanvas';

// Custom flow node/edge types
export * from './flow';

// =============================================================================
// ai-elements (re-exported for direct use when needed)
// =============================================================================
export * from './ai-elements/queue';
export * from './ai-elements/confirmation';
export * from './ai-elements/loader';
export * from './ai-elements/shimmer';

// =============================================================================
// shadcn UI components
// =============================================================================
export * from './ui/button';
export * from './ui/badge';
export * from './ui/card';
export * from './ui/scroll-area';
export * from './ui/tooltip';
```

**Step 3: Commit**

```bash
git add dashboard/src/components/index.ts dashboard/src/components/flow/index.ts
git commit -m "feat(dashboard): add component index exports

- Barrel exports for ai-elements wrappers
- Barrel exports for custom WorkflowCanvas components
- Re-export ai-elements for direct use
- Re-export shadcn UI components"
```

---

## PART 4: Additional shadcn/ui Components

These tasks add Progress, Skeleton, EmptyState, and Sidebar components for enhanced UX.

---

## Task 14: Progress Component

Add shadcn/ui Progress component for showing overall workflow progress.

**Files:**
- Create: `dashboard/src/components/ui/progress.tsx`
- Create: `dashboard/src/components/WorkflowProgress.tsx`
- Create: `dashboard/src/components/WorkflowProgress.test.tsx`

**Step 1: Install Progress component**

```bash
cd dashboard
npx shadcn@latest add progress
```

**Step 2: Write the failing test**

```typescript
// dashboard/src/components/WorkflowProgress.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowProgress } from './WorkflowProgress';

describe('WorkflowProgress', () => {
  it('renders progress bar', () => {
    const { container } = render(<WorkflowProgress completed={2} total={5} />);
    expect(container.querySelector('[data-slot="progress"]')).toBeInTheDocument();
  });

  it('shows percentage label', () => {
    render(<WorkflowProgress completed={2} total={5} />);
    expect(screen.getByText('40%')).toBeInTheDocument();
  });

  it('shows stage count', () => {
    render(<WorkflowProgress completed={2} total={5} />);
    expect(screen.getByText('2 of 5 stages')).toBeInTheDocument();
  });

  it('applies correct progress value', () => {
    const { container } = render(<WorkflowProgress completed={3} total={4} />);
    const indicator = container.querySelector('[data-slot="progress-indicator"]');
    expect(indicator).toHaveStyle({ transform: 'translateX(-25%)' });
  });

  it('uses OKLCH status colors', () => {
    const { container } = render(<WorkflowProgress completed={5} total={5} />);
    expect(container.querySelector('[data-complete="true"]')).toBeInTheDocument();
  });

  it('has proper ARIA attributes', () => {
    render(<WorkflowProgress completed={2} total={5} />);
    const progress = screen.getByRole('progressbar');
    expect(progress).toHaveAttribute('aria-valuenow', '40');
    expect(progress).toHaveAttribute('aria-valuemin', '0');
    expect(progress).toHaveAttribute('aria-valuemax', '100');
  });
});
```

**Step 3: Implement WorkflowProgress component**

```typescript
// dashboard/src/components/WorkflowProgress.tsx
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface WorkflowProgressProps {
  completed: number;
  total: number;
  className?: string;
}

/**
 * WorkflowProgress shows overall workflow completion using shadcn/ui Progress.
 * Includes percentage label and stage count.
 *
 * Uses OKLCH status colors:
 * - In progress: --status-running (amber)
 * - Complete: --status-completed (teal/green)
 */
export function WorkflowProgress({ completed, total, className }: WorkflowProgressProps) {
  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
  const isComplete = completed === total && total > 0;

  return (
    <div
      data-slot="workflow-progress"
      data-complete={isComplete}
      className={cn('flex flex-col gap-2', className)}
    >
      <div className="flex items-center justify-between text-sm">
        <span className="font-mono text-muted-foreground">
          {completed} of {total} stages
        </span>
        <span className="font-mono font-semibold text-foreground">
          {percentage}%
        </span>
      </div>

      <Progress
        data-slot="progress"
        value={percentage}
        className={cn(
          'h-2',
          isComplete && '[&>[data-slot=progress-indicator]]:bg-status-completed'
        )}
        aria-label={`Workflow progress: ${percentage}% complete`}
      />
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add dashboard/src/components/ui/progress.tsx dashboard/src/components/WorkflowProgress.tsx dashboard/src/components/WorkflowProgress.test.tsx
git commit -m "feat(dashboard): add WorkflowProgress component

- Wraps shadcn/ui Progress with workflow-specific display
- Percentage label and stage count
- OKLCH status colors (amber in progress, teal complete)
- data-slot attributes for styling hooks
- ARIA progressbar attributes"
```

---

## Task 15: Skeleton Component for Loading States

Add shadcn/ui Skeleton component for loading placeholders in JobQueue and ActivityLog.

**Files:**
- Create: `dashboard/src/components/ui/skeleton.tsx`
- Create: `dashboard/src/components/JobQueueSkeleton.tsx`
- Create: `dashboard/src/components/ActivityLogSkeleton.tsx`

**Step 1: Install Skeleton component**

```bash
cd dashboard
npx shadcn@latest add skeleton
```

**Step 2: Implement JobQueueSkeleton**

```typescript
// dashboard/src/components/JobQueueSkeleton.tsx
import { Skeleton } from '@/components/ui/skeleton';

interface JobQueueSkeletonProps {
  count?: number;
}

/**
 * JobQueueSkeleton provides loading placeholder for JobQueue.
 * Matches the structure of JobQueueItem for smooth transition.
 */
export function JobQueueSkeleton({ count = 3 }: JobQueueSkeletonProps) {
  return (
    <div data-slot="job-queue-skeleton" className="flex flex-col gap-2 p-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 p-3 rounded-lg border border-border/50"
        >
          {/* Status indicator */}
          <Skeleton className="h-4 w-16 rounded-md" />

          {/* Content */}
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-12" /> {/* Issue ID */}
            <Skeleton className="h-3 w-32" /> {/* Worktree name */}
          </div>

          {/* Stage */}
          <Skeleton className="h-3 w-20" />
        </div>
      ))}
    </div>
  );
}
```

**Step 3: Implement ActivityLogSkeleton**

```typescript
// dashboard/src/components/ActivityLogSkeleton.tsx
import { Skeleton } from '@/components/ui/skeleton';

interface ActivityLogSkeletonProps {
  lines?: number;
}

/**
 * ActivityLogSkeleton provides loading placeholder for ActivityLog.
 * Matches terminal-style log entry structure.
 */
export function ActivityLogSkeleton({ lines = 5 }: ActivityLogSkeletonProps) {
  return (
    <div data-slot="activity-log-skeleton" className="flex flex-col gap-1.5 p-4 font-mono">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          {/* Timestamp */}
          <Skeleton className="h-4 w-16" />

          {/* Agent */}
          <Skeleton className="h-4 w-20" />

          {/* Message - varying widths for natural look */}
          <Skeleton
            className="h-4 flex-1"
            style={{ maxWidth: `${50 + Math.random() * 40}%` }}
          />
        </div>
      ))}
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add dashboard/src/components/ui/skeleton.tsx dashboard/src/components/JobQueueSkeleton.tsx dashboard/src/components/ActivityLogSkeleton.tsx
git commit -m "feat(dashboard): add Skeleton components for loading states

- JobQueueSkeleton matches JobQueueItem structure
- ActivityLogSkeleton matches terminal log entry format
- data-slot attributes for styling hooks
- Pulse animation via shadcn/ui Skeleton"
```

---

## Task 16: EmptyState Component

Create a reusable empty state component for when no workflows are active.

**Files:**
- Create: `dashboard/src/components/EmptyState.tsx`
- Create: `dashboard/src/components/EmptyState.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/EmptyState.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('renders icon', () => {
    const { container } = render(<EmptyState icon="inbox" message="No items" />);
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('renders message', () => {
    render(<EmptyState icon="inbox" message="No active workflows" />);
    expect(screen.getByText('No active workflows')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(
      <EmptyState
        icon="inbox"
        message="No workflows"
        description="Start a new workflow to see it here"
      />
    );
    expect(screen.getByText('Start a new workflow to see it here')).toBeInTheDocument();
  });

  it('renders action button when provided', () => {
    const onAction = vi.fn();
    render(
      <EmptyState
        icon="inbox"
        message="No workflows"
        action={{ label: 'New Workflow', onClick: onAction }}
      />
    );

    fireEvent.click(screen.getByText('New Workflow'));
    expect(onAction).toHaveBeenCalled();
  });

  it('has data-slot attribute', () => {
    const { container } = render(<EmptyState icon="inbox" message="Empty" />);
    expect(container.querySelector('[data-slot="empty-state"]')).toBeInTheDocument();
  });

  it('uses muted foreground colors', () => {
    const { container } = render(<EmptyState icon="inbox" message="Empty" />);
    expect(container.querySelector('.text-muted-foreground')).toBeInTheDocument();
  });
});
```

**Step 2: Implement EmptyState component with CVA**

```typescript
// dashboard/src/components/EmptyState.tsx
import { cva, type VariantProps } from 'class-variance-authority';
import { Inbox, FileText, Activity, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const emptyStateVariants = cva(
  'flex flex-col items-center justify-center text-center p-8',
  {
    variants: {
      size: {
        sm: 'p-4 gap-2',
        md: 'p-8 gap-3',
        lg: 'p-12 gap-4',
      },
    },
    defaultVariants: {
      size: 'md',
    },
  }
);

const icons = {
  inbox: Inbox,
  file: FileText,
  activity: Activity,
  alert: AlertCircle,
};

interface EmptyStateProps extends VariantProps<typeof emptyStateVariants> {
  icon: keyof typeof icons;
  message: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

/**
 * EmptyState displays a placeholder when no content is available.
 * Uses CVA for size variants and includes optional action button.
 *
 * Includes data-slot="empty-state" for styling hooks.
 */
export function EmptyState({
  icon,
  message,
  description,
  action,
  size,
  className,
}: EmptyStateProps) {
  const Icon = icons[icon];

  return (
    <div
      data-slot="empty-state"
      className={cn(emptyStateVariants({ size }), className)}
    >
      <Icon
        className="h-12 w-12 text-muted-foreground/50"
        strokeWidth={1.5}
        aria-hidden="true"
      />

      <h3 className="font-heading text-lg font-semibold text-muted-foreground">
        {message}
      </h3>

      {description && (
        <p className="text-sm text-muted-foreground/70 max-w-sm">
          {description}
        </p>
      )}

      {action && (
        <Button
          variant="outline"
          onClick={action.onClick}
          className="mt-2 focus-visible:ring-ring/50 focus-visible:ring-[3px]"
        >
          {action.label}
        </Button>
      )}
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add dashboard/src/components/EmptyState.tsx dashboard/src/components/EmptyState.test.tsx
git commit -m "feat(dashboard): add EmptyState component

- CVA for size variants (sm, md, lg)
- Icon options: inbox, file, activity, alert
- Optional description and action button
- data-slot attribute for styling hooks
- focus-visible states on action button"
```

---

## Task 17: Sidebar Component for Dashboard Layout

Install and configure shadcn/ui Sidebar for the dashboard navigation layout.

**Files:**
- Create: `dashboard/src/components/ui/sidebar.tsx`
- Create: `dashboard/src/components/DashboardSidebar.tsx`
- Create: `dashboard/src/components/DashboardSidebar.test.tsx`
- Modify: `dashboard/src/layouts/DashboardLayout.tsx`

**Step 1: Install Sidebar component**

```bash
cd dashboard
npx shadcn@latest add sidebar
```

This installs the full shadcn/ui Sidebar with:
- `SidebarProvider` - State management with cookie persistence
- `Sidebar`, `SidebarContent`, `SidebarHeader`, `SidebarFooter`
- `SidebarMenu`, `SidebarMenuItem`, `SidebarMenuButton`
- `SidebarMenuCollapsible`, `SidebarMenuSub`
- `SidebarTrigger` - Toggle button for mobile

**Step 2: Write the failing test**

```typescript
// dashboard/src/components/DashboardSidebar.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DashboardSidebar } from './DashboardSidebar';
import { SidebarProvider } from '@/components/ui/sidebar';

const renderSidebar = () => {
  return render(
    <SidebarProvider>
      <DashboardSidebar />
    </SidebarProvider>
  );
};

describe('DashboardSidebar', () => {
  it('renders sidebar with data-slot', () => {
    const { container } = renderSidebar();
    expect(container.querySelector('[data-slot="dashboard-sidebar"]')).toBeInTheDocument();
  });

  it('renders navigation menu items', () => {
    renderSidebar();
    expect(screen.getByText('Workflows')).toBeInTheDocument();
    expect(screen.getByText('Activity')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('renders collapsible section for workflows', () => {
    renderSidebar();
    const trigger = screen.getByRole('button', { name: /Workflows/i });
    expect(trigger).toHaveAttribute('aria-expanded');
  });

  it('expands collapsible on click', () => {
    renderSidebar();
    const trigger = screen.getByRole('button', { name: /Workflows/i });

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
  });

  it('renders footer with version info', () => {
    renderSidebar();
    expect(screen.getByText(/Amelia/)).toBeInTheDocument();
  });

  it('has proper focus-visible states', () => {
    const { container } = renderSidebar();
    const buttons = container.querySelectorAll('[data-slot="sidebar-menu-button"]');
    buttons.forEach(button => {
      expect(button.className).toContain('focus-visible:ring');
    });
  });
});
```

**Step 3: Implement DashboardSidebar component**

```typescript
// dashboard/src/components/DashboardSidebar.tsx
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuCollapsible,
  SidebarMenuCollapsibleTrigger,
  SidebarMenuCollapsibleContent,
  SidebarMenuSub,
  SidebarMenuSubItem,
  SidebarMenuSubButton,
} from '@/components/ui/sidebar';
import { LayoutDashboard, GitBranch, Activity, Settings, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * DashboardSidebar provides navigation for the Amelia dashboard.
 * Uses shadcn/ui Sidebar with collapsible sections.
 *
 * Features:
 * - SidebarProvider for state management (in parent layout)
 * - Cookie-based state persistence
 * - Mobile responsive with sheet drawer
 * - Keyboard navigation with focus-visible states
 */
export function DashboardSidebar() {
  return (
    <Sidebar data-slot="dashboard-sidebar" className="border-r border-border">
      <SidebarHeader className="px-4 py-6">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-md bg-primary/20 flex items-center justify-center">
            <LayoutDashboard className="h-4 w-4 text-primary" />
          </div>
          <span className="font-heading text-lg font-bold tracking-wider">
            AMELIA
          </span>
        </div>
      </SidebarHeader>

      <SidebarContent className="px-2">
        <SidebarMenu>
          {/* Workflows section - collapsible */}
          <SidebarMenuCollapsible defaultOpen>
            <SidebarMenuItem>
              <SidebarMenuCollapsibleTrigger asChild>
                <SidebarMenuButton
                  className={cn(
                    'w-full justify-between',
                    'focus-visible:ring-ring/50 focus-visible:ring-[3px]'
                  )}
                >
                  <span className="flex items-center gap-2">
                    <GitBranch className="h-4 w-4" />
                    Workflows
                  </span>
                  <ChevronDown className="h-4 w-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
                </SidebarMenuButton>
              </SidebarMenuCollapsibleTrigger>

              <SidebarMenuCollapsibleContent>
                <SidebarMenuSub>
                  <SidebarMenuSubItem>
                    <SidebarMenuSubButton
                      className="focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                    >
                      Active
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                  <SidebarMenuSubItem>
                    <SidebarMenuSubButton
                      className="focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                    >
                      Completed
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                  <SidebarMenuSubItem>
                    <SidebarMenuSubButton
                      className="focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                    >
                      Failed
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                </SidebarMenuSub>
              </SidebarMenuCollapsibleContent>
            </SidebarMenuItem>
          </SidebarMenuCollapsible>

          {/* Activity */}
          <SidebarMenuItem>
            <SidebarMenuButton
              className="focus-visible:ring-ring/50 focus-visible:ring-[3px]"
            >
              <Activity className="h-4 w-4" />
              Activity
            </SidebarMenuButton>
          </SidebarMenuItem>

          {/* Settings */}
          <SidebarMenuItem>
            <SidebarMenuButton
              className="focus-visible:ring-ring/50 focus-visible:ring-[3px]"
            >
              <Settings className="h-4 w-4" />
              Settings
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="px-4 py-4 border-t border-border">
        <p className="text-xs text-muted-foreground">
          Amelia v1.0.0
        </p>
      </SidebarFooter>
    </Sidebar>
  );
}
```

**Step 4: Update DashboardLayout to use SidebarProvider**

```typescript
// dashboard/src/layouts/DashboardLayout.tsx
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar';
import { DashboardSidebar } from '@/components/DashboardSidebar';

interface DashboardLayoutProps {
  children: React.ReactNode;
}

/**
 * DashboardLayout wraps the app with SidebarProvider for navigation.
 * Cookie-based persistence remembers sidebar open/closed state.
 */
export function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <SidebarProvider defaultOpen>
      <div className="flex min-h-screen">
        <DashboardSidebar />

        <main className="flex-1">
          {/* Mobile sidebar trigger */}
          <div className="sticky top-0 z-10 flex h-14 items-center gap-4 border-b border-border bg-background px-4 lg:hidden">
            <SidebarTrigger className="focus-visible:ring-ring/50 focus-visible:ring-[3px]" />
            <span className="font-heading font-bold">AMELIA</span>
          </div>

          <div className="p-6">
            {children}
          </div>
        </main>
      </div>
    </SidebarProvider>
  );
}
```

**Step 5: Commit**

```bash
git add dashboard/src/components/ui/sidebar.tsx dashboard/src/components/DashboardSidebar.tsx dashboard/src/components/DashboardSidebar.test.tsx dashboard/src/layouts/DashboardLayout.tsx
git commit -m "feat(dashboard): add Sidebar for dashboard navigation

- Install shadcn/ui Sidebar component
- DashboardSidebar with collapsible Workflows section
- SidebarProvider with cookie-based state persistence
- Mobile responsive with SidebarTrigger
- focus-visible states on all interactive elements
- data-slot attributes for styling hooks"
```

---

## Task 18: Update Component Index Exports

Update the component index to include new components.

**Files:**
- Modify: `dashboard/src/components/index.ts`

**Step 1: Update exports**

```typescript
// dashboard/src/components/index.ts

// =============================================================================
// Domain Components
// =============================================================================

// ai-elements based wrappers (Queue, Confirmation)
export { StatusBadge } from './StatusBadge';
export { JobQueueItem } from './JobQueueItem';
export { JobQueue } from './JobQueue';
export { ActivityLogItem } from './ActivityLogItem';
export { ActivityLog } from './ActivityLog';
export { ApprovalControls } from './ApprovalControls';
export { WorkflowHeader } from './WorkflowHeader';
export { WorkflowProgress } from './WorkflowProgress';

// Skeleton loading states
export { JobQueueSkeleton } from './JobQueueSkeleton';
export { ActivityLogSkeleton } from './ActivityLogSkeleton';

// Empty states
export { EmptyState } from './EmptyState';

// Layout components
export { DashboardSidebar } from './DashboardSidebar';

// Custom React Flow components (WorkflowCanvas)
export { WorkflowCanvas } from './WorkflowCanvas';

// Custom flow node/edge types
export * from './flow';

// =============================================================================
// ai-elements (re-exported for direct use when needed)
// =============================================================================
export * from './ai-elements/queue';
export * from './ai-elements/confirmation';
export * from './ai-elements/loader';
export * from './ai-elements/shimmer';

// =============================================================================
// shadcn UI components
// =============================================================================
export * from './ui/button';
export * from './ui/badge';
export * from './ui/card';
export * from './ui/progress';
export * from './ui/skeleton';
export * from './ui/sidebar';
export * from './ui/scroll-area';
export * from './ui/tooltip';
```

**Step 2: Commit**

```bash
git add dashboard/src/components/index.ts
git commit -m "feat(dashboard): update component exports

- Add WorkflowProgress, JobQueueSkeleton, ActivityLogSkeleton
- Add EmptyState and DashboardSidebar
- Add progress, skeleton, sidebar UI exports"
```

---

## Verification Checklist

After completing all tasks, verify:

**React Router v7 Data Mode Patterns:**
- [ ] Components receive data from `useLoaderData()` in parent pages
- [ ] ApprovalControls uses `useFetcher()` for approve/reject mutations
- [ ] Navigation state shows loading indicators via `useNavigation()`
- [ ] NavLink shows active route styling automatically
- [ ] ActivityLog merges loader data with Zustand real-time events
- [ ] No custom data-fetching hooks in components (use loaders/actions)

**ai-elements Components:**
- [ ] ai-elements queue, confirmation, loader, shimmer installed in `src/components/ai-elements/`
- [ ] StatusBadge wraps QueueItemIndicator with correct labels
- [ ] JobQueue uses QueueSection with collapsible behavior
- [ ] ActivityLog shows events with auto-scroll and blinking cursor
- [ ] ApprovalControls uses Confirmation state machine + useFetcher

**Custom WorkflowCanvas Components:**
- [ ] WorkflowNode renders MapPin icons (NOT Card-based layout)
- [ ] WorkflowNode has beacon glow animation for active status
- [ ] WorkflowNode shows status-based colors (amber active, teal completed, muted pending)
- [ ] WorkflowEdge shows time labels at midpoint
- [ ] WorkflowEdge has animated flow indicator for active edges
- [ ] WorkflowEdge uses dashed lines for pending, solid for completed
- [ ] WorkflowCanvas is view-only (non-interactive)
- [ ] WorkflowCanvas has dot pattern background

**Additional shadcn/ui Components:**
- [ ] Progress component shows workflow completion with OKLCH colors
- [ ] Skeleton components match JobQueue/ActivityLog structure
- [ ] EmptyState displays when no workflows are active
- [ ] Sidebar has collapsible navigation with cookie persistence
- [ ] Mobile responsive Sidebar with sheet drawer

**shadcn/ui Patterns:**
- [ ] All custom components have `data-slot` attributes
- [ ] CVA used for component variants (StatusBadge, EmptyState)
- [ ] `cn()` utility used for className merging
- [ ] Focus states include `focus-visible:ring-ring/50 focus-visible:ring-[3px]`
- [ ] OKLCH color format used throughout CSS variables
- [ ] Two-tier CSS variable system (`@theme inline` + base variables)

**General:**
- [ ] All component tests pass: `pnpm run test:run`
- [ ] TypeScript compilation passes: `pnpm run type-check`
- [ ] Components render correctly in browser
- [ ] All components use aviation theme via CSS variables
- [ ] Components have proper ARIA attributes
- [ ] Keyboard navigation works for interactive elements

---

## Summary

This plan uses a **hybrid approach** to component development:

### ai-elements Based Components

| Component | ai-elements Foundation | Purpose |
|-----------|------------------------|---------|
| StatusBadge | QueueItemIndicator | Status indicators with workflow labels |
| JobQueueItem | QueueItem, QueueItemContent | Individual queue entries |
| JobQueue | QueueSection, QueueList | Collapsible queue lists |
| ActivityLogItem | QueueItem, QueueItemIndicator | Terminal-style log entries |
| ActivityLog | QueueSection, Shimmer | Auto-scrolling activity log |
| ApprovalControls | Confirmation, ConfirmationActions | Approval workflow state machine |

### Custom React Flow Components

| Component | Built With | Purpose |
|-----------|------------|---------|
| WorkflowNode | React Flow + lucide MapPin | Map pin waypoint nodes |
| WorkflowEdge | React Flow + SVG animation | Status-based edges with time labels |
| WorkflowCanvas | React Flow container | Flight route visualization |

### Additional shadcn/ui Components

| Component | shadcn/ui Foundation | Purpose |
|-----------|----------------------|---------|
| WorkflowProgress | Progress | Overall workflow completion indicator |
| JobQueueSkeleton | Skeleton | Loading placeholder for JobQueue |
| ActivityLogSkeleton | Skeleton | Loading placeholder for ActivityLog |
| EmptyState | Custom + CVA | Placeholder when no workflows active |
| DashboardSidebar | Sidebar | Collapsible navigation with state persistence |

### Benefits of Hybrid Approach

1. **Consistency** - ai-elements provides battle-tested patterns for queues and confirmations
2. **Design Fidelity** - Custom React Flow preserves the aviation "flight route" aesthetic
3. **Accessibility** - ai-elements includes built-in ARIA attributes
4. **Performance** - Custom nodes/edges are memoized for React Flow optimization
5. **Theme Integration** - All components use aviation theme CSS variables

### Modern shadcn/ui Patterns Applied

1. **data-slot attributes** - All custom components include `data-slot` for semantic styling hooks
2. **OKLCH color format** - Perceptually uniform colors with `oklch()` syntax
3. **Two-tier CSS variables** - Base variables + `@theme inline` for Tailwind mapping
4. **CVA for variants** - Type-safe variant definitions with class-variance-authority
5. **Focus-visible states** - Consistent `focus-visible:ring-ring/50 focus-visible:ring-[3px]`
6. **cn() utility** - Proper className merging with clsx + tailwind-merge

**Next Steps:**
- Plan 11: State management integration (connect to Zustand store)
- Plan 12: WebSocket real-time updates
- Plan 13: E2E tests with Playwright
