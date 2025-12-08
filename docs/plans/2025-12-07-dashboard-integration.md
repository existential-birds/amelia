# Dashboard Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire Phase 09 infrastructure (loaders, WebSocket, store) to dashboard UI components

**Architecture:** Connect React Router loaders to routes, initialize WebSocket in Layout, implement page components that consume loader data and render UI components

**Tech Stack:** React Router v7, Zustand, WebSocket, TypeScript, Vitest

---

## Pre-Implementation Notes

### Key Codebase Facts
- **Base path:** All files are in `dashboard/src/` (not `src/`)
- **Package manager:** Use `pnpm` (run commands from `dashboard/` directory)
- **Test commands:** `cd dashboard && pnpm test` or `pnpm test <file>`
- **Test patterns:** Colocated tests (e.g., `Component.test.tsx` alongside `Component.tsx`)
- **Test selectors:** Components use `data-slot` attribute (not `data-testid`)

### Router Structure (Actual)
The router uses **flat routes** (not nested):
- `/workflows` - List page
- `/workflows/:id` - Detail page (uses `:id`, not `:workflowId`)
- `/history` - History page
- `/logs` - Logs page (exists but not in plan)

### Type Structure (Actual)
```typescript
// WorkflowSummary - list view
interface WorkflowSummary {
  id: string;
  issue_id: string;        // e.g., "JIRA-123"
  worktree_name: string;   // e.g., "jira-123-feature"
  status: WorkflowStatus;  // 'pending' | 'in_progress' | 'blocked' | 'completed' | 'failed' | 'cancelled'
  started_at: string | null;
  current_stage: string | null;
}

// WorkflowDetail - detail view (extends WorkflowSummary)
interface WorkflowDetail extends WorkflowSummary {
  worktree_path: string;
  completed_at: string | null;
  failure_reason: string | null;
  plan: TaskDAG | null;            // Not "pipeline"
  token_usage: Record<string, TokenSummary>;
  recent_events: WorkflowEvent[];  // Not "events"
}
```

