# Simplify React Flow Workflow Canvas Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce custom React Flow code by leveraging built-in behaviors, switching to horizontal layout while preserving our aviation color palette.

**Architecture:** Replace custom WorkflowEdge with built-in smoothstep edges styled via props. Update layout to horizontal (LTR). Remove redundant ReactFlow props that match defaults. Keep custom WorkflowNode for status-based styling.

**Tech Stack:** React Flow (@xyflow/react), TypeScript, Vitest, Tailwind CSS v4

---

## Task 1: Update Layout to Horizontal

**Files:**
- Modify: `dashboard/src/utils/layout.ts:23-31`
- Modify: `dashboard/src/utils/layout.test.ts`

**Step 1: Update the failing test for horizontal layout**

```typescript
// dashboard/src/utils/layout.test.ts
import { describe, it, expect } from 'vitest';
import { getLayoutedElements } from './layout';
import type { WorkflowNodeType } from '@/components/flow/WorkflowNode';
import type { WorkflowEdgeType } from '@/components/flow/WorkflowEdge';

describe('getLayoutedElements', () => {
  const mockNodes: WorkflowNodeType[] = [
    { id: '1', type: 'workflow', position: { x: 0, y: 0 }, data: { label: 'A', status: 'completed' } },
    { id: '2', type: 'workflow', position: { x: 0, y: 0 }, data: { label: 'B', status: 'active' } },
    { id: '3', type: 'workflow', position: { x: 0, y: 0 }, data: { label: 'C', status: 'pending' } },
  ];
  const mockEdges: WorkflowEdgeType[] = [];

  it('positions nodes horizontally with consistent spacing', () => {
    const result = getLayoutedElements(mockNodes, mockEdges);

    // All nodes should be on the same Y coordinate (horizontal layout)
    expect(result[0].position.y).toBe(0);
    expect(result[1].position.y).toBe(0);
    expect(result[2].position.y).toBe(0);

    // X coordinates should increase with spacing
    expect(result[0].position.x).toBe(0);
    expect(result[1].position.x).toBe(200);
    expect(result[2].position.x).toBe(400);
  });

  it('returns empty array for empty input', () => {
    const result = getLayoutedElements([], []);
    expect(result).toEqual([]);
  });

  it('preserves node data and type', () => {
    const result = getLayoutedElements(mockNodes, mockEdges);
    expect(result[0].data.label).toBe('A');
    expect(result[0].type).toBe('workflow');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/utils/layout.test.ts`
Expected: FAIL - nodes currently positioned vertically (y varies, x is 0)

**Step 3: Update layout implementation for horizontal positioning**

```typescript
// dashboard/src/utils/layout.ts
/**
 * @fileoverview Simple layout utility for workflow visualization.
 *
 * Uses React Flow's default behavior - nodes are positioned sequentially.
 */
import type { WorkflowNodeType } from '@/components/flow/WorkflowNode';
import type { WorkflowEdgeType } from '@/components/flow/WorkflowEdge';

/** Spacing between nodes. */
const NODE_SPACING = 200;

/**
 * Positions nodes sequentially for React Flow.
 *
 * Places nodes in a horizontal row with consistent spacing.
 * React Flow's fitView will scale and center the result.
 *
 * @param nodes - React Flow nodes to layout
 * @param _edges - Edges (unused, kept for API compatibility)
 * @returns Nodes with updated positions
 */
export function getLayoutedElements(
  nodes: WorkflowNodeType[],
  _edges: WorkflowEdgeType[]
): WorkflowNodeType[] {
  return nodes.map((node, index) => ({
    ...node,
    position: { x: index * NODE_SPACING, y: 0 },
  }));
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test:run src/utils/layout.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/utils/layout.ts dashboard/src/utils/layout.test.ts
git commit -m "feat(flow): switch to horizontal layout for workflow canvas"
```

---

## Task 2: Update Handle Positions for Horizontal Flow

**Files:**
- Modify: `dashboard/src/components/flow/WorkflowNode.tsx:135-136`
- Modify: `dashboard/src/components/flow/WorkflowNode.test.tsx`

**Step 1: Update test expectations for horizontal handles**

Add this test case to `dashboard/src/components/flow/WorkflowNode.test.tsx`:

```typescript
// Add to the describe block in WorkflowNode.test.tsx
it('positions handles for horizontal flow (left target, right source)', () => {
  renderNode({ label: 'Test', status: 'pending' });

  const handles = document.querySelectorAll('.react-flow__handle');
  expect(handles.length).toBe(2);

  // Check for left/right positioning classes
  const targetHandle = document.querySelector('.react-flow__handle-left');
  const sourceHandle = document.querySelector('.react-flow__handle-right');
  expect(targetHandle).toBeInTheDocument();
  expect(sourceHandle).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/components/flow/WorkflowNode.test.tsx`
Expected: FAIL - handles currently use top/bottom positions

**Step 3: Update Handle positions to Left/Right**

In `dashboard/src/components/flow/WorkflowNode.tsx`, change lines 135-136:

