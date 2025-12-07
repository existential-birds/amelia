# WorkflowsPage Canvas Design

**Date:** 2025-12-07
**Status:** Approved (Revised after seventh review)

## Overview

Update the WorkflowsPage to match the design mock by displaying a workflow canvas for the active job. Currently, the page only shows the JobQueue list. The new layout will show the full workflow pipeline visualization at the top with the job queue and activity log below.

## Review Notes

This plan was reviewed and revised to address:
- **TDD compliance**: Tasks reordered to write tests BEFORE implementation
- **Type alignment**: Use `started_at` instead of non-existent `updated_at` field
- **Architecture**: Use React Router loader pattern instead of custom `useWorkflowDetail` hook
- **Missing utilities**: Added tasks to extract `buildPipeline()` and create `getActiveWorkflow()`
- **Error handling**: Added graceful degradation for loader failures
- **Library usage**: Added ScrollArea recommendations for consistency

### Second Review (2025-12-07)
Additional improvements based on detailed analysis:
- **Type completeness**: Added `activeDetail` to `WorkflowsLoaderData` type documentation
- **Route requirements**: Added `useFetcher.load()` route configuration requirement
- **Props alignment**: Added note about `WorkflowHeader` props type compatibility
- **Test behavior focus**: Rewrote test descriptions to verify behavior, not implementation
- **Type safety**: Added `useLoaderData<typeof loader>()` recommendation
- **Realistic estimates**: Adjusted parallelization savings from ~30% to ~10-15%

### Third Review (2025-12-07)
Fixes based on detailed agent review:
- **Fetcher route**: Changed to use existing `/workflows/:id` route instead of new `/api/workflows/:id`
- **Type safety**: Updated to use `useLoaderData<typeof loader>()` pattern consistently
- **useFetcher typing**: Fixed generic to reference loader type
- **Parallelization**: Moved JobQueue task to Batch 2 (has dependency on WorkflowsPage behavior)
- **Savings estimate**: Corrected from 10-15% to ~35%

### Fourth Review (2025-12-07)
Fixes based on code review:
- **Import path**: Fixed `workflowDetailLoader` import from `@/loaders/workflow-detail` to `@/loaders/workflows`
- **Template literal**: Fixed single quotes to backticks in `fetcher.load()` call
- **Premature optimization**: Removed unnecessary `useMemo` wrappers - O(n) operations on <100 items don't need memoization
- **Fetcher state**: Changed to `fetcher.state !== 'idle'` for comprehensive loading detection
- **Time savings**: Corrected estimate from ~35% to ~22-25% based on dependency analysis

### Fifth Review (2025-12-07)
Final fixes based on detailed review:
- **useFetcher typing**: Fixed generic from `typeof workflowDetailLoader()` to `Awaited<ReturnType<typeof workflowDetailLoader>>()` for proper type inference
- **Import alignment**: Updated import statement to match corrected useFetcher typing pattern
- **Test coverage**: Added missing test case for pre-loaded activeDetail optimization path
- **Parallelization clarity**: Added Batch 0 for prerequisites, clarified sequential work within agents, fixed Agent C dependency on Agent A
- **Time estimates**: Corrected savings from ~22-25% to ~18-20% based on refined dependency analysis
- **Prerequisites**: Added task to create utils directory structure

### Sixth Review (2025-12-07)
Pre-execution fixes based on comprehensive 5-agent review:
- **Type completeness**: Added `activeDetail` field to `WorkflowsLoaderData` type in codebase
- **Directory structure**: Created `dashboard/src/utils/__tests__` directory
- **Props alignment**: Updated `JobQueue.onSelect` signature to accept `string | null`
- **useFetcher typing**: Simplified generic from `Awaited<ReturnType<typeof loader>>` to `typeof loader`
- **Test coverage**: Added missing buildPipeline edge case tests (null plan, no dependencies)

### Seventh Review (2025-12-07)
Design system compliance fixes:
- **Card components**: Updated Component Structure to use shadcn `Card`, `CardHeader`, `CardContent` for the active workflow section instead of raw `<div>` and `<>` fragments
- **Separator usage**: Replaced `className="border-b"` with semantic `<Separator />` component for visual dividers
- **Import alignment**: Added Card and Separator imports to the WorkflowsPage import statement
- **Visual hierarchy**: Card wraps the header+canvas section to group them semantically; bottom grid sections use ScrollArea without additional Cards to avoid visual noise
- **Pattern consistency**: Matches the anti-pattern fix needed in `WorkflowDetailPage.tsx` (lines 86, 95, 114)

## Prerequisites (Before Execution)

Before running the implementation tasks, verify:

1. [ ] **Update `WorkflowsLoaderData` type** in `dashboard/src/types/api.ts`:
   ```typescript
   export interface WorkflowsLoaderData {
     workflows: WorkflowSummary[];
     activeDetail: WorkflowDetail | null;  // Add this field
   }
   ```