### Component Props Reference
- **JobQueue:** `workflows`, `selectedId`, `onSelect`, `className`
- **WorkflowEmptyState:** `variant`, `title?`, `description?`, `action?`, `className?`
- **WorkflowHeader:** `workflow` (Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_name' | 'status'>), `elapsedTime?`, `className?`
- **WorkflowProgress:** `completed`, `total`, `className?`
- **ActivityLog:** `workflowId`, `initialEvents?`, `className?`
- **ApprovalControls:** `workflowId`, `planSummary` (string), `status?` ('pending' | 'approved' | 'rejected'), `className?`
- **WorkflowCanvas:** `pipeline` (custom Pipeline type), `className?`

---

## Task 1: Wire loaders to router.tsx

**Files:**
- **Modify:** `dashboard/src/router.tsx`
- **Test:** `dashboard/src/router.test.tsx`

**Step 1: Write the failing test**

Create `dashboard/src/router.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest';
import { router } from '@/router';

describe('Router Configuration', () => {
  it('should have loader for workflows route', () => {
    const workflowsRoute = router.routes[0]?.children?.find(
      (r) => r.path === 'workflows'
    );
    expect(workflowsRoute).toBeDefined();
    expect(workflowsRoute?.loader).toBeDefined();
  });

  it('should have loader for workflow detail route', () => {
    const detailRoute = router.routes[0]?.children?.find(
      (r) => r.path === 'workflows/:id'
    );
    expect(detailRoute).toBeDefined();
    expect(detailRoute?.loader).toBeDefined();
  });

  it('should have loader for history route', () => {
    const historyRoute = router.routes[0]?.children?.find(
      (r) => r.path === 'history'
    );
    expect(historyRoute).toBeDefined();
    expect(historyRoute?.loader).toBeDefined();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/router.test.tsx
```

Expected output: Tests fail because loaders are not yet configured

**Step 3: Write minimal implementation**

Modify `dashboard/src/router.tsx`:

```typescript
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { RootErrorBoundary } from '@/components/ErrorBoundary';
import { workflowsLoader, workflowDetailLoader, historyLoader } from '@/loaders/workflows';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    errorElement: <RootErrorBoundary />,
    children: [
      {
        index: true,
        element: <Navigate to="/workflows" replace />
      },
      {
        path: 'workflows',
        lazy: async () => {
          const { default: Component } = await import('@/pages/WorkflowsPage');
          return { Component };
        },
        loader: workflowsLoader,
      },
      {
        path: 'workflows/:id',
        lazy: async () => {
          const { default: Component } = await import('@/pages/WorkflowDetailPage');
          return { Component };
        },
        loader: workflowDetailLoader,
      },
      {
        path: 'history',
        lazy: async () => {
          const { default: Component } = await import('@/pages/HistoryPage');
          return { Component };
        },
        loader: historyLoader,
      },
      {
        path: 'logs',
        lazy: async () => {
          const { default: Component } = await import('@/pages/LogsPage');
          return { Component };
        },
      },
      {
        path: '*',
        element: <Navigate to="/workflows" replace />,
      },
    ],
  },
]);
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/router.test.tsx
```

Expected output: All tests pass

**Step 5: Commit**

```bash
cd /Users/ka/github/amelia-langgraph-bridge && git add dashboard/src/router.tsx dashboard/src/router.test.tsx && git commit -m "feat(router): wire loaders to routes"
```

---

## Task 2: Initialize WebSocket in Layout.tsx

**Files:**
- **Modify:** `dashboard/src/components/Layout.tsx`
- **Test:** `dashboard/src/components/Layout.test.tsx`

**Step 1: Write the failing test**

Create `dashboard/src/components/Layout.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Layout } from './Layout';

// Mock the hooks
const mockUseWebSocket = vi.fn();
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => mockUseWebSocket(),
}));

vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn((selector) => {
    const state = { isConnected: true };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

describe('Layout WebSocket Initialization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should initialize WebSocket on mount', () => {
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    );
    expect(mockUseWebSocket).toHaveBeenCalledTimes(1);
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/components/Layout.test.tsx
```

Expected output: Test fails because WebSocket hook is not called in Layout

**Step 3: Write minimal implementation**

Modify `dashboard/src/components/Layout.tsx` to use the existing DashboardSidebar component:

```typescript
import { Outlet } from 'react-router-dom';
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import { DashboardSidebar } from '@/components/DashboardSidebar';
import { NavigationProgress } from '@/components/NavigationProgress';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useWorkflowStore } from '@/store/workflowStore';
import { useNavigation } from 'react-router-dom';

export function Layout() {
  // Initialize WebSocket connection
  useWebSocket();

  const navigation = useNavigation();
  const isConnected = useWorkflowStore((state) => state.isConnected);
  const isNavigating = navigation.state !== 'idle';

  return (
    <SidebarProvider defaultOpen>
      <DashboardSidebar isConnected={isConnected} />
      <SidebarInset>
        {isNavigating && <NavigationProgress />}
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  );
}
```

**Note:** The `DashboardSidebar` component will need to be updated to:
1. Accept an `isConnected: boolean` prop
2. Display the connection indicator in `SidebarFooter` based on this prop
3. Use actual React Router `Link` components for navigation (instead of button elements)

**Step 4: Run test to verify it passes**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/components/Layout.test.tsx
```

Expected output: All tests pass

**Step 5: Commit**

```bash
cd /Users/ka/github/amelia-langgraph-bridge && git add dashboard/src/components/Layout.tsx dashboard/src/components/Layout.test.tsx && git commit -m "feat(layout): initialize WebSocket and wire connection indicator"
```

---

## Task 3: Implement WorkflowsPage

**Files:**
- **Modify:** `dashboard/src/pages/WorkflowsPage.tsx`
- **Test:** `dashboard/src/pages/WorkflowsPage.test.tsx`

**Step 1: Write the failing test**

Create `dashboard/src/pages/WorkflowsPage.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import WorkflowsPage from './WorkflowsPage';

// Mock data matching actual WorkflowSummary type
const mockWorkflows = [
  {
    id: 'wf-001',
    issue_id: 'PROJ-123',
    worktree_name: 'proj-123-feature',
    status: 'in_progress' as const,
    started_at: '2025-12-07T09:00:00Z',
    current_stage: 'developer',
  },
];

// Mock hooks
vi.mock('@/hooks/useWorkflows', () => ({
  useWorkflows: vi.fn(),
}));

import { useWorkflows } from '@/hooks/useWorkflows';

describe('WorkflowsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render JobQueue when workflows exist', () => {
    vi.mocked(useWorkflows).mockReturnValue({
      workflows: mockWorkflows,
      isConnected: true,
      isRevalidating: false,
      revalidate: vi.fn(),
    });

    render(
      <MemoryRouter>
        <WorkflowsPage />
      </MemoryRouter>
    );

    // JobQueue uses data-slot attribute
    expect(document.querySelector('[data-slot="job-queue"]')).toBeInTheDocument();
  });

  it('should render WorkflowEmptyState when no workflows', () => {
    vi.mocked(useWorkflows).mockReturnValue({
      workflows: [],
      isConnected: true,
      isRevalidating: false,
      revalidate: vi.fn(),
    });

    render(
      <MemoryRouter>
        <WorkflowsPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/no active workflows/i)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/pages/WorkflowsPage.test.tsx
```

Expected output: Tests fail because WorkflowsPage is not implemented

**Step 3: Write minimal implementation**

Modify `dashboard/src/pages/WorkflowsPage.tsx`:

```typescript
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorkflows } from '@/hooks/useWorkflows';
import { JobQueue } from '@/components/JobQueue';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { ScrollArea } from '@/components/ui/scroll-area';

export default function WorkflowsPage() {
  const { workflows, isConnected, isRevalidating } = useWorkflows();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const handleSelect = (workflowId: string) => {
    setSelectedId(workflowId);
    navigate(`/workflows/${workflowId}`);
  };

  if (workflows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <WorkflowEmptyState variant="no-workflows" />
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="p-6">
        <div className="mb-6">
          <h1 className="text-3xl font-display font-bold tracking-wider">Active Workflows</h1>
          <p className="text-muted-foreground font-mono text-sm mt-1">
            {isConnected ? 'Connected' : 'Disconnected'} {isRevalidating && '• Refreshing...'} • {workflows.length} active
          </p>
        </div>
        <JobQueue
          workflows={workflows}
          selectedId={selectedId}
          onSelect={handleSelect}
        />
      </div>
    </ScrollArea>
  );
}
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/pages/WorkflowsPage.test.tsx
```

Expected output: All tests pass

**Step 5: Commit**

```bash
cd /Users/ka/github/amelia-langgraph-bridge && git add dashboard/src/pages/WorkflowsPage.tsx dashboard/src/pages/WorkflowsPage.test.tsx && git commit -m "feat(pages): implement WorkflowsPage with JobQueue and EmptyState"
```

---

## Task 4: Implement WorkflowDetailPage

**Files:**
- **Modify:** `dashboard/src/pages/WorkflowDetailPage.tsx`
- **Test:** `dashboard/src/pages/WorkflowDetailPage.test.tsx`

**Step 1: Write the failing test**

Create `dashboard/src/pages/WorkflowDetailPage.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import WorkflowDetailPage from './WorkflowDetailPage';
import type { WorkflowDetail } from '@/types';

// Mock data matching actual WorkflowDetail type
const mockWorkflow: WorkflowDetail = {
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_name: 'proj-123-feature',
  worktree_path: '/tmp/worktrees/proj-123',
  status: 'in_progress',
  started_at: '2025-12-07T09:00:00Z',
  completed_at: null,
  current_stage: 'developer',
  failure_reason: null,
  plan: {
    tasks: [
      { id: 't1', description: 'Setup', agent: 'developer', dependencies: [], status: 'completed' },
      { id: 't2', description: 'Implement', agent: 'developer', dependencies: ['t1'], status: 'in_progress' },
    ],
    execution_order: ['t1', 't2'],
  },
  token_usage: {},
  recent_events: [],
};

// Mock loader data
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
  };
});