```typescript
// Before:
<Handle type="target" position={Position.Top} />
<Handle type="source" position={Position.Bottom} />

// After:
<Handle type="target" position={Position.Left} />
<Handle type="source" position={Position.Right} />
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test:run src/components/flow/WorkflowNode.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/flow/WorkflowNode.tsx dashboard/src/components/flow/WorkflowNode.test.tsx
git commit -m "feat(flow): update handle positions for horizontal layout"
```

---

## Task 3: Replace Custom Edge with Built-in smoothstep

**Files:**
- Modify: `dashboard/src/components/WorkflowCanvas.tsx`
- Delete: `dashboard/src/components/flow/WorkflowEdge.tsx`
- Delete: `dashboard/src/components/flow/WorkflowEdge.test.tsx`

**Step 1: Update WorkflowCanvas to use built-in edge styling**

Replace the edge creation and remove custom edge type in `dashboard/src/components/WorkflowCanvas.tsx`:

```typescript
/**
 * @fileoverview React Flow canvas for visualizing workflow pipelines.
 */
import { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  type NodeTypes,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { GitBranch, Loader2 } from 'lucide-react';
import { WorkflowNode, type WorkflowNodeType } from '@/components/flow/WorkflowNode';
import { cn } from '@/lib/utils';
import type { Pipeline } from '@/utils/pipeline';
import { getLayoutedElements } from '@/utils/layout';

/**
 * Props for the WorkflowCanvas component.
 * @property pipeline - Pipeline data to visualize (optional)
 * @property isLoading - Whether the pipeline is loading
 * @property className - Optional additional CSS classes
 */
interface WorkflowCanvasProps {
  pipeline?: Pipeline;
  isLoading?: boolean;
  className?: string;
}

/** Custom node types for React Flow. */
const nodeTypes: NodeTypes = {
  workflow: WorkflowNode,
};

/** Maps edge status to stroke color CSS variable. */
const edgeColors: Record<string, string> = {
  completed: 'var(--status-completed)',
  active: 'var(--primary)',
  pending: 'var(--muted-foreground)',
};

/**
 * Visualizes a workflow pipeline using React Flow.
 *
 * Converts pipeline data to React Flow format and renders nodes
 * and edges in a non-interactive view. Shows stage progress indicator.
 *
 * Displays three states:
 * 1. Empty state: No pipeline provided
 * 2. Loading state: Pipeline is loading
 * 3. Active state: Pipeline data is available
 *
 * @param props - Component props
 * @returns The workflow canvas visualization
 *
 * @example
 * ```tsx
 * <WorkflowCanvas
 *   pipeline={{
 *     nodes: [{ id: '1', label: 'Plan', status: 'completed' }],
 *     edges: [{ from: '1', to: '2', label: 'approve', status: 'active' }]
 *   }}
 * />
 * ```
 */
export function WorkflowCanvas({ pipeline, isLoading = false, className }: WorkflowCanvasProps) {
  // Create nodes without positions first
  const rawNodes: WorkflowNodeType[] = useMemo(
    () =>
      pipeline?.nodes.map((node) => ({
        id: node.id,
        type: 'workflow' as const,
        position: { x: 0, y: 0 }, // Will be set by layout
        data: {
          label: node.label,
          subtitle: node.subtitle,
          status: node.status,
          tokens: node.tokens,
        },
      })) ?? [],
    [pipeline?.nodes]
  );

  // Create edges with built-in smoothstep type and status-based styling
  const edges: Edge[] = useMemo(
    () =>
      pipeline?.edges.map((edge) => {
        const status = edge.status;
        const strokeColor = edgeColors[status] || edgeColors.pending;

        return {
          id: `e-${edge.from}-${edge.to}`,
          source: edge.from,
          target: edge.to,
          type: 'smoothstep',
          animated: status === 'active',
          label: edge.label || undefined,
          style: {
            stroke: strokeColor,
            strokeWidth: 2.5,
            strokeDasharray: status !== 'completed' ? '8 4' : undefined,
            opacity: status === 'pending' ? 0.6 : 1,
          },
          labelStyle: {
            fill: strokeColor,
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
          },
          labelBgStyle: {
            fill: 'var(--background)',
            stroke: 'var(--border)',
          },
        };
      }) ?? [],
    [pipeline?.edges]
  );

  // Apply layout to position nodes
  const nodes = useMemo(
    () => getLayoutedElements(rawNodes, []),
    [rawNodes]
  );

  const currentStage = pipeline?.nodes.find((n) => n.status === 'active')?.label || 'Unknown';

  // Empty state - no pipeline selected
  if (!pipeline && !isLoading) {
    return (
      <div
        role="status"
        aria-label="No workflow selected"
        data-slot="workflow-canvas"
        className={cn('h-64 bg-linear-to-b from-card/40 to-background/40 relative overflow-hidden', className)}
        style={{
          backgroundImage: 'radial-gradient(circle, var(--muted-foreground) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          backgroundPosition: '0 0',
          opacity: 0.1,
        }}
      >
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3" style={{ opacity: 1 }}>
          <GitBranch className="h-12 w-12 text-muted-foreground/40" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">Select a workflow to view pipeline</p>
        </div>
      </div>
    );
  }

  // Loading state - workflow selected but loading
  if (isLoading || !pipeline) {
    return (
      <div
        role="status"
        aria-label="Loading pipeline"
        data-slot="workflow-canvas"
        className={cn('h-64 bg-linear-to-b from-card/40 to-background/40 relative overflow-hidden', className)}
        style={{
          backgroundImage: 'radial-gradient(circle, var(--muted-foreground) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          backgroundPosition: '0 0',
          opacity: 0.1,
        }}
      >
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3" style={{ opacity: 1 }}>
          <Loader2 className="h-8 w-8 text-muted-foreground/60 animate-spin" strokeWidth={2} />
          <p className="text-sm text-muted-foreground">Loading pipeline...</p>
        </div>
      </div>
    );
  }

  // Active state - pipeline data is guaranteed defined after above guards
  const nodeCount = pipeline.nodes.length;
  return (
    <div
      role="img"
      aria-label={`Workflow pipeline with ${nodeCount} stages. Current stage: ${currentStage}`}
      data-slot="workflow-canvas"
      className={cn('h-80 py-4 bg-linear-to-b from-card/40 to-background/40 relative', className)}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15, maxZoom: 1.5, minZoom: 0.1 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        className="workflow-canvas"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--muted-foreground)"
          style={{ opacity: 0.1 }}
        />
        <Controls
          showZoom={true}
          showFitView={true}
          showInteractive={false}
          position="bottom-right"
          aria-label="Workflow canvas zoom controls"
        />
        <MiniMap
          nodeColor={(node) => {
            const status = node.data?.status;
            if (status === 'completed') return 'var(--status-completed)';
            if (status === 'active') return 'var(--primary)';
            if (status === 'blocked') return 'var(--destructive)';
            return 'var(--muted-foreground)';
          }}
          maskColor="rgba(0, 0, 0, 0.1)"
          style={{
            backgroundColor: 'var(--background)',
            border: '1px solid var(--border)',
          }}
          pannable
          zoomable
          aria-label="Workflow minimap for navigation"
        />
      </ReactFlow>
    </div>
  );
}
```

