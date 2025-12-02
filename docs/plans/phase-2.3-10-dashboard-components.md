# Dashboard Components & Accessibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the complete React UI for Amelia's web dashboard with aviation-themed components, React Flow integration for pipeline visualization, full accessibility (WCAG AA), and end-to-end tests for multi-workflow selection and approval flow.

**Architecture:** React component library with TypeScript, Tailwind CSS for styling, React Flow for pipeline visualization, Vitest for component tests, Playwright for E2E tests. Components follow atomic design principles (atoms → molecules → organisms → pages).

**Tech Stack:** React 18, TypeScript, Tailwind CSS, React Flow, Vitest, @testing-library/react, Playwright, axe-core

**Depends on:**
- Phase 2.3 Plan 8: React project setup (Vite, TypeScript, Tailwind)
- Phase 2.3 Plan 9: State management (Zustand store, WebSocket hooks)

---

## Task 1: StatusBadge Component (Atom)

**Files:**
- Create: `dashboard/src/components/atoms/StatusBadge.tsx`
- Create: `dashboard/src/components/atoms/StatusBadge.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/atoms/StatusBadge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders RUNNING badge with gold background and dark text', () => {
    render(<StatusBadge status="running" />);
    const badge = screen.getByText('RUNNING');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-accent-gold', 'text-bg-dark');
  });

  it('renders DONE badge with green background', () => {
    render(<StatusBadge status="completed" />);
    const badge = screen.getByText('DONE');
    expect(badge).toHaveClass('bg-status-completed', 'text-bg-dark');
  });

  it('renders QUEUED badge with gray background', () => {
    render(<StatusBadge status="pending" />);
    const badge = screen.getByText('QUEUED');
    expect(badge).toHaveClass('bg-status-pending', 'text-text-primary');
  });

  it('renders BLOCKED badge with red background', () => {
    render(<StatusBadge status="blocked" />);
    const badge = screen.getByText('BLOCKED');
    expect(badge).toHaveClass('bg-status-blocked', 'text-text-primary');
  });

  it('renders CANCELLED badge with red background', () => {
    render(<StatusBadge status="cancelled" />);
    const badge = screen.getByText('CANCELLED');
    expect(badge).toHaveClass('bg-status-failed', 'text-text-primary');
  });

  it('has proper ARIA role and label', () => {
    render(<StatusBadge status="running" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'Workflow status: running');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/atoms/StatusBadge.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Implement StatusBadge component**

```typescript
// dashboard/src/components/atoms/StatusBadge.tsx
import { FC } from 'react';

export type WorkflowStatus = 'running' | 'completed' | 'pending' | 'blocked' | 'cancelled' | 'failed';

interface StatusBadgeProps {
  status: WorkflowStatus;
  className?: string;
}

const statusConfig: Record<WorkflowStatus, { label: string; bgClass: string; textClass: string }> = {
  running: {
    label: 'RUNNING',
    bgClass: 'bg-accent-gold',
    textClass: 'text-bg-dark',
  },
  completed: {
    label: 'DONE',
    bgClass: 'bg-status-completed',
    textClass: 'text-bg-dark',
  },
  pending: {
    label: 'QUEUED',
    bgClass: 'bg-status-pending',
    textClass: 'text-text-primary',
  },
  blocked: {
    label: 'BLOCKED',
    bgClass: 'bg-status-blocked',
    textClass: 'text-text-primary',
  },
  cancelled: {
    label: 'CANCELLED',
    bgClass: 'bg-status-failed',
    textClass: 'text-text-primary',
  },
  failed: {
    label: 'FAILED',
    bgClass: 'bg-status-failed',
    textClass: 'text-text-primary',
  },
};

export const StatusBadge: FC<StatusBadgeProps> = ({ status, className = '' }) => {
  const config = statusConfig[status];

  return (
    <span
      role="status"
      aria-label={`Workflow status: ${status}`}
      className={`
        inline-block
        px-2.5 py-1
        font-heading text-xs font-semibold tracking-wider
        ${config.bgClass}
        ${config.textClass}
        ${className}
      `.trim()}
    >
      {config.label}
    </span>
  );
};
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/atoms/StatusBadge.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/atoms/StatusBadge.tsx dashboard/src/components/atoms/StatusBadge.test.tsx
git commit -m "feat(dashboard): add StatusBadge component with accessibility

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Sidebar Component with Navigation

**Files:**
- Create: `dashboard/src/components/organisms/Sidebar.tsx`
- Create: `dashboard/src/components/organisms/Sidebar.test.tsx`
- Create: `dashboard/src/components/atoms/CompassRose.tsx`
- Create: `dashboard/src/assets/icons.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/organisms/Sidebar.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Sidebar } from './Sidebar';

const renderSidebar = () => {
  return render(
    <BrowserRouter>
      <Sidebar />
    </BrowserRouter>
  );
};

describe('Sidebar', () => {
  it('renders AMELIA logo with subtitle', () => {
    renderSidebar();
    expect(screen.getByText('AMELIA')).toBeInTheDocument();
    expect(screen.getByText('AGENTIC ORCHESTRATOR')).toBeInTheDocument();
  });

  it('renders navigation sections with correct labels', () => {
    renderSidebar();
    expect(screen.getByText('WORKFLOWS')).toBeInTheDocument();
    expect(screen.getByText('HISTORY')).toBeInTheDocument();
    expect(screen.getByText('MONITORING')).toBeInTheDocument();
  });

  it('renders Active Jobs nav item as active', () => {
    renderSidebar();
    const activeJobs = screen.getByText('Active Jobs').closest('a');
    expect(activeJobs).toHaveClass('border-l-accent-gold', 'bg-accent-gold/10');
  });

  it('renders coming soon nav items with badge', () => {
    renderSidebar();
    const agents = screen.getByText('Agents').closest('div');
    expect(agents?.querySelector('[data-testid="coming-soon-badge"]')).toBeInTheDocument();
  });

  it('renders compass rose in footer', () => {
    renderSidebar();
    expect(screen.getByTestId('compass-rose')).toBeInTheDocument();
  });

  it('renders version number', () => {
    renderSidebar();
    expect(screen.getByText('v0.0.1')).toBeInTheDocument();
  });

  it('has proper navigation semantics', () => {
    renderSidebar();
    const nav = screen.getByRole('navigation');
    expect(nav).toHaveAttribute('aria-label', 'Main navigation');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/organisms/Sidebar.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Create icon components**

```typescript
// dashboard/src/assets/icons.tsx
import { FC, SVGProps } from 'react';

export const GitBranchIcon: FC<SVGProps<SVGSVGElement>> = (props) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <line x1="6" y1="3" x2="6" y2="15" />
    <circle cx="18" cy="6" r="3" />
    <circle cx="6" cy="18" r="3" />
    <path d="M18 9a9 9 0 0 1-9 9" />
  </svg>
);

export const UsersIcon: FC<SVGProps<SVGSVGElement>> = (props) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);

export const PackageIcon: FC<SVGProps<SVGSVGElement>> = (props) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <line x1="16.5" y1="9.4" x2="7.5" y2="4.21" />
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
    <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
    <line x1="12" y1="22.08" x2="12" y2="12" />
  </svg>
);

export const HistoryIcon: FC<SVGProps<SVGSVGElement>> = (props) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M3 3v5h5" />
    <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
    <path d="M12 7v5l4 2" />
  </svg>
);

export const TargetIcon: FC<SVGProps<SVGSVGElement>> = (props) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="6" />
    <circle cx="12" cy="12" r="2" />
  </svg>
);

export const CloudIcon: FC<SVGProps<SVGSVGElement>> = (props) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
  </svg>
);

export const RadioIcon: FC<SVGProps<SVGSVGElement>> = (props) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="12" cy="12" r="2" />
    <path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14" />
  </svg>
);

export const SendIcon: FC<SVGProps<SVGSVGElement>> = (props) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);
```

**Step 4: Create CompassRose component**

```typescript
// dashboard/src/components/atoms/CompassRose.tsx
import { FC } from 'react';