import { useLoaderData } from 'react-router-dom';

describe('WorkflowDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render workflow header with issue_id', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflow: mockWorkflow });

    render(
      <MemoryRouter>
        <WorkflowDetailPage />
      </MemoryRouter>
    );

    expect(screen.getByText('PROJ-123')).toBeInTheDocument();
  });

  it('should render workflow progress', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflow: mockWorkflow });

    render(
      <MemoryRouter>
        <WorkflowDetailPage />
      </MemoryRouter>
    );

    // WorkflowProgress uses data-slot="workflow-progress"
    expect(document.querySelector('[data-slot="workflow-progress"]')).toBeInTheDocument();
  });

  it('should render activity log', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflow: mockWorkflow });

    render(
      <MemoryRouter>
        <WorkflowDetailPage />
      </MemoryRouter>
    );

    expect(document.querySelector('[data-slot="activity-log"]')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/pages/WorkflowDetailPage.test.tsx
```

Expected output: Tests fail because WorkflowDetailPage is not implemented

**Step 3: Write minimal implementation**

Modify `dashboard/src/pages/WorkflowDetailPage.tsx`:

```typescript
import { useLoaderData } from 'react-router-dom';
import type { WorkflowDetailLoaderData } from '@/types/api';
import { WorkflowHeader } from '@/components/WorkflowHeader';
import { WorkflowProgress } from '@/components/WorkflowProgress';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import { ActivityLog } from '@/components/ActivityLog';
import { ApprovalControls } from '@/components/ApprovalControls';
import { ScrollArea } from '@/components/ui/scroll-area';

export default function WorkflowDetailPage() {
  const { workflow } = useLoaderData() as WorkflowDetailLoaderData;

  // Calculate progress from plan tasks
  const tasks = workflow.plan?.tasks ?? [];
  const completedTasks = tasks.filter((task) => task.status === 'completed').length;
  const totalTasks = tasks.length;

  // Transform TaskDAG to Pipeline format for WorkflowCanvas
  const pipeline = transformPlanToPipeline(workflow);

  // Determine approval status from workflow status
  const approvalStatus = workflow.status === 'blocked' ? 'pending' as const : undefined;

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col h-full">
        {/* Header */}
        <WorkflowHeader workflow={workflow} />

        {/* Main content grid */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
          {/* Left column: Canvas and Progress */}
          <div className="space-y-6">
            <WorkflowProgress completed={completedTasks} total={totalTasks} />
            <WorkflowCanvas pipeline={pipeline} />
          </div>

          {/* Right column: Activity and Approvals */}
          <div className="space-y-6">
            <ActivityLog
              workflowId={workflow.id}
              initialEvents={workflow.recent_events}
              className="h-80"
            />
            {workflow.status === 'blocked' && workflow.plan && (
              <ApprovalControls
                workflowId={workflow.id}
                planSummary={`${totalTasks} tasks planned`}
                status={approvalStatus}
              />
            )}
          </div>
        </div>
      </div>
    </ScrollArea>
  );
}

/**
 * Transform TaskDAG from API to Pipeline format for WorkflowCanvas.
 */
function transformPlanToPipeline(workflow: WorkflowDetailLoaderData['workflow']) {
  // Default pipeline stages (architect -> developer -> reviewer)
  const stages = ['architect', 'developer', 'reviewer'];

  // Determine status for each stage based on workflow state
  const getStageStatus = (stage: string): 'completed' | 'active' | 'pending' | 'blocked' => {
    if (workflow.current_stage === stage) return 'active';
    const stageIndex = stages.indexOf(stage);
    const currentIndex = stages.indexOf(workflow.current_stage ?? '');
    if (currentIndex === -1) return 'pending';
    if (stageIndex < currentIndex) return 'completed';
    return 'pending';
  };

  return {
    nodes: stages.map((stage) => ({
      id: stage,
      label: stage.charAt(0).toUpperCase() + stage.slice(1),
      status: getStageStatus(stage),
    })),
    edges: [
      { from: 'architect', to: 'developer', label: 'plan', status: getStageStatus('developer') === 'pending' ? 'pending' as const : 'completed' as const },
      { from: 'developer', to: 'reviewer', label: 'code', status: getStageStatus('reviewer') === 'pending' ? 'pending' as const : 'completed' as const },
    ],
  };
}
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/pages/WorkflowDetailPage.test.tsx
```

Expected output: All tests pass

**Step 5: Commit**

```bash
cd /Users/ka/github/amelia-langgraph-bridge && git add dashboard/src/pages/WorkflowDetailPage.tsx dashboard/src/pages/WorkflowDetailPage.test.tsx && git commit -m "feat(pages): implement WorkflowDetailPage with full component layout"
```

---

## Task 5: Implement HistoryPage

**Files:**
- **Modify:** `dashboard/src/pages/HistoryPage.tsx`
- **Test:** `dashboard/src/pages/HistoryPage.test.tsx`

**Step 1: Write the failing test**

Create `dashboard/src/pages/HistoryPage.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HistoryPage from './HistoryPage';
import type { WorkflowSummary } from '@/types';

const mockWorkflows: WorkflowSummary[] = [
  {
    id: 'wf-001',
    issue_id: 'PROJ-123',
    worktree_name: 'proj-123-feature',
    status: 'completed',
    started_at: '2025-12-07T09:00:00Z',
    current_stage: null,
  },
  {
    id: 'wf-002',
    issue_id: 'PROJ-124',
    worktree_name: 'proj-124-bugfix',
    status: 'failed',
    started_at: '2025-12-07T08:00:00Z',
    current_stage: null,
  },
];

// Mock loader data
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
    useNavigate: () => vi.fn(),
  };
});