**Step 2: Run tests to verify canvas still works**

Run: `cd dashboard && pnpm test:run`
Expected: All tests pass (edge tests will be deleted next)

**Step 3: Delete custom edge files**

```bash
rm dashboard/src/components/flow/WorkflowEdge.tsx
rm dashboard/src/components/flow/WorkflowEdge.test.tsx
```

**Step 4: Update layout.ts import (remove unused edge type)**

In `dashboard/src/utils/layout.ts`, update import:

```typescript
// Before:
import type { WorkflowEdgeType } from '@/components/flow/WorkflowEdge';

// After:
import type { Edge } from '@xyflow/react';
```

And update function signature:

```typescript
export function getLayoutedElements(
  nodes: WorkflowNodeType[],
  _edges: Edge[]
): WorkflowNodeType[] {
```

**Step 5: Update layout.test.ts import**

```typescript
// Before:
import type { WorkflowEdgeType } from '@/components/flow/WorkflowEdge';

// After:
import type { Edge } from '@xyflow/react';

// And update:
const mockEdges: Edge[] = [];
```

**Step 6: Run all tests**

Run: `cd dashboard && pnpm test:run`
Expected: PASS (fewer tests now, but all passing)

**Step 7: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor(flow): replace custom edge with built-in smoothstep

- Delete WorkflowEdge.tsx and WorkflowEdge.test.tsx
- Use React Flow's built-in smoothstep edge type
- Apply status-based styling via edge style props
- Remove edgeTypes from WorkflowCanvas
- Update layout.ts to use generic Edge type

BREAKING CHANGE: WorkflowEdgeType export removed"
```

---

## Task 4: Visual Verification

**Files:**
- None (manual testing)

**Step 1: Start dev server**

Run: `cd dashboard && pnpm dev`

**Step 2: Verify horizontal layout**

- Open browser to http://localhost:8421
- Navigate to a workflow with multiple stages
- Verify nodes flow left-to-right horizontally
- Verify edges connect horizontally between nodes

**Step 3: Verify edge styling**

- Completed edges: solid line, green color
- Active edges: dashed line with animation, gold color
- Pending edges: dashed line, muted color with opacity

**Step 4: Verify fitView**

- Canvas should auto-fit to show all nodes
- Zoom controls should work
- MiniMap should show correct node colors

**Step 5: Document any issues**

If visual issues found, create follow-up tasks.

---

## Summary

| Task | Description | Lines Changed |
|------|-------------|---------------|
| 1 | Horizontal layout | ~5 |
| 2 | Handle positions | ~4 |
| 3 | Replace custom edge | -153, +50 |
| 4 | Visual verification | 0 |

**Total reduction:** ~100 lines of custom code removed.