2. [ ] **Update `WorkflowHeader` props** to accept `WorkflowDetail | Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_name' | 'status'>`

3. [ ] **Create utils directory**: `mkdir -p dashboard/src/utils/__tests__`

## Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  WORKFLOW HEADER + CANVAS (full width)                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Issue → Architect → Developer → Reviewer → Done         ││
│  └─────────────────────────────────────────────────────────┘│
├───────────────────┬─────────────────────────────────────────┤
│  JOB QUEUE (1/3)  │  ACTIVITY LOG (2/3)                     │
│  ┌─────────────┐  │  ┌─────────────────────────────────────┐│
│  │ #8 RUNNING  │  │  │ 14:32:07Z [ARCHITECT] Issue #8...   ││
│  │ #7 DONE     │  │  │ 14:32:45Z [ARCHITECT] Plan approved ││
│  │ #9 QUEUED   │  │  │ 14:33:12Z [DEVELOPER] Task received ││
│  └─────────────┘  │  └─────────────────────────────────────┘│
└───────────────────┴─────────────────────────────────────────┘
```

- Canvas at TOP, full width of page
- Below: JobQueue on LEFT (1/3 width), ActivityLog on RIGHT (2/3 width)

## State Selection Logic

Which workflow to display in the canvas/activity area:

```typescript
// Location: dashboard/src/utils/workflow.ts (NEW FILE)
import type { WorkflowSummary } from '@/types';

/**
 * Determines which workflow to display as the "active" workflow.
 *
 * Priority:
 * 1. Running workflow (status === 'in_progress')
 * 2. Most recently started completed workflow
 *
 * @param workflows - List of workflow summaries
 * @returns The active workflow or null if none exist
 */
export function getActiveWorkflow(workflows: WorkflowSummary[]): WorkflowSummary | null {
  // Priority 1: Running workflow
  const running = workflows.find(w => w.status === 'in_progress');
  if (running) return running;

  // Priority 2: Last completed (most recent by started_at)
  // Note: Using started_at since updated_at doesn't exist in WorkflowSummary
  const completed = workflows
    .filter(w => w.status === 'completed')
    .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());

  return completed[0] ?? null;
}
```

### Display States

| State | Canvas Area | Activity Log |
|-------|-------------|--------------|
| Running workflow exists | Show running workflow's pipeline | Live activity stream |
| No running, has completed | Show last completed pipeline | Historical events |
| No workflows at all | `WorkflowEmptyState` (full page) | - |

### Selection Behavior

- User can click any job in the queue to view its details
- This updates the canvas + activity log without page navigation
- A subtle highlight indicates which job is currently displayed

## Data Fetching Strategy

**Pre-fetch active workflow in loader:**
- Route loader fetches both `workflows` list AND detail for the active one
- Instant display for the default view
- Graceful degradation if detail fetch fails (show list without canvas)
- On-demand fetching when user clicks a different job

```typescript
// Location: dashboard/src/loaders/workflows.ts (UPDATE)
import { api } from '@/api/client';
import { getActiveWorkflow } from '@/utils/workflow';
import type { WorkflowsLoaderData } from '@/types/api';

/**
 * Loader for WorkflowsPage - fetches workflow list and active workflow detail.
 *
 * @returns Workflow list and optionally the active workflow's detail
 */
export async function workflowsLoader(): Promise<WorkflowsLoaderData> {
  const workflows = await api.getWorkflows();
  const active = getActiveWorkflow(workflows);

  // Fetch active detail with error handling - don't fail the whole page if detail fails
  let activeDetail = null;
  if (active) {
    try {
      activeDetail = await api.getWorkflow(active.id);
    } catch (error) {
      console.error('Failed to fetch active workflow detail:', error);
      // Continue with null - page will show list without canvas
    }
  }

  return { workflows, activeDetail };
}
```

```typescript
// Location: dashboard/src/types/api.ts (UPDATE)
// NOTE: This type already exists but needs activeDetail field added
import type { WorkflowSummary, WorkflowDetail } from '@/types';

export interface WorkflowsLoaderData {
  workflows: WorkflowSummary[];
  activeDetail: WorkflowDetail | null;  // ADD: currently missing from existing type
}
```

**Route Note for useFetcher:**
The `fetcher.load('/workflows/${id}')` pattern reuses the existing `/workflows/:id` route and its `workflowDetailLoader`, eliminating the need for a new API route.

**For user-selected jobs:** Use React Router's `useFetcher` hook (not a custom hook):
- Leverages React Router's built-in caching
- Shows skeleton in ActivityLog while loading
- No custom state management needed

## Component Structure

```tsx
// Location: dashboard/src/pages/WorkflowsPage.tsx (UPDATE)
import { useState } from 'react';
import { useLoaderData, useFetcher } from 'react-router-dom';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { WorkflowEmptyState } from '@/components/WorkflowEmptyState';
import { WorkflowHeader } from '@/components/WorkflowHeader';
import { WorkflowCanvas } from '@/components/WorkflowCanvas';
import { ActivityLog } from '@/components/ActivityLog';
import { ActivityLogSkeleton } from '@/components/ActivityLogSkeleton';
import { JobQueue } from '@/components/JobQueue';
import { getActiveWorkflow } from '@/utils/workflow';
import { buildPipeline } from '@/utils/pipeline';
import type { workflowsLoader, workflowDetailLoader } from '@/loaders/workflows';