import { useLoaderData } from 'react-router-dom';

describe('HistoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render completed workflows list', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: mockWorkflows });

    render(
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    );

    expect(screen.getByText('PROJ-123')).toBeInTheDocument();
    expect(screen.getByText('PROJ-124')).toBeInTheDocument();
  });

  it('should show empty state when no history', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: [] });

    render(
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/no activity yet/i)).toBeInTheDocument();
  });

  it('should display workflow status badges', () => {
    vi.mocked(useLoaderData).mockReturnValue({ workflows: mockWorkflows });

    render(
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    );

    expect(screen.getByText('DONE')).toBeInTheDocument();
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/pages/HistoryPage.test.tsx
```

Expected output: Tests fail because HistoryPage is not implemented

**Step 3: Write minimal implementation**

Modify `dashboard/src/pages/HistoryPage.tsx`:

```typescript
import { useLoaderData, useNavigate } from 'react-router-dom';
import type { WorkflowsLoaderData } from '@/types/api';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { StatusBadge } from '@/components/StatusBadge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

export default function HistoryPage() {
  const { workflows } = useLoaderData() as WorkflowsLoaderData;
  const navigate = useNavigate();

  if (workflows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <WorkflowEmptyState variant="no-activity" />
      </div>
    );
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Unknown';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <ScrollArea className="h-full">
      <div className="p-6">
        <div className="mb-6">
          <h1 className="text-3xl font-display font-bold tracking-wider">Workflow History</h1>
          <p className="text-muted-foreground font-mono text-sm mt-1">
            {workflows.length} past workflows
          </p>
        </div>

        <div className="space-y-3">
          {workflows.map((workflow) => (
            <div
              key={workflow.id}
              className={cn(
                "border border-border rounded-lg p-4 bg-card/50",
                "hover:bg-card cursor-pointer transition-colors"
              )}
              onClick={() => navigate(`/workflows/${workflow.id}`)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-display text-xl font-bold tracking-wider">
                    {workflow.issue_id}
                  </h3>
                  <p className="text-sm font-mono text-muted-foreground mt-1">
                    {workflow.worktree_name}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={workflow.status} />
                  <span className="text-sm font-mono text-muted-foreground">
                    {formatDate(workflow.started_at)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </ScrollArea>
  );
}
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/pages/HistoryPage.test.tsx
```

Expected output: All tests pass

**Step 5: Commit**

```bash
cd /Users/ka/github/amelia-langgraph-bridge && git add dashboard/src/pages/HistoryPage.tsx dashboard/src/pages/HistoryPage.test.tsx && git commit -m "feat(pages): implement HistoryPage with workflow list and status badges"
```

---

## Task 6: Add test fixtures

**Files:**
- **Create:** `dashboard/src/test/fixtures.ts`
- **Test:** `dashboard/src/test/fixtures.test.ts`

**Step 1: Write the failing test**

Create `dashboard/src/test/fixtures.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { mockWorkflowSummaries, mockWorkflowDetail } from './fixtures';

describe('Test Fixtures', () => {
  it('should export mockWorkflowSummaries array', () => {
    expect(mockWorkflowSummaries).toBeDefined();
    expect(Array.isArray(mockWorkflowSummaries)).toBe(true);
    expect(mockWorkflowSummaries.length).toBeGreaterThan(0);
  });

  it('should export mockWorkflowDetail object', () => {
    expect(mockWorkflowDetail).toBeDefined();
    expect(mockWorkflowDetail.id).toBeDefined();
    expect(mockWorkflowDetail.issue_id).toBeDefined();
  });

  it('mockWorkflowSummaries should have required fields', () => {
    const summary = mockWorkflowSummaries[0];
    expect(summary.id).toBeDefined();
    expect(summary.status).toBeDefined();
    expect(summary.issue_id).toBeDefined();
    expect(summary.worktree_name).toBeDefined();
  });

  it('mockWorkflowDetail should have all required fields', () => {
    expect(mockWorkflowDetail.id).toBeDefined();
    expect(mockWorkflowDetail.status).toBeDefined();
    expect(mockWorkflowDetail.issue_id).toBeDefined();
    expect(mockWorkflowDetail.plan).toBeDefined();
    expect(mockWorkflowDetail.recent_events).toBeDefined();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/test/fixtures.test.ts
```

Expected output: Tests fail if fixtures are missing

**Step 3: Write minimal implementation**

Create `dashboard/src/test/fixtures.ts`:

```typescript
import type { WorkflowSummary, WorkflowDetail, WorkflowEvent } from '@/types';

export const mockWorkflowSummaries: WorkflowSummary[] = [
  {
    id: 'wf-001',
    issue_id: 'PROJ-123',
    worktree_name: 'proj-123-auth',
    status: 'in_progress',
    started_at: '2025-12-07T09:00:00Z',
    current_stage: 'developer',
  },
  {
    id: 'wf-002',
    issue_id: 'PROJ-124',
    worktree_name: 'proj-124-dashboard',
    status: 'blocked',
    started_at: '2025-12-07T08:30:00Z',
    current_stage: 'architect',
  },
  {
    id: 'wf-003',
    issue_id: 'PROJ-122',
    worktree_name: 'proj-122-bugfix',
    status: 'completed',
    started_at: '2025-12-07T08:00:00Z',
    current_stage: null,
  },
];

export const mockWorkflowEvents: WorkflowEvent[] = [
  {
    id: 'evt-001',
    workflow_id: 'wf-001',
    sequence: 1,
    timestamp: '2025-12-07T09:00:00Z',
    agent: 'orchestrator',
    event_type: 'workflow_started',
    message: 'Workflow started',
  },
  {
    id: 'evt-002',
    workflow_id: 'wf-001',
    sequence: 2,
    timestamp: '2025-12-07T09:05:00Z',
    agent: 'architect',
    event_type: 'stage_started',
    message: 'Architect agent started planning',
  },
  {
    id: 'evt-003',
    workflow_id: 'wf-001',
    sequence: 3,
    timestamp: '2025-12-07T09:10:00Z',
    agent: 'architect',
    event_type: 'stage_completed',
    message: 'Plan generated with 4 tasks',
  },
];

export const mockWorkflowDetail: WorkflowDetail = {
  id: 'wf-001',
  issue_id: 'PROJ-123',
  worktree_name: 'proj-123-auth',
  worktree_path: '/tmp/worktrees/proj-123-auth',
  status: 'in_progress',
  started_at: '2025-12-07T09:00:00Z',
  completed_at: null,
  current_stage: 'developer',
  failure_reason: null,
  plan: {
    tasks: [
      {
        id: 't1',
        description: 'Generate implementation plan',
        agent: 'architect',
        dependencies: [],
        status: 'completed',
      },
      {
        id: 't2',
        description: 'Implement JWT middleware',
        agent: 'developer',
        dependencies: ['t1'],
        status: 'in_progress',
      },
      {
        id: 't3',
        description: 'Add authentication routes',
        agent: 'developer',
        dependencies: ['t2'],
        status: 'pending',
      },
      {
        id: 't4',
        description: 'Write tests',
        agent: 'developer',
        dependencies: ['t3'],
        status: 'pending',
      },
    ],
    execution_order: ['t1', 't2', 't3', 't4'],
  },
  token_usage: {
    architect: { total_tokens: 5000, total_cost_usd: 0.05 },
    developer: { total_tokens: 12000, total_cost_usd: 0.12 },
  },
  recent_events: mockWorkflowEvents,
};
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test src/test/fixtures.test.ts
```

Expected output: All tests pass

**Step 5: Commit**

```bash
cd /Users/ka/github/amelia-langgraph-bridge && git add dashboard/src/test/fixtures.ts dashboard/src/test/fixtures.test.ts && git commit -m "feat(tests): add comprehensive workflow fixtures for testing"
```

---

## Task 7: Run full test suite and verify

**Files:**
- No new files, validation only

**Step 1: Run all tests**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm test:run
```

Expected output: All tests pass

**Step 2: Run type checking**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm type-check
```

Expected output: No type errors

**Step 3: Run linting**

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm lint
```

Expected output: No linting errors

**Step 4: Manual smoke test**

Start the development server and verify:

```bash
cd /Users/ka/github/amelia-langgraph-bridge/dashboard && pnpm dev
```

1. Navigate to `/workflows` - should show JobQueue or EmptyState
2. Click a workflow - should navigate to detail page
3. Detail page should show all components (header, progress, canvas, activity, approvals if blocked)
4. Navigate to `/history` - should show completed workflows
5. Connection indicator in sidebar should reflect WebSocket state

**Step 5: Final commit**

```bash
cd /Users/ka/github/amelia-langgraph-bridge && git add -A && git commit -m "feat(dashboard): complete Phase 10 - wire infrastructure to UI

- Wire loaders to all routes in router.tsx
- Initialize WebSocket in Layout component
- Connect store to connection indicator
- Implement WorkflowsPage with JobQueue/EmptyState
- Implement WorkflowDetailPage with full layout
- Implement HistoryPage with workflow list
- Add comprehensive test fixtures

All Phase 09 infrastructure now connected to UI components.
Dashboard is fully functional with real-time updates."
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] All routes have loaders configured
- [ ] WebSocket initializes on app mount (in Layout)
- [ ] Connection indicator shows real connection state from store
- [ ] WorkflowsPage renders JobQueue with real data
- [ ] WorkflowDetailPage shows header, progress, canvas, activity, and approvals
- [ ] HistoryPage displays completed workflows with status badges
- [ ] All tests pass (unit + integration)
- [ ] Type checking passes with no errors
- [ ] Linting passes with no warnings
- [ ] Manual testing confirms UI works end-to-end

---

## Remaining Ambiguities

The following items may need human review or decision:

1. **Pipeline Visualization**: The `transformPlanToPipeline` function makes assumptions about the 3-stage pipeline (architect → developer → reviewer). If the actual workflow has different stages, this may need adjustment.

2. **Approval Status Mapping**: The plan assumes `status === 'blocked'` means pending approval. Verify this matches the actual backend behavior.