export const CompassRose: FC = () => (
  <svg
    width="48"
    height="48"
    viewBox="0 0 48 48"
    data-testid="compass-rose"
    className="opacity-80"
    aria-hidden="true"
  >
    <circle cx="24" cy="24" r="20" fill="none" stroke="#EFF8E2" strokeWidth="1" opacity="0.2" />
    <path d="M24 4 L26 24 L24 44 L22 24 Z" fill="#EFF8E2" opacity="0.15" />
    <path d="M4 24 L24 22 L44 24 L24 26 Z" fill="#EFF8E2" opacity="0.15" />
    <path d="M24 8 L26 24 L24 20 L22 24 Z" fill="#FFC857" />
    <circle cx="24" cy="24" r="3" fill="#0D1A12" />
  </svg>
);
```

**Step 5: Implement Sidebar component**

```typescript
// dashboard/src/components/organisms/Sidebar.tsx
import { FC, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { CompassRose } from '../atoms/CompassRose';
import {
  GitBranchIcon,
  UsersIcon,
  PackageIcon,
  HistoryIcon,
  TargetIcon,
  CloudIcon,
  RadioIcon,
  SendIcon,
} from '../../assets/icons';

interface NavItemProps {
  icon: ReactNode;
  label: string;
  active?: boolean;
  comingSoon?: boolean;
  href?: string;
}

const NavItem: FC<NavItemProps> = ({ icon, label, active = false, comingSoon = false, href = '#' }) => {
  const Component = comingSoon ? 'div' : Link;
  const props = comingSoon ? {} : { to: href };

  return (
    <Component
      {...props}
      className={`
        flex items-center gap-3 px-5 py-2.5
        border-l-3 transition-all duration-200
        font-heading text-sm font-semibold tracking-wider uppercase
        ${active
          ? 'border-l-accent-gold bg-accent-gold/10 text-text-primary'
          : 'border-l-transparent text-text-secondary hover:text-text-primary hover:bg-text-primary/5'
        }
        ${comingSoon ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}
      `.trim()}
      aria-current={active ? 'page' : undefined}
      aria-disabled={comingSoon}
    >
      <span className="flex items-center opacity-80">{icon}</span>
      <span className="flex-1">{label}</span>
      {comingSoon && (
        <span
          data-testid="coming-soon-badge"
          className="text-[9px] px-1.5 py-0.5 bg-text-secondary/20 text-text-secondary rounded"
        >
          SOON
        </span>
      )}
    </Component>
  );
};

interface NavSectionProps {
  label: string;
  children: ReactNode;
}

const NavSection: FC<NavSectionProps> = ({ label, children }) => (
  <div className="mb-6">
    <span className="block px-5 pb-2 font-heading text-xs font-semibold tracking-widest text-text-secondary">
      {label}
    </span>
    {children}
  </div>
);

export const Sidebar: FC = () => {
  return (
    <aside className="w-60 bg-bg-dark text-text-primary flex flex-col border-r border-text-primary/8">
      {/* Logo */}
      <div className="px-5 py-7 border-b border-text-primary/8 text-center">
        <h1 className="font-display text-4xl font-bold tracking-[0.12em] text-accent-gold [text-shadow:0_0_20px_rgba(255,200,87,0.3)]">
          AMELIA
        </h1>
        <p className="mt-1 font-heading text-xs tracking-[0.15em] text-text-secondary">
          AGENTIC ORCHESTRATOR
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-5" role="navigation" aria-label="Main navigation">
        <NavSection label="WORKFLOWS">
          <NavItem icon={<GitBranchIcon />} label="Active Jobs" active href="/jobs" />
          <NavItem icon={<UsersIcon />} label="Agents" comingSoon />
          <NavItem icon={<PackageIcon />} label="Outputs" comingSoon />
        </NavSection>

        <NavSection label="HISTORY">
          <NavItem icon={<HistoryIcon />} label="Past Runs" comingSoon />
          <NavItem icon={<TargetIcon />} label="Milestones" comingSoon />
          <NavItem icon={<CloudIcon />} label="Deployments" comingSoon />
        </NavSection>

        <NavSection label="MONITORING">
          <NavItem icon={<RadioIcon />} label="Logs" comingSoon />
          <NavItem icon={<SendIcon />} label="Notifications" comingSoon />
        </NavSection>
      </nav>

      {/* Footer */}
      <div className="px-5 py-5 border-t border-text-primary/8 flex flex-col items-center gap-3">
        <CompassRose />
        <span className="font-mono text-[9px] text-text-secondary tracking-wider">v0.0.1</span>
      </div>
    </aside>
  );
};
```

**Step 6: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/organisms/Sidebar.test.tsx`
Expected: PASS

**Step 7: Commit**

```bash
git add dashboard/src/components/organisms/Sidebar.tsx \
  dashboard/src/components/organisms/Sidebar.test.tsx \
  dashboard/src/components/atoms/CompassRose.tsx \
  dashboard/src/assets/icons.tsx
git commit -m "feat(dashboard): add Sidebar with navigation and compass rose

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Header Component with Workflow Info

**Files:**
- Create: `dashboard/src/components/organisms/Header.tsx`
- Create: `dashboard/src/components/organisms/Header.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/organisms/Header.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Header } from './Header';