export default function WorkflowsPage() {
  const { workflows, activeDetail } = useLoaderData<typeof workflowsLoader>();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const fetcher = useFetcher<typeof workflowDetailLoader>();

  // Auto-select active workflow
  // Note: No useMemo needed - getActiveWorkflow is O(n) on <100 items
  const activeWorkflow = getActiveWorkflow(workflows);
  const displayedId = selectedId ?? activeWorkflow?.id ?? null;

  // Determine which detail to show:
  // 1. If user selected a different workflow and fetcher has data, use fetcher data
  // 2. If displaying the active workflow, use pre-loaded activeDetail
  // 3. Otherwise show loading state
  const isLoadingDetail = fetcher.state !== 'idle';
  let detail = null;
  if (selectedId && fetcher.data?.workflow) {
    detail = fetcher.data.workflow;
  } else if (displayedId === activeWorkflow?.id) {
    detail = activeDetail;
  }

  // Fetch detail when user selects a different workflow
  // NOTE: Uses existing /workflows/:id route and workflowDetailLoader
  const handleSelect = (id: string | null) => {
    setSelectedId(id);
    if (id && id !== activeWorkflow?.id) {
      fetcher.load(`/workflows/${id}`);
    }
  };

  if (workflows.length === 0) {
    return <WorkflowEmptyState variant="no-workflows" />;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top: Header + Canvas (full width) - Card groups related content semantically */}
      {detail && (
        <Card className="rounded-none border-x-0 border-t-0">
          <CardHeader className="p-0">
            {/* NOTE: WorkflowHeader currently expects Pick<WorkflowSummary, ...>
                Either update WorkflowHeader to accept WorkflowDetail | WorkflowSummary,
                or pass only the required fields: { id, issue_id, worktree_name, status } */}
            <WorkflowHeader workflow={detail} />
          </CardHeader>
          <Separator />
          <CardContent className="p-0">
            <WorkflowCanvas pipeline={buildPipeline(detail)} />
          </CardContent>
        </Card>
      )}

      {/* Bottom: Queue + Activity (split) - ScrollArea provides overflow handling
          Note: No additional Cards here to avoid visual noise; ScrollArea is sufficient */}
      <div className="flex-1 grid grid-cols-[1fr_2fr] gap-4 p-4 overflow-hidden">
        <ScrollArea className="h-full">
          <JobQueue
            workflows={workflows}
            selectedId={displayedId}
            onSelect={handleSelect}
          />
        </ScrollArea>
        <ScrollArea className="h-full">
          {detail ? (
            <ActivityLog workflowId={detail.id} initialEvents={detail.recent_events} />
          ) : isLoadingDetail ? (
            <ActivityLogSkeleton />
          ) : null}
        </ScrollArea>
      </div>
    </div>
  );
}
```

## Implementation Tasks (TDD Order)

Following Test-Driven Development: tests are written BEFORE implementation.

### Phase 1: RED - Write Failing Tests

#### 1.1 Test `getActiveWorkflow` utility
**File:** `dashboard/src/utils/__tests__/workflow.test.ts` (NEW)
```typescript
describe('getActiveWorkflow', () => {
  it('should return running workflow when one exists')
  it('should return most recent completed workflow when no running')
  it('should return null when no workflows exist')
  it('should prioritize running over completed')
  it('should sort completed by started_at descending')
})
```

#### 1.2 Test `buildPipeline` utility
**File:** `dashboard/src/utils/__tests__/pipeline.test.ts` (NEW)
```typescript
describe('buildPipeline', () => {
  it('should convert workflow detail to pipeline nodes')
  it('should create edges between sequential stages')
  it('should mark current stage as active')
  it('should handle empty stages array')
  it('should handle workflow detail with null plan')
  it('should handle stages with no dependencies')
})
```

#### 1.3 Test `workflowsLoader` updates
**File:** `dashboard/src/loaders/__tests__/workflows.test.ts` (UPDATE)
```typescript
describe('workflowsLoader', () => {
  it('should return workflows list and activeDetail in response')
  it('should return null activeDetail when no workflows exist')
  it('should return null activeDetail when detail API call fails')
  it('should include active workflow detail when running workflow exists')
})
```

#### 1.4 Test `WorkflowsPage` new layout
**File:** `dashboard/src/pages/WorkflowsPage.test.tsx` (UPDATE)
```typescript
describe('WorkflowsPage', () => {
  it('should display workflow header with issue info when activeDetail exists')
  it('should display workflow pipeline canvas when activeDetail exists')
  it('should display job queue and activity log side by side')
  it('should display loading indicator when fetching selected workflow')
  it('should display selected workflow details when user clicks a different job')
  it('should not show loading skeleton when activeDetail is pre-loaded from loader')
  it('should allow scrolling when job queue content overflows')
})
```

### Phase 2: GREEN - Implementation

#### 2.1 Create `getActiveWorkflow` utility
**File:** `dashboard/src/utils/workflow.ts` (NEW)
- Implement selection logic (see State Selection Logic section above)
- Export from `dashboard/src/utils/index.ts`

#### 2.2 Extract `buildPipeline` utility
**File:** `dashboard/src/utils/pipeline.ts` (NEW)
- Extract logic from `WorkflowDetailPage.tsx:45-74`
- Add proper TypeScript types
- Export from `dashboard/src/utils/index.ts`

#### 2.3 Update `workflowsLoader`
**File:** `dashboard/src/loaders/workflows.ts` (UPDATE)
- Import and use `getActiveWorkflow`
- Add `activeDetail` fetching with error handling
- Update return type

#### 2.4 Add loader data type
**File:** `dashboard/src/types/api.ts` (UPDATE)
- Add `WorkflowsLoaderData` interface

#### 2.5 Update `WorkflowsPage.tsx`
**File:** `dashboard/src/pages/WorkflowsPage.tsx` (UPDATE)
- Implement new layout (see Component Structure above)
- Use `useFetcher` for on-demand loading
- Add `ScrollArea` wrappers for bottom grid sections
- Use `Card`, `CardHeader`, `CardContent` for header+canvas section
- Use `Separator` between header and canvas (not `className="border-b"`)

#### 2.6 Update `JobQueue` component
**File:** `dashboard/src/components/JobQueue.tsx` (UPDATE)
- Verify `selectedId` highlighting works
- Ensure `onSelect` is called without navigation

### Phase 3: REFACTOR - Polish

#### 3.1 Styling adjustments
- Canvas area: full width, appropriate height
- Bottom grid: `grid-cols-[1fr_2fr]` for 1/3 + 2/3 split
- Verify ScrollArea styling matches design

#### 3.2 Code cleanup
- Remove any dead code from refactoring
- Ensure consistent imports
- Run `ruff check --fix` and `mypy`

---

## Parallelization Strategy

This plan can be executed by **parallel agents** in batches:

### Batch 0: Prerequisites (1 agent)
Setup tasks that must complete before all others:

| Agent | Task | Files |
|-------|------|-------|
| Pre | Prerequisites 1-3 | `types/api.ts`, create `utils/` directory |

### Batch 1: Parallel (3 agents)
Depends on Batch 0. These tasks have no dependencies on each other.
**Note:** Within each agent, work is SEQUENTIAL (tests first, then implementation), but agents A, B, and D run in PARALLEL with each other.

| Agent | Task | Files |
|-------|------|-------|
| A | 1.1 + 2.1: getActiveWorkflow tests & impl | `utils/workflow.ts`, `utils/__tests__/workflow.test.ts` |
| B | 1.2 + 2.2: buildPipeline tests & impl | `utils/pipeline.ts`, `utils/__tests__/pipeline.test.ts` |
| D | 2.6: JobQueue verification | `components/JobQueue.tsx` |

### Batch 2: Sequential (1 agent)
Depends on Batch 1 completion.
**Note:** Agent C is BLOCKED until Agent A completes (needs `getActiveWorkflow`).

| Agent | Task | Files |
|-------|------|-------|
| C | 1.3 + 2.3 + 2.4: Loader tests & impl | `loaders/workflows.ts`, `types/api.ts` |

### Batch 3: Sequential (1 agent)
Depends on Batch 2 completion:

| Agent | Task | Files |
|-------|------|-------|
| E | 1.4 + 2.5: WorkflowsPage tests & impl | `pages/WorkflowsPage.tsx`, `pages/WorkflowsPage.test.tsx` |

### Batch 4: Final (1 agent)
Depends on all previous:

| Agent | Task | Files |
|-------|------|-------|
| F | 3.1 + 3.2: Styling & cleanup | All modified files |

**Estimated time savings:** ~26% vs sequential execution
> Sequential: ~165 minutes, Parallel: ~122 minutes
> Critical path: Prerequisites (10m) → buildPipeline (30m) → loader (25m) → WorkflowsPage (35m) → styling (15m) = 115m minimum