describe('Header', () => {
  const mockWorkflow = {
    id: 'wf-001',
    issue_id: '#8',
    worktree_name: 'feature-benchmark',
    status: 'running' as const,
    eta_seconds: 165, // 02:45
  };

  it('renders workflow ID and worktree name', () => {
    render(<Header workflow={mockWorkflow} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
  });

  it('renders status badge', () => {
    render(<Header workflow={mockWorkflow} />);
    expect(screen.getByRole('status')).toHaveTextContent('RUNNING');
  });

  it('renders ETA in MM:SS format', () => {
    render(<Header workflow={mockWorkflow} />);
    expect(screen.getByText('02:45')).toBeInTheDocument();
  });

  it('renders placeholder ETA when no estimate available', () => {
    const workflowNoEta = { ...mockWorkflow, eta_seconds: null };
    render(<Header workflow={workflowNoEta} />);
    expect(screen.getByText('--:--')).toBeInTheDocument();
  });

  it('has proper semantic structure', () => {
    render(<Header workflow={mockWorkflow} />);
    const header = screen.getByRole('banner');
    expect(header).toBeInTheDocument();
  });

  it('renders pulsing status indicator for running workflows', () => {
    render(<Header workflow={mockWorkflow} />);
    const statusDot = screen.getByTestId('status-indicator');
    expect(statusDot).toHaveClass('animate-pulse');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/organisms/Header.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Implement Header component**

```typescript
// dashboard/src/components/organisms/Header.tsx
import { FC } from 'react';
import { StatusBadge, WorkflowStatus } from '../atoms/StatusBadge';

interface Workflow {
  id: string;
  issue_id: string;
  worktree_name: string;
  status: WorkflowStatus;
  eta_seconds: number | null;
}

interface HeaderProps {
  workflow: Workflow;
}

const formatETA = (seconds: number | null): string => {
  if (seconds === null || seconds <= 0) return '--:--';

  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
};

export const Header: FC<HeaderProps> = ({ workflow }) => {
  const isRunning = workflow.status === 'running';

  return (
    <header
      role="banner"
      className="flex items-center justify-between px-8 py-5 border-b border-text-primary/10 bg-bg-dark/50"
    >
      {/* Left: Workflow ID */}
      <div>
        <span className="block font-heading text-xs font-semibold tracking-[0.15em] text-text-secondary mb-1">
          WORKFLOW
        </span>
        <h2 className="font-display text-4xl font-bold tracking-[0.08em] text-text-primary">
          {workflow.issue_id}
        </h2>
      </div>

      {/* Center: ETA */}
      <div className="text-center">
        <span className="block font-heading text-xs font-semibold tracking-[0.15em] text-text-secondary mb-1">
          EST. COMPLETION
        </span>
        <span className="font-mono text-3xl font-semibold text-accent-gold [text-shadow:0_0_10px_rgba(255,200,87,0.4)]">
          {formatETA(workflow.eta_seconds)}
        </span>
      </div>

      {/* Right: Status */}
      <div className="flex items-center gap-2 px-4 py-2 bg-accent-gold/10 border border-accent-gold/30">
        <div
          data-testid="status-indicator"
          className={`
            w-2 h-2 rounded-full bg-accent-gold
            shadow-[0_0_8px_rgba(255,200,87,0.6)]
            ${isRunning ? 'animate-pulse' : ''}
          `.trim()}
        />
        <StatusBadge status={workflow.status} />
      </div>
    </header>
  );
};
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/organisms/Header.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/organisms/Header.tsx dashboard/src/components/organisms/Header.test.tsx
git commit -m "feat(dashboard): add Header with workflow status and ETA

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: JobQueue Component

**Files:**
- Create: `dashboard/src/components/organisms/JobQueue.tsx`
- Create: `dashboard/src/components/organisms/JobQueue.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/organisms/JobQueue.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JobQueue } from './JobQueue';

describe('JobQueue', () => {
  const mockWorkflows = [
    {
      id: 'wf-001',
      issue_id: '#8',
      worktree_name: 'feature-benchmark',
      status: 'running' as const,
      eta_seconds: 165,
    },
    {
      id: 'wf-002',
      issue_id: '#7',
      worktree_name: 'main',
      status: 'completed' as const,
      eta_seconds: 0,
    },
    {
      id: 'wf-003',
      issue_id: '#9',
      worktree_name: 'feature-clarifications',
      status: 'pending' as const,
      eta_seconds: 270,
    },
  ];

  it('renders all workflows', () => {
    render(<JobQueue workflows={mockWorkflows} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText('#8')).toBeInTheDocument();
    expect(screen.getByText('#7')).toBeInTheDocument();
    expect(screen.getByText('#9')).toBeInTheDocument();
  });

  it('highlights selected workflow with gold border', () => {
    render(<JobQueue workflows={mockWorkflows} selectedId="wf-001" onSelect={() => {}} />);
    const selectedItem = screen.getByText('#8').closest('div[role="button"]');
    expect(selectedItem).toHaveClass('border-accent-gold', 'border-2');
  });

  it('calls onSelect when workflow is clicked', () => {
    const onSelect = vi.fn();
    render(<JobQueue workflows={mockWorkflows} selectedId={null} onSelect={onSelect} />);

    const workflow = screen.getByText('#8').closest('div[role="button"]');
    fireEvent.click(workflow!);

    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('supports keyboard navigation', () => {
    const onSelect = vi.fn();
    render(<JobQueue workflows={mockWorkflows} selectedId={null} onSelect={onSelect} />);

    const workflow = screen.getByText('#8').closest('div[role="button"]');
    fireEvent.keyDown(workflow!, { key: 'Enter' });

    expect(onSelect).toHaveBeenCalledWith('wf-001');
  });

  it('renders status badges for each workflow', () => {
    render(<JobQueue workflows={mockWorkflows} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
    expect(screen.getByText('DONE')).toBeInTheDocument();
    expect(screen.getByText('QUEUED')).toBeInTheDocument();
  });

  it('has proper ARIA labels', () => {
    render(<JobQueue workflows={mockWorkflows} selectedId="wf-001" onSelect={() => {}} />);
    const items = screen.getAllByRole('button');
    expect(items[0]).toHaveAttribute('aria-pressed', 'true');
    expect(items[1]).toHaveAttribute('aria-pressed', 'false');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/organisms/JobQueue.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Implement JobQueue component**

```typescript
// dashboard/src/components/organisms/JobQueue.tsx
import { FC } from 'react';
import { StatusBadge, WorkflowStatus } from '../atoms/StatusBadge';

interface Workflow {
  id: string;
  issue_id: string;
  worktree_name: string;
  status: WorkflowStatus;
  eta_seconds: number | null;
}

interface JobQueueProps {
  workflows: Workflow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const formatETA = (seconds: number | null): string => {
  if (seconds === null || seconds <= 0) return '--:--';
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
};

interface QueueItemProps {
  workflow: Workflow;
  isSelected: boolean;
  onClick: () => void;
}

const QueueItem: FC<QueueItemProps> = ({ workflow, isSelected, onClick }) => {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      className={`
        p-3 cursor-pointer transition-all duration-200
        bg-bg-main/60 border
        ${isSelected
          ? 'border-accent-gold border-2 bg-accent-gold/8 shadow-[0_0_15px_rgba(255,200,87,0.1)]'
          : 'border-text-primary/8 hover:border-text-primary/20'
        }
      `.trim()}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-mono text-sm font-semibold text-accent-blue">
          {workflow.issue_id}
        </span>
        <StatusBadge status={workflow.status} />
      </div>
      <p className="font-body text-base text-text-primary mb-1">
        {workflow.worktree_name}
      </p>
      <span className="font-heading text-xs tracking-wider text-text-secondary">
        Est: {formatETA(workflow.eta_seconds)}
      </span>
    </div>
  );
};

export const JobQueue: FC<JobQueueProps> = ({ workflows, selectedId, onSelect }) => {
  return (
    <div className="bg-bg-dark/60 border border-text-primary/10 p-5 flex flex-col">
      <h3 className="font-heading text-sm font-semibold tracking-[0.12em] text-text-secondary mb-4 pb-3 border-b border-text-primary/10">
        JOB QUEUE
      </h3>
      <div className="flex flex-col gap-3 flex-1 overflow-auto">
        {workflows.map((workflow) => (
          <QueueItem
            key={workflow.id}
            workflow={workflow}
            isSelected={workflow.id === selectedId}
            onClick={() => onSelect(workflow.id)}
          />
        ))}
      </div>
    </div>
  );
};
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/organisms/JobQueue.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/organisms/JobQueue.tsx dashboard/src/components/organisms/JobQueue.test.tsx
git commit -m "feat(dashboard): add JobQueue with keyboard navigation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: ActivityLog Component with Scanlines

**Files:**
- Create: `dashboard/src/components/organisms/ActivityLog.tsx`
- Create: `dashboard/src/components/organisms/ActivityLog.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/organisms/ActivityLog.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityLog } from './ActivityLog';

describe('ActivityLog', () => {
  const mockEvents = [
    {
      id: 'evt-001',
      workflow_id: 'wf-001',
      timestamp: '2025-12-01T14:32:07Z',
      agent: 'ARCHITECT',
      message: 'Issue #8 parsed. Creating task DAG for benchmark framework.',
    },
    {
      id: 'evt-002',
      workflow_id: 'wf-001',
      timestamp: '2025-12-01T14:32:45Z',
      agent: 'ARCHITECT',
      message: 'Plan approved. Routing to DEVELOPER.',
    },
    {
      id: 'evt-003',
      workflow_id: 'wf-001',
      timestamp: '2025-12-01T14:33:12Z',
      agent: 'DEVELOPER',
      message: 'Task received. Scaffolding tests/benchmark/ structure.',
    },
  ];

  it('renders all events in chronological order', () => {
    render(<ActivityLog events={mockEvents} />);
    expect(screen.getByText(/Issue #8 parsed/)).toBeInTheDocument();
    expect(screen.getByText(/Plan approved/)).toBeInTheDocument();
    expect(screen.getByText(/Task received/)).toBeInTheDocument();
  });

  it('displays timestamps in HH:MM:SSZ format', () => {
    render(<ActivityLog events={mockEvents} />);
    expect(screen.getByText('14:32:07Z')).toBeInTheDocument();
    expect(screen.getByText('14:32:45Z')).toBeInTheDocument();
  });

  it('displays agent names in brackets', () => {
    render(<ActivityLog events={mockEvents} />);
    expect(screen.getByText('[ARCHITECT]')).toBeInTheDocument();
    expect(screen.getByText('[DEVELOPER]')).toBeInTheDocument();
  });

  it('has role="log" for screen readers', () => {
    render(<ActivityLog events={mockEvents} />);
    const log = screen.getByRole('log');
    expect(log).toHaveAttribute('aria-live', 'polite');
    expect(log).toHaveAttribute('aria-label', 'Workflow activity log');
  });

  it('renders blinking cursor at end', () => {
    render(<ActivityLog events={mockEvents} />);
    expect(screen.getByTestId('log-cursor')).toHaveClass('animate-blink');
  });

  it('auto-scrolls to bottom when new events arrive', () => {
    const { rerender } = render(<ActivityLog events={mockEvents} />);

    const newEvents = [
      ...mockEvents,
      {
        id: 'evt-004',
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:34:00Z',
        agent: 'REVIEWER',
        message: 'Code review commenced.',
      },
    ];

    rerender(<ActivityLog events={newEvents} />);
    expect(screen.getByText(/Code review commenced/)).toBeInTheDocument();
  });

  it('respects prefers-reduced-motion for scanlines', () => {
    const { container } = render(<ActivityLog events={mockEvents} />);
    const scanlines = container.querySelector('.scanlines');
    expect(scanlines).toHaveClass('motion-reduce:hidden');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/organisms/ActivityLog.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Implement ActivityLog component**

```typescript
// dashboard/src/components/organisms/ActivityLog.tsx
import { FC, useEffect, useRef } from 'react';

interface WorkflowEvent {
  id: string;
  workflow_id: string;
  timestamp: string;
  agent: string;
  message: string;
}

interface ActivityLogProps {
  events: WorkflowEvent[];
}

const formatTimestamp = (isoString: string): string => {
  const date = new Date(isoString);
  const hours = String(date.getUTCHours()).padStart(2, '0');
  const minutes = String(date.getUTCMinutes()).padStart(2, '0');
  const seconds = String(date.getUTCSeconds()).padStart(2, '0');
  return `${hours}:${minutes}:${seconds}Z`;
};

export const ActivityLog: FC<ActivityLogProps> = ({ events }) => {
  const logEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  return (
    <div className="bg-bg-dark/60 border border-text-primary/10 p-5 flex flex-col">
      <h3 className="font-heading text-sm font-semibold tracking-[0.12em] text-text-secondary mb-4 pb-3 border-b border-text-primary/10">
        ACTIVITY LOG
      </h3>

      <div
        role="log"
        aria-live="polite"
        aria-label="Workflow activity log"
        className="relative font-mono text-sm leading-relaxed flex-1 overflow-auto"
      >
        {/* Scanlines effect */}
        <div
          className="scanlines absolute inset-0 pointer-events-none motion-reduce:hidden"
          style={{
            background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(239, 248, 226, 0.015) 2px, rgba(239, 248, 226, 0.015) 4px)',
          }}
          aria-hidden="true"
        />

        {/* Log entries */}
        {events.map((event) => (
          <div
            key={event.id}
            className="grid grid-cols-[90px_90px_1fr] gap-3 py-1 border-b border-text-primary/[0.04]"
          >
            <span className="text-text-secondary">{formatTimestamp(event.timestamp)}</span>
            <span className="text-accent-blue font-semibold">[{event.agent}]</span>
            <span className="text-text-primary/80">{event.message}</span>
          </div>
        ))}

        {/* Blinking cursor */}
        <div
          data-testid="log-cursor"
          className="text-accent-gold [text-shadow:0_0_8px_rgba(255,200,87,0.6)] animate-blink mt-2"
          aria-hidden="true"
        >
          ▋
        </div>

        {/* Scroll anchor */}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};
```

**Step 4: Add blink animation to Tailwind config**

```typescript
// dashboard/tailwind.config.js
export default {
  // ... existing config
  theme: {
    extend: {
      animation: {
        blink: 'blink 1s step-end infinite',
        pulse: 'pulse 2s ease-in-out infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        pulse: {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 8px rgba(255, 200, 87, 0.6)' },
          '50%': { opacity: '0.6', boxShadow: '0 0 12px rgba(255, 200, 87, 0.8)' },
        },
      },
    },
  },
};
```

**Step 5: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/organisms/ActivityLog.test.tsx`
Expected: PASS

**Step 6: Commit**

```bash
git add dashboard/src/components/organisms/ActivityLog.tsx \
  dashboard/src/components/organisms/ActivityLog.test.tsx \
  dashboard/tailwind.config.js
git commit -m "feat(dashboard): add ActivityLog with scanlines and auto-scroll

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: BeaconNode Custom React Flow Node

**Files:**
- Create: `dashboard/src/components/flow/BeaconNode.tsx`
- Create: `dashboard/src/components/flow/BeaconNode.test.tsx`
- Create: `dashboard/src/components/flow/MapPinIcon.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/flow/BeaconNode.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BeaconNode } from './BeaconNode';

describe('BeaconNode', () => {
  const baseProps = {
    id: 'architect',
    data: {
      label: 'Architect',
      subtitle: 'Planning',
      status: 'completed' as const,
      tokens: '12.4k',
    },
  };

  it('renders stage label and subtitle', () => {
    render(<BeaconNode {...baseProps} />);
    expect(screen.getByText('Architect')).toBeInTheDocument();
    expect(screen.getByText('Planning')).toBeInTheDocument();
  });

  it('renders token count when provided', () => {
    render(<BeaconNode {...baseProps} />);
    expect(screen.getByText('12.4k tokens')).toBeInTheDocument();
  });

  it('renders map pin icon with completed state styling', () => {
    render(<BeaconNode {...baseProps} />);
    const pin = screen.getByTestId('map-pin-icon');
    expect(pin).toHaveAttribute('data-status', 'completed');
  });

  it('applies beacon pulse animation to active state', () => {
    const activeProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'active' as const },
    };
    render(<BeaconNode {...activeProps} />);
    const pin = screen.getByTestId('map-pin-icon');
    expect(pin).toHaveClass('animate-beacon-glow');
  });

  it('applies blocked state styling', () => {
    const blockedProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'blocked' as const },
    };
    render(<BeaconNode {...blockedProps} />);
    const pin = screen.getByTestId('map-pin-icon');
    expect(pin).toHaveAttribute('data-status', 'blocked');
  });

  it('does not render token count when not provided', () => {
    const noTokensProps = {
      ...baseProps,
      data: { ...baseProps.data, tokens: null },
    };
    render(<BeaconNode {...noTokensProps} />);
    expect(screen.queryByText(/tokens/)).not.toBeInTheDocument();
  });

  it('has proper ARIA role and label', () => {
    render(<BeaconNode {...baseProps} />);
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('aria-label', 'Workflow stage: Architect - Planning (completed)');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/flow/BeaconNode.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Create MapPinIcon component**

```typescript
// dashboard/src/components/flow/MapPinIcon.tsx
import { FC } from 'react';

type NodeStatus = 'completed' | 'active' | 'pending' | 'blocked';

interface MapPinIconProps {
  status: NodeStatus;
  size?: number;
  className?: string;
}

const statusColors = {
  completed: {
    fill: '#5B8A72',
    stroke: '#3D5E4B',
  },
  active: {
    fill: '#FFC857',
    stroke: '#D4A53D',
  },
  pending: {
    fill: '#4A5C54',
    stroke: '#2D3B35',
  },
  blocked: {
    fill: '#A33D2E',
    stroke: '#6B1F14',
  },
};

export const MapPinIcon: FC<MapPinIconProps> = ({ status, size = 32, className = '' }) => {
  const colors = statusColors[status];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={colors.fill}
      stroke={colors.stroke}
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      data-testid="map-pin-icon"
      data-status={status}
      className={`${status === 'active' ? 'animate-beacon-glow' : ''} ${className}`.trim()}
      aria-hidden="true"
    >
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" fill={colors.stroke} />
    </svg>
  );
};
```

**Step 4: Implement BeaconNode component**

```typescript
// dashboard/src/components/flow/BeaconNode.tsx
import { FC, memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { MapPinIcon } from './MapPinIcon';

type NodeStatus = 'completed' | 'active' | 'pending' | 'blocked';

interface BeaconNodeData {
  label: string;
  subtitle: string;
  status: NodeStatus;
  tokens: string | null;
}

export type BeaconNodeProps = NodeProps<BeaconNodeData>;

const BeaconNodeComponent: FC<BeaconNodeProps> = ({ data }) => {
  const tokenColor = data.status === 'active' ? 'text-accent-gold' : 'text-status-completed';

  return (
    <div
      role="img"
      aria-label={`Workflow stage: ${data.label} - ${data.subtitle} (${data.status})`}
      className="flex flex-col items-center gap-2 min-w-[100px] transition-transform duration-200 hover:-translate-y-0.5 hover:drop-shadow-[0_4px_12px_rgba(255,200,87,0.15)]"
    >
      {/* Input handle (left) */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-2 h-2 !bg-text-primary/20 border-0"
      />

      {/* Map Pin Icon */}
      <MapPinIcon status={data.status} size={32} />

      {/* Label */}
      <span className="font-heading text-lg font-semibold tracking-wider text-text-primary text-center mt-3">
        {data.label}
      </span>

      {/* Subtitle */}
      <span className="font-body text-sm text-text-secondary text-center">
        {data.subtitle}
      </span>

      {/* Token count (if provided) */}
      {data.tokens && (
        <span className={`font-mono text-xs text-center ${tokenColor}`}>
          {data.tokens} tokens
        </span>
      )}

      {/* Output handle (right) */}
      <Handle
        type="source"
        position={Position.Right}
        className="w-2 h-2 !bg-text-primary/20 border-0"
      />
    </div>
  );
};

export const BeaconNode = memo(BeaconNodeComponent);
```

**Step 5: Add beacon-glow animation to Tailwind config**

```typescript
// dashboard/tailwind.config.js
export default {
  // ... existing config
  theme: {
    extend: {
      animation: {
        blink: 'blink 1s step-end infinite',
        pulse: 'pulse 2s ease-in-out infinite',
        'beacon-glow': 'beaconGlow 2s ease-in-out infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        pulse: {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 8px rgba(255, 200, 87, 0.6)' },
          '50%': { opacity: '0.6', boxShadow: '0 0 12px rgba(255, 200, 87, 0.8)' },
        },
        beaconGlow: {
          '0%, 100%': {
            filter: 'drop-shadow(0 0 4px rgba(255, 200, 87, 0.6)) drop-shadow(0 0 8px rgba(255, 200, 87, 0.4))',
          },
          '50%': {
            filter: 'drop-shadow(0 0 8px rgba(255, 200, 87, 0.9)) drop-shadow(0 0 16px rgba(255, 200, 87, 0.6)) drop-shadow(0 0 24px rgba(255, 200, 87, 0.3))',
          },
        },
      },
    },
  },
};
```

**Step 6: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/flow/BeaconNode.test.tsx`
Expected: PASS

**Step 7: Commit**

```bash
git add dashboard/src/components/flow/BeaconNode.tsx \
  dashboard/src/components/flow/BeaconNode.test.tsx \
  dashboard/src/components/flow/MapPinIcon.tsx \
  dashboard/tailwind.config.js
git commit -m "feat(dashboard): add BeaconNode with animated map pin

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: FlightEdge Custom React Flow Edge

**Files:**
- Create: `dashboard/src/components/flow/FlightEdge.tsx`
- Create: `dashboard/src/components/flow/FlightEdge.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/flow/FlightEdge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FlightEdge } from './FlightEdge';

describe('FlightEdge', () => {
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
    data: {
      label: '0:24',
      status: 'completed' as const,
    },
  };

  it('renders edge path', () => {
    const { container } = render(<FlightEdge {...baseProps} />);
    const path = container.querySelector('path');
    expect(path).toBeInTheDocument();
  });

  it('renders time label', () => {
    render(<FlightEdge {...baseProps} />);
    expect(screen.getByText('0:24')).toBeInTheDocument();
  });

  it('applies completed state styling (solid green line)', () => {
    const { container } = render(<FlightEdge {...baseProps} />);
    const path = container.querySelector('path[data-status="completed"]');
    expect(path).toHaveAttribute('stroke', '#5B8A72');
  });

  it('applies active state styling (dashed gold line with glow)', () => {
    const activeProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'active' as const },
    };
    const { container } = render(<FlightEdge {...activeProps} />);
    const path = container.querySelector('path[data-status="active"]');
    expect(path).toHaveAttribute('stroke', '#FFC857');
    expect(path).toHaveAttribute('stroke-dasharray', '5 5');
  });

  it('applies pending state styling (dashed low opacity)', () => {
    const pendingProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'pending' as const },
    };
    const { container } = render(<FlightEdge {...pendingProps} />);
    const path = container.querySelector('path[data-status="pending"]');
    expect(path).toHaveClass('opacity-30');
  });

  it('positions label at midpoint of edge', () => {
    render(<FlightEdge {...baseProps} />);
    const label = screen.getByText('0:24');
    expect(label).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/flow/FlightEdge.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Implement FlightEdge component**

```typescript
// dashboard/src/components/flow/FlightEdge.tsx
import { FC, memo } from 'react';
import { EdgeProps, getStraightPath } from 'reactflow';

type EdgeStatus = 'completed' | 'active' | 'pending';

interface FlightEdgeData {
  label: string;
  status: EdgeStatus;
}

export type FlightEdgeProps = EdgeProps<FlightEdgeData>;

const statusConfig = {
  completed: {
    stroke: '#5B8A72',
    strokeWidth: 2,
    opacity: 1,
    dashArray: undefined,
    glow: false,
  },
  active: {
    stroke: '#FFC857',
    strokeWidth: 2,
    opacity: 1,
    dashArray: '5 5',
    glow: true,
  },
  pending: {
    stroke: 'rgba(239, 248, 226, 0.2)',
    strokeWidth: 2,
    opacity: 0.3,
    dashArray: '5 5',
    glow: false,
  },
};

const FlightEdgeComponent: FC<FlightEdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}) => {
  const [edgePath, labelX, labelY] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });

  const config = statusConfig[data?.status || 'pending'];

  return (
    <g>
      {/* Edge path */}
      <path
        id={id}
        d={edgePath}
        stroke={config.stroke}
        strokeWidth={config.strokeWidth}
        strokeDasharray={config.dashArray}
        fill="none"
        data-status={data?.status}
        className={`
          ${config.opacity < 1 ? 'opacity-30' : ''}
          ${config.glow ? 'drop-shadow-[0_0_8px_rgba(255,200,87,0.4)]' : ''}
        `.trim()}
      />

      {/* Time label */}
      <foreignObject
        x={labelX - 30}
        y={labelY - 15}
        width={60}
        height={30}
        className="overflow-visible"
      >
        <div className="flex items-center justify-center h-full">
          <span className="px-2 py-0.5 font-mono text-xs text-text-secondary bg-bg-dark/80 border border-text-primary/15">
            {data?.label}
          </span>
        </div>
      </foreignObject>

      {/* Arrow indicator */}
      <foreignObject
        x={labelX - 6}
        y={labelY + 18}
        width={12}
        height={12}
        className="overflow-visible"
      >
        <div className="flex items-center justify-center text-[10px] text-text-primary/40">
          ▸
        </div>
      </foreignObject>
    </g>
  );
};

export const FlightEdge = memo(FlightEdgeComponent);
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/flow/FlightEdge.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/flow/FlightEdge.tsx dashboard/src/components/flow/FlightEdge.test.tsx
git commit -m "feat(dashboard): add FlightEdge with time labels and animations

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: WorkflowCanvas with React Flow Integration

**Files:**
- Create: `dashboard/src/components/organisms/WorkflowCanvas.tsx`
- Create: `dashboard/src/components/organisms/WorkflowCanvas.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/organisms/WorkflowCanvas.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowCanvas } from './WorkflowCanvas';

describe('WorkflowCanvas', () => {
  const mockPipeline = {
    nodes: [
      { id: 'issue', label: 'Issue', subtitle: 'Origin', status: 'completed' as const, tokens: null },
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

  it('renders navigation grid pattern background', () => {
    const { container } = render(<WorkflowCanvas pipeline={mockPipeline} />);
    const gridPattern = container.querySelector('[data-testid="grid-pattern"]');
    expect(gridPattern).toBeInTheDocument();
  });

  it('has proper ARIA role for pipeline visualization', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    const canvas = screen.getByRole('img');
    expect(canvas).toHaveAttribute('aria-label');
    expect(canvas.getAttribute('aria-label')).toContain('pipeline');
  });

  it('renders all nodes from pipeline', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    expect(screen.getByText('Issue')).toBeInTheDocument();
    expect(screen.getByText('Architect')).toBeInTheDocument();
    expect(screen.getByText('Developer')).toBeInTheDocument();
  });

  it('renders edges with time labels', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    expect(screen.getByText('0:08')).toBeInTheDocument();
    expect(screen.getByText('0:24')).toBeInTheDocument();
  });

  it('disables user interaction (view-only)', () => {
    const { container } = render(<WorkflowCanvas pipeline={mockPipeline} />);
    const reactFlow = container.querySelector('.react-flow');
    expect(reactFlow).toHaveAttribute('data-interactive', 'false');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/organisms/WorkflowCanvas.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Implement WorkflowCanvas component**

```typescript
// dashboard/src/components/organisms/WorkflowCanvas.tsx
import { FC, useMemo } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Background,
  BackgroundVariant,
  ReactFlowProvider,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { BeaconNode } from '../flow/BeaconNode';
import { FlightEdge } from '../flow/FlightEdge';

type NodeStatus = 'completed' | 'active' | 'pending' | 'blocked';
type EdgeStatus = 'completed' | 'active' | 'pending';

interface PipelineNode {
  id: string;
  label: string;
  subtitle: string;
  status: NodeStatus;
  tokens: string | null;
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
}

const nodeTypes = {
  beacon: BeaconNode,
};

const edgeTypes = {
  flight: FlightEdge,
};

const WorkflowCanvasComponent: FC<WorkflowCanvasProps> = ({ pipeline }) => {
  // Convert pipeline data to React Flow format
  const nodes: Node[] = useMemo(
    () =>
      pipeline.nodes.map((node, index) => ({
        id: node.id,
        type: 'beacon',
        position: { x: index * 200, y: 50 },
        data: {
          label: node.label,
          subtitle: node.subtitle,
          status: node.status,
          tokens: node.tokens,
        },
      })),
    [pipeline.nodes]
  );

  const edges: Edge[] = useMemo(
    () =>
      pipeline.edges.map((edge, index) => ({
        id: `e-${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        type: 'flight',
        data: {
          label: edge.label,
          status: edge.status,
        },
      })),
    [pipeline.edges]
  );

  const currentStage = pipeline.nodes.find((n) => n.status === 'active')?.label || 'Unknown';

  return (
    <div
      role="img"
      aria-label={`Workflow pipeline with ${pipeline.nodes.length} stages. Current stage: ${currentStage}`}
      className="relative h-64 bg-gradient-to-b from-bg-main/40 to-bg-dark/40"
    >
      {/* Grid pattern background */}
      <div
        data-testid="grid-pattern"
        className="absolute inset-0 opacity-50 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(239, 248, 226, 0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(239, 248, 226, 0.05) 1px, transparent 1px)
          `,
          backgroundSize: '20px 20px',
        }}
        aria-hidden="true"
      />

      {/* React Flow */}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        panOnDrag={false}
        data-interactive="false"
        className="workflow-canvas"
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(239, 248, 226, 0.1)" />
      </ReactFlow>
    </div>
  );
};

export const WorkflowCanvas: FC<WorkflowCanvasProps> = (props) => (
  <ReactFlowProvider>
    <WorkflowCanvasComponent {...props} />
  </ReactFlowProvider>
);
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/organisms/WorkflowCanvas.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/organisms/WorkflowCanvas.tsx dashboard/src/components/organisms/WorkflowCanvas.test.tsx
git commit -m "feat(dashboard): add WorkflowCanvas with React Flow integration

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: ApprovalButtons Component

**Files:**
- Create: `dashboard/src/components/molecules/ApprovalButtons.tsx`
- Create: `dashboard/src/components/molecules/ApprovalButtons.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/molecules/ApprovalButtons.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApprovalButtons } from './ApprovalButtons';

describe('ApprovalButtons', () => {
  it('renders Approve and Reject buttons', () => {
    render(<ApprovalButtons workflowId="wf-001" onApprove={() => {}} onReject={() => {}} isPending={false} />);
    expect(screen.getByText('Approve')).toBeInTheDocument();
    expect(screen.getByText('Reject')).toBeInTheDocument();
  });

  it('calls onApprove when Approve button is clicked', () => {
    const onApprove = vi.fn();
    render(<ApprovalButtons workflowId="wf-001" onApprove={onApprove} onReject={() => {}} isPending={false} />);

    fireEvent.click(screen.getByText('Approve'));
    expect(onApprove).toHaveBeenCalledWith('wf-001');
  });

  it('calls onReject when Reject button is clicked', () => {
    const onReject = vi.fn();
    render(<ApprovalButtons workflowId="wf-001" onApprove={() => {}} onReject={onReject} isPending={false} />);

    fireEvent.click(screen.getByText('Reject'));
    expect(onReject).toHaveBeenCalledWith('wf-001');
  });

  it('disables buttons when isPending is true', () => {
    render(<ApprovalButtons workflowId="wf-001" onApprove={() => {}} onReject={() => {}} isPending={true} />);

    const approveBtn = screen.getByText('Approve');
    const rejectBtn = screen.getByText('Reject');

    expect(approveBtn).toBeDisabled();
    expect(rejectBtn).toBeDisabled();
  });

  it('shows loading spinner when isPending is true', () => {
    render(<ApprovalButtons workflowId="wf-001" onApprove={() => {}} onReject={() => {}} isPending={true} />);
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
  });

  it('has proper ARIA labels for accessibility', () => {
    render(<ApprovalButtons workflowId="wf-001" onApprove={() => {}} onReject={() => {}} isPending={false} />);

    const approveBtn = screen.getByLabelText('Approve workflow plan');
    const rejectBtn = screen.getByLabelText('Reject workflow plan');

    expect(approveBtn).toBeInTheDocument();
    expect(rejectBtn).toBeInTheDocument();
  });

  it('supports keyboard interaction (Enter key)', () => {
    const onApprove = vi.fn();
    render(<ApprovalButtons workflowId="wf-001" onApprove={onApprove} onReject={() => {}} isPending={false} />);

    const approveBtn = screen.getByText('Approve');
    fireEvent.keyDown(approveBtn, { key: 'Enter' });

    expect(onApprove).toHaveBeenCalledWith('wf-001');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/components/molecules/ApprovalButtons.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Implement ApprovalButtons component**

```typescript
// dashboard/src/components/molecules/ApprovalButtons.tsx
import { FC } from 'react';

interface ApprovalButtonsProps {
  workflowId: string;
  onApprove: (workflowId: string) => void;
  onReject: (workflowId: string) => void;
  isPending: boolean;
}

const Spinner: FC = () => (
  <svg
    data-testid="loading-spinner"
    className="animate-spin h-4 w-4"
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
);

export const ApprovalButtons: FC<ApprovalButtonsProps> = ({
  workflowId,
  onApprove,
  onReject,
  isPending,
}) => {
  const handleApprove = () => {
    if (!isPending) {
      onApprove(workflowId);
    }
  };

  const handleReject = () => {
    if (!isPending) {
      onReject(workflowId);
    }
  };

  const handleKeyDown = (handler: () => void) => (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isPending) {
      handler();
    }
  };

  return (
    <div className="flex gap-3" role="group" aria-label="Plan approval actions">
      <button
        onClick={handleApprove}
        onKeyDown={handleKeyDown(handleApprove)}
        disabled={isPending}
        aria-label="Approve workflow plan"
        className={`
          flex items-center justify-center gap-2
          px-6 py-3
          font-heading text-sm font-semibold tracking-wider uppercase
          bg-status-completed text-bg-dark
          border-2 border-status-completed
          transition-all duration-200
          ${isPending
            ? 'opacity-50 cursor-not-allowed'
            : 'hover:bg-status-completed/90 hover:shadow-lg hover:shadow-status-completed/20 active:scale-95'
          }
        `.trim()}
      >
        {isPending ? <Spinner /> : null}
        Approve
      </button>

      <button
        onClick={handleReject}
        onKeyDown={handleKeyDown(handleReject)}
        disabled={isPending}
        aria-label="Reject workflow plan"
        className={`
          flex items-center justify-center gap-2
          px-6 py-3
          font-heading text-sm font-semibold tracking-wider uppercase
          bg-transparent text-status-failed
          border-2 border-status-failed
          transition-all duration-200
          ${isPending
            ? 'opacity-50 cursor-not-allowed'
            : 'hover:bg-status-failed hover:text-text-primary hover:shadow-lg hover:shadow-status-failed/20 active:scale-95'
          }
        `.trim()}
      >
        {isPending ? <Spinner /> : null}
        Reject
      </button>
    </div>
  );
};
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && npm test src/components/molecules/ApprovalButtons.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/molecules/ApprovalButtons.tsx dashboard/src/components/molecules/ApprovalButtons.test.tsx
git commit -m "feat(dashboard): add ApprovalButtons with loading states

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: ActiveJobs Page Assembly

**Files:**
- Create: `dashboard/src/pages/ActiveJobs.tsx`
- Create: `dashboard/src/pages/ActiveJobs.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/pages/ActiveJobs.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ActiveJobs } from './ActiveJobs';
import { useWorkflowStore } from '../store/workflowStore';

// Mock the store
vi.mock('../store/workflowStore', () => ({
  useWorkflowStore: vi.fn(),
}));

describe('ActiveJobs', () => {
  const mockWorkflows = {
    'wf-001': {
      id: 'wf-001',
      issue_id: '#8',
      worktree_name: 'feature-benchmark',
      status: 'blocked' as const,
      eta_seconds: 165,
      pipeline: {
        nodes: [
          { id: 'issue', label: 'Issue', subtitle: 'Origin', status: 'completed' as const, tokens: null },
          { id: 'architect', label: 'Architect', subtitle: 'Planning', status: 'completed' as const, tokens: '12.4k' },
        ],
        edges: [
          { from: 'issue', to: 'architect', label: '0:08', status: 'completed' as const },
        ],
      },
    },
    'wf-002': {
      id: 'wf-002',
      issue_id: '#7',
      worktree_name: 'main',
      status: 'completed' as const,
      eta_seconds: 0,
      pipeline: {
        nodes: [],
        edges: [],
      },
    },
  };

  const mockEventsByWorkflow = {
    'wf-001': [
      {
        id: 'evt-001',
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:32:07Z',
        agent: 'ARCHITECT',
        message: 'Plan approved.',
      },
    ],
  };

  beforeEach(() => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      workflows: mockWorkflows,
      selectedWorkflowId: 'wf-001',
      eventsByWorkflow: mockEventsByWorkflow,
      selectWorkflow: vi.fn(),
      isConnected: true,
      error: null,
    } as any);
  });

  it('renders all major components', () => {
    render(<ActiveJobs />);

    // Check for header
    expect(screen.getByText('#8')).toBeInTheDocument();

    // Check for job queue
    expect(screen.getByText('JOB QUEUE')).toBeInTheDocument();

    // Check for workflow canvas
    expect(screen.getByRole('img', { name: /pipeline/i })).toBeInTheDocument();

    // Check for activity log
    expect(screen.getByText('ACTIVITY LOG')).toBeInTheDocument();
  });

  it('renders approval buttons when workflow is blocked', () => {
    render(<ActiveJobs />);
    expect(screen.getByText('Approve')).toBeInTheDocument();
    expect(screen.getByText('Reject')).toBeInTheDocument();
  });

  it('does not render approval buttons when workflow is not blocked', () => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      workflows: mockWorkflows,
      selectedWorkflowId: 'wf-002',
      eventsByWorkflow: {},
      selectWorkflow: vi.fn(),
      isConnected: true,
      error: null,
    } as any);

    render(<ActiveJobs />);
    expect(screen.queryByText('Approve')).not.toBeInTheDocument();
  });

  it('shows error message when connection is lost', () => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      workflows: {},
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      selectWorkflow: vi.fn(),
      isConnected: false,
      error: 'Connection lost',
    } as any);

    render(<ActiveJobs />);
    expect(screen.getByText(/connection lost/i)).toBeInTheDocument();
  });

  it('shows placeholder when no workflows exist', () => {
    vi.mocked(useWorkflowStore).mockReturnValue({
      workflows: {},
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      selectWorkflow: vi.fn(),
      isConnected: true,
      error: null,
    } as any);

    render(<ActiveJobs />);
    expect(screen.getByText(/no active workflows/i)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test src/pages/ActiveJobs.test.tsx`
Expected: FAIL - Component does not exist

**Step 3: Implement ActiveJobs page**

```typescript
// dashboard/src/pages/ActiveJobs.tsx
import { FC } from 'react';
import { useWorkflowStore } from '../store/workflowStore';
import { useWorkflowActions } from '../hooks/useWorkflowActions';
import { Header } from '../components/organisms/Header';
import { JobQueue } from '../components/organisms/JobQueue';
import { WorkflowCanvas } from '../components/organisms/WorkflowCanvas';
import { ActivityLog } from '../components/organisms/ActivityLog';
import { ApprovalButtons } from '../components/molecules/ApprovalButtons';

export const ActiveJobs: FC = () => {
  const {
    workflows,
    selectedWorkflowId,
    eventsByWorkflow,
    selectWorkflow,
    isConnected,
    error,
  } = useWorkflowStore();

  const { approveWorkflow, rejectWorkflow, isActionPending } = useWorkflowActions();

  const workflowList = Object.values(workflows);
  const selectedWorkflow = selectedWorkflowId ? workflows[selectedWorkflowId] : null;
  const selectedEvents = selectedWorkflowId ? eventsByWorkflow[selectedWorkflowId] || [] : [];

  // Error state
  if (!isConnected && error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-status-failed text-xl mb-2">Connection Lost</div>
          <div className="text-text-secondary text-sm">{error}</div>
        </div>
      </div>
    );
  }

  // Empty state
  if (workflowList.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-text-primary text-xl mb-2">No Active Workflows</div>
          <div className="text-text-secondary text-sm">
            Start a workflow from the CLI: <code className="font-mono">amelia start ISSUE-123</code>
          </div>
        </div>
      </div>
    );
  }

  const isBlocked = selectedWorkflow?.status === 'blocked';
  const isPending = selectedWorkflowId ? isActionPending(selectedWorkflowId) : false;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      {selectedWorkflow && <Header workflow={selectedWorkflow} />}

      {/* Workflow Visualization */}
      {selectedWorkflow && selectedWorkflow.pipeline && (
        <div className="px-12 py-6">
          <WorkflowCanvas pipeline={selectedWorkflow.pipeline} />
        </div>
      )}

      {/* Approval Buttons (when blocked) */}
      {isBlocked && selectedWorkflowId && (
        <div className="px-12 py-4 flex justify-center">
          <ApprovalButtons
            workflowId={selectedWorkflowId}
            onApprove={approveWorkflow}
            onReject={rejectWorkflow}
            isPending={isPending}
          />
        </div>
      )}

      {/* Bottom Section: Queue + Log */}
      <div className="grid grid-cols-[320px_1fr] gap-6 px-8 pb-6 flex-1 min-h-0">
        <JobQueue
          workflows={workflowList}
          selectedId={selectedWorkflowId}
          onSelect={selectWorkflow}
        />
        <ActivityLog events={selectedEvents} />
      </div>
    </div>
  );
};
```

**Step 4: Create useWorkflowActions hook (stub for testing)**

```typescript
// dashboard/src/hooks/useWorkflowActions.ts
import { useWorkflowStore } from '../store/workflowStore';

export interface UseWorkflowActionsResult {
  approveWorkflow: (workflowId: string) => Promise<void>;
  rejectWorkflow: (workflowId: string) => Promise<void>;
  cancelWorkflow: (workflowId: string) => Promise<void>;
  isActionPending: (workflowId: string) => boolean;
}

export function useWorkflowActions(): UseWorkflowActionsResult {
  const { pendingActions } = useWorkflowStore();

  const approveWorkflow = async (workflowId: string) => {
    // Implementation will be added in Plan 9 (state management)
    console.log('Approve workflow:', workflowId);
  };

  const rejectWorkflow = async (workflowId: string) => {
    console.log('Reject workflow:', workflowId);
  };

  const cancelWorkflow = async (workflowId: string) => {
    console.log('Cancel workflow:', workflowId);
  };

  const isActionPending = (workflowId: string) => {
    return pendingActions.some(id => id.endsWith(workflowId));
  };

  return {
    approveWorkflow,
    rejectWorkflow,
    cancelWorkflow,
    isActionPending,
  };
}
```

**Step 5: Run test to verify it passes**

Run: `cd dashboard && npm test src/pages/ActiveJobs.test.tsx`
Expected: PASS

**Step 6: Commit**

```bash
git add dashboard/src/pages/ActiveJobs.tsx \
  dashboard/src/pages/ActiveJobs.test.tsx \
  dashboard/src/hooks/useWorkflowActions.ts
git commit -m "feat(dashboard): add ActiveJobs page with all components

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: Accessibility Audit & Fixes

**Files:**
- Create: `dashboard/src/utils/a11y.test.ts`
- Modify: `dashboard/src/index.css`
- Modify: All component files as needed

**Step 1: Write accessibility tests with axe-core**

```typescript
// dashboard/src/utils/a11y.test.ts
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { Sidebar } from '../components/organisms/Sidebar';
import { Header } from '../components/organisms/Header';
import { JobQueue } from '../components/organisms/JobQueue';
import { ActivityLog } from '../components/organisms/ActivityLog';
import { ApprovalButtons } from '../components/molecules/ApprovalButtons';
import { BrowserRouter } from 'react-router-dom';

expect.extend(toHaveNoViolations);

describe('Accessibility (WCAG AA)', () => {
  it('Sidebar has no violations', async () => {
    const { container } = render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('Header has no violations', async () => {
    const mockWorkflow = {
      id: 'wf-001',
      issue_id: '#8',
      worktree_name: 'feature',
      status: 'running' as const,
      eta_seconds: 165,
    };
    const { container } = render(<Header workflow={mockWorkflow} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('JobQueue has no violations', async () => {
    const mockWorkflows = [
      {
        id: 'wf-001',
        issue_id: '#8',
        worktree_name: 'feature',
        status: 'running' as const,
        eta_seconds: 165,
      },
    ];
    const { container } = render(
      <JobQueue workflows={mockWorkflows} selectedId={null} onSelect={() => {}} />
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('ActivityLog has no violations', async () => {
    const mockEvents = [
      {
        id: 'evt-001',
        workflow_id: 'wf-001',
        timestamp: '2025-12-01T14:32:07Z',
        agent: 'ARCHITECT',
        message: 'Test message',
      },
    ];
    const { container } = render(<ActivityLog events={mockEvents} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('ApprovalButtons has no violations', async () => {
    const { container } = render(
      <ApprovalButtons
        workflowId="wf-001"
        onApprove={() => {}}
        onReject={() => {}}
        isPending={false}
      />
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
```

**Step 2: Install axe-core dependencies**

```bash
cd dashboard
npm install -D jest-axe @axe-core/react
```

**Step 3: Add reduced motion styles to index.css**

```css
/* dashboard/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Respect prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  .beacon-pulse,
  .animate-beacon-glow,
  .animate-pulse,
  .animate-blink {
    animation: none !important;
  }
}

/* High contrast mode support */
@media (prefers-contrast: high) {
  :root {
    --text-primary: #FFFFFF;
    --text-secondary: #CCCCCC;
    --bg-dark: #000000;
    --bg-main: #0A0A0A;
  }
}

/* Focus visible styles for keyboard navigation */
*:focus-visible {
  outline: 2px solid #FFC857;
  outline-offset: 2px;
}
```

**Step 4: Run accessibility tests**

Run: `cd dashboard && npm test src/utils/a11y.test.ts`
Expected: PASS with no axe violations

**Step 5: Commit**

```bash
git add dashboard/src/utils/a11y.test.ts \
  dashboard/src/index.css \
  dashboard/package.json \
  dashboard/package-lock.json
git commit -m "feat(dashboard): add accessibility audit with axe-core

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 12: Playwright E2E Tests for Multi-Workflow Flow

**Files:**
- Create: `dashboard/e2e/multi-workflow.spec.ts`
- Create: `dashboard/playwright.config.ts`

**Step 1: Write E2E test**

```typescript
// dashboard/e2e/multi-workflow.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Multi-Workflow Selection and Approval Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Start mock server with multiple workflows
    await page.goto('http://localhost:5173/jobs');
    await page.waitForLoadState('networkidle');
  });

  test('displays all active workflows in job queue', async ({ page }) => {
    // Verify job queue shows multiple workflows
    const queueItems = page.locator('[role="button"][aria-pressed]');
    await expect(queueItems).toHaveCount(3);

    // Verify workflow IDs are visible
    await expect(page.locator('text=#8')).toBeVisible();
    await expect(page.locator('text=#7')).toBeVisible();
    await expect(page.locator('text=#9')).toBeVisible();
  });

  test('switches between workflows on click', async ({ page }) => {
    // Initially, workflow #8 is selected (gold border)
    const workflow8 = page.locator('text=#8').locator('..');
    await expect(workflow8).toHaveClass(/border-accent-gold/);

    // Click workflow #7
    await page.locator('text=#7').click();

    // Verify workflow #7 is now selected
    const workflow7 = page.locator('text=#7').locator('..');
    await expect(workflow7).toHaveClass(/border-accent-gold/);

    // Verify header updated to show #7
    await expect(page.locator('h2', { hasText: '#7' })).toBeVisible();
  });

  test('switches workflows using keyboard navigation', async ({ page }) => {
    // Focus first workflow
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab'); // Navigate to job queue

    // Press Enter to select
    await page.keyboard.press('Enter');

    // Verify selection
    const firstItem = page.locator('[role="button"][aria-pressed="true"]').first();
    await expect(firstItem).toBeFocused();
  });

  test('displays approval buttons only for blocked workflows', async ({ page }) => {
    // Select blocked workflow (#8)
    await page.locator('text=#8').click();

    // Verify approval buttons are visible
    await expect(page.locator('button', { hasText: 'Approve' })).toBeVisible();
    await expect(page.locator('button', { hasText: 'Reject' })).toBeVisible();

    // Select completed workflow (#7)
    await page.locator('text=#7').click();

    // Verify approval buttons are hidden
    await expect(page.locator('button', { hasText: 'Approve' })).not.toBeVisible();
  });

  test('approves workflow and updates status', async ({ page }) => {
    // Select blocked workflow
    await page.locator('text=#8').click();

    // Click Approve button
    await page.locator('button', { hasText: 'Approve' }').click();

    // Verify button shows loading state
    await expect(page.locator('[data-testid="loading-spinner"]')).toBeVisible();

    // Wait for approval to complete (mock WebSocket event)
    await page.waitForTimeout(500);

    // Verify status badge updated to RUNNING
    await expect(page.locator('text=RUNNING')).toBeVisible();

    // Verify approval buttons disappeared
    await expect(page.locator('button', { hasText: 'Approve' })).not.toBeVisible();
  });

  test('activity log updates when switching workflows', async ({ page }) => {
    // Select workflow #8
    await page.locator('text=#8').click();

    // Verify activity log shows events for #8
    await expect(page.locator('text=[ARCHITECT]')).toBeVisible();
    await expect(page.locator('text=Issue #8 parsed')).toBeVisible();

    // Select workflow #7
    await page.locator('text=#7').click();

    // Verify activity log updates to show events for #7
    await expect(page.locator('text=Issue #7 completed')).toBeVisible();
  });

  test('respects reduced motion preference', async ({ page, context }) => {
    // Enable reduced motion
    await context.addInitScript(() => {
      Object.defineProperty(window, 'matchMedia', {
        value: (query: string) => ({
          matches: query === '(prefers-reduced-motion: reduce)',
          media: query,
          addEventListener: () => {},
          removeEventListener: () => {},
        }),
      });
    });

    await page.reload();

    // Verify animations are disabled
    const beaconNode = page.locator('[data-testid="map-pin-icon"]').first();
    const animationDuration = await beaconNode.evaluate((el) =>
      window.getComputedStyle(el).animationDuration
    );
    expect(animationDuration).toBe('0.01ms');
  });

  test('keyboard navigation follows ARIA best practices', async ({ page }) => {
    // Tab through interactive elements
    await page.keyboard.press('Tab'); // Sidebar nav
    await page.keyboard.press('Tab'); // First queue item

    // Verify focus is visible
    const focused = page.locator(':focus');
    await expect(focused).toHaveCSS('outline-color', 'rgb(255, 200, 87)'); // Gold outline

    // Navigate with arrow keys (if implemented)
    await page.keyboard.press('ArrowDown');
    const nextFocused = page.locator(':focus');
    await expect(nextFocused).toBeDefined();
  });

  test('announces workflow status changes to screen readers', async ({ page }) => {
    // Select blocked workflow
    await page.locator('text=#8').click();

    // Verify ARIA live region exists
    const liveRegion = page.locator('[aria-live="polite"]');
    await expect(liveRegion).toBeVisible();

    // Approve workflow
    await page.locator('button', { hasText: 'Approve' }').click();

    // Wait for status update
    await page.waitForTimeout(500);

    // Verify live region was updated (content changed)
    const logContent = await liveRegion.textContent();
    expect(logContent).toContain('DEVELOPER');
  });
});
```

**Step 2: Create Playwright config**

```typescript
// dashboard/playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
  },
});
```

**Step 3: Install Playwright**

```bash
cd dashboard
npm install -D @playwright/test
npx playwright install
```

**Step 4: Add E2E script to package.json**

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui"
  }
}
```

**Step 5: Run E2E tests**

Run: `cd dashboard && npm run test:e2e`
Expected: PASS (with mock server setup)

**Step 6: Commit**

```bash
git add dashboard/e2e/multi-workflow.spec.ts \
  dashboard/playwright.config.ts \
  dashboard/package.json \
  dashboard/package-lock.json
git commit -m "test(dashboard): add Playwright E2E tests for multi-workflow flow

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 13: Starfield & Visual Effects

**Files:**
- Create: `dashboard/src/components/effects/Starfield.tsx`
- Create: `dashboard/src/components/effects/CockpitGlass.tsx`
- Create: `dashboard/src/components/effects/Vignette.tsx`
- Modify: `dashboard/src/App.tsx`

**Step 1: Create Starfield effect**

```typescript
// dashboard/src/components/effects/Starfield.tsx
import { FC } from 'react';

export const Starfield: FC = () => (
  <div
    className="fixed inset-0 pointer-events-none opacity-40 motion-reduce:hidden"
    style={{
      background: `
        radial-gradient(1px 1px at 20px 30px, #EFF8E2, transparent),
        radial-gradient(1px 1px at 40px 70px, rgba(239, 248, 226, 0.8), transparent),
        radial-gradient(1px 1px at 50px 160px, rgba(239, 248, 226, 0.6), transparent),
        radial-gradient(1px 1px at 90px 40px, #EFF8E2, transparent),
        radial-gradient(1px 1px at 130px 80px, rgba(239, 248, 226, 0.7), transparent),
        radial-gradient(1.5px 1.5px at 160px 120px, #FFC857, transparent),
        radial-gradient(1px 1px at 200px 50px, rgba(239, 248, 226, 0.5), transparent),
        radial-gradient(1px 1px at 220px 150px, rgba(239, 248, 226, 0.9), transparent),
        radial-gradient(1px 1px at 280px 20px, rgba(239, 248, 226, 0.6), transparent),
        radial-gradient(1.5px 1.5px at 320px 100px, rgba(91, 155, 213, 0.8), transparent),
        radial-gradient(1px 1px at 350px 180px, rgba(239, 248, 226, 0.7), transparent),
        radial-gradient(1px 1px at 400px 60px, #EFF8E2, transparent),
        radial-gradient(1px 1px at 450px 130px, rgba(239, 248, 226, 0.5), transparent),
        radial-gradient(1px 1px at 500px 30px, rgba(239, 248, 226, 0.8), transparent),
        radial-gradient(1.5px 1.5px at 550px 90px, #FFC857, transparent),
        radial-gradient(1px 1px at 600px 170px, rgba(239, 248, 226, 0.6), transparent),
        radial-gradient(1px 1px at 650px 50px, rgba(239, 248, 226, 0.9), transparent),
        radial-gradient(1px 1px at 700px 120px, rgba(239, 248, 226, 0.4), transparent),
        radial-gradient(1px 1px at 750px 80px, #EFF8E2, transparent),
        radial-gradient(1px 1px at 800px 160px, rgba(239, 248, 226, 0.7), transparent)
      `,
      backgroundRepeat: 'repeat',
      backgroundSize: '800px 200px',
    }}
    aria-hidden="true"
  />
);
```

**Step 2: Create CockpitGlass scanlines**

```typescript
// dashboard/src/components/effects/CockpitGlass.tsx
import { FC } from 'react';

export const CockpitGlass: FC = () => (
  <div
    className="fixed inset-0 pointer-events-none z-[1000] motion-reduce:hidden"
    style={{
      background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(239, 248, 226, 0.01) 2px, rgba(239, 248, 226, 0.01) 4px)',
    }}
    aria-hidden="true"
  />
);
```

**Step 3: Create Vignette overlay**

```typescript
// dashboard/src/components/effects/Vignette.tsx
import { FC } from 'react';

export const Vignette: FC = () => (
  <div
    className="fixed inset-0 pointer-events-none z-[999]"
    style={{
      background: 'radial-gradient(ellipse at center, transparent 30%, rgba(13, 26, 18, 0.6) 100%)',
    }}
    aria-hidden="true"
  />
);
```

**Step 4: Update App.tsx to include effects**

```typescript
// dashboard/src/App.tsx
import { FC } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Sidebar } from './components/organisms/Sidebar';
import { ActiveJobs } from './pages/ActiveJobs';
import { Starfield } from './components/effects/Starfield';
import { CockpitGlass } from './components/effects/CockpitGlass';
import { Vignette } from './components/effects/Vignette';

export const App: FC = () => {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-bg-main text-text-primary overflow-hidden relative">
        {/* Visual effects */}
        <Starfield />
        <CockpitGlass />
        <Vignette />

        {/* Main layout */}
        <Sidebar />
        <main className="flex-1 relative z-10 overflow-auto">
          <Routes>
            <Route path="/jobs" element={<ActiveJobs />} />
            <Route path="/" element={<Navigate to="/jobs" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
};
```

**Step 5: Commit**

```bash
git add dashboard/src/components/effects/ dashboard/src/App.tsx
git commit -m "feat(dashboard): add starfield, scanlines, and vignette effects

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Verification Checklist

After completing all tasks, verify:

**Component Functionality:**
- [ ] StatusBadge renders all workflow states (RUNNING, DONE, QUEUED, BLOCKED, CANCELLED)
- [ ] Sidebar navigation highlights active route with gold border
- [ ] Header displays workflow ID, status, and ETA placeholder
- [ ] JobQueue allows selecting workflows with keyboard (Enter/Space)
- [ ] ActivityLog auto-scrolls to bottom when new events arrive
- [ ] BeaconNode shows map pin with pulsing animation for active state
- [ ] FlightEdge renders solid/dashed lines with time labels
- [ ] WorkflowCanvas displays React Flow pipeline with grid background
- [ ] ApprovalButtons disable when action is pending (loading spinner)
- [ ] ActiveJobs page composes all components correctly

**Accessibility (WCAG AA):**
- [ ] All interactive elements have proper ARIA labels
- [ ] Color contrast ratios meet WCAG AA (4.5:1 for text)
- [ ] Keyboard navigation works (Tab, Enter, Space, Arrow keys)
- [ ] Focus visible indicator (gold outline) on all interactive elements
- [ ] ActivityLog has `role="log"` with `aria-live="polite"`
- [ ] WorkflowCanvas has `role="img"` with descriptive aria-label
- [ ] Reduced motion media query disables animations
- [ ] Axe-core audit passes with 0 violations

**Visual Design:**
- [ ] Aviation theme colors applied (gold, green, red, blue)
- [ ] Typography uses Bebas Neue, Barlow Condensed, Source Sans, IBM Plex Mono
- [ ] Starfield background visible with random star placement
- [ ] Cockpit glass scanlines overlay at top layer
- [ ] Vignette darkens edges for depth
- [ ] Beacon nodes glow when active
- [ ] Status badges use correct colors with dark/light text for contrast

**E2E Tests:**
- [ ] Multi-workflow selection works (click to switch)
- [ ] Approval flow updates status badge from BLOCKED → RUNNING
- [ ] Activity log filters by selected workflow
- [ ] Keyboard navigation follows ARIA patterns
- [ ] Screen reader announcements work (aria-live updates)

**Build & Performance:**
- [ ] `npm run build` succeeds with no errors
- [ ] Bundle size is reasonable (<500KB gzipped)
- [ ] No console errors in browser
- [ ] All Vitest unit tests pass
- [ ] All Playwright E2E tests pass

---

## Summary

This plan delivers the complete dashboard UI with:

1. **Atomic design components** - StatusBadge, CompassRose, icons
2. **Molecules** - ApprovalButtons with loading states
3. **Organisms** - Sidebar, Header, JobQueue, ActivityLog, WorkflowCanvas
4. **Pages** - ActiveJobs composing all components
5. **React Flow integration** - BeaconNode and FlightEdge custom components
6. **Full accessibility** - WCAG AA compliance, keyboard navigation, screen reader support
7. **Aviation theme** - Starfield, scanlines, vignette, gold accents, map pin beacons
8. **E2E tests** - Playwright tests for multi-workflow selection and approval flow
9. **Visual effects** - Reduced motion support, high contrast mode

The implementation follows TDD with tests written first for all components. All interactive elements are keyboard accessible with proper ARIA labels. The design matches the HTML mock while maintaining accessibility standards.
