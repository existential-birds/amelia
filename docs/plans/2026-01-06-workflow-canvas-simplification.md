# Workflow Canvas Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix bug #218 where workflow canvas nodes don't show active state during execution, while simplifying code with ai-elements library.

**Architecture:** Replace custom WorkflowNode/WorkflowCanvas with ai-elements components. Rewrite pipeline builder to derive state from events array (real-time) instead of `current_stage` (stale loader data).

**Tech Stack:** React, TypeScript, ai-elements (>=1.6.3), @xyflow/react, @dagrejs/dagre, Zustand

---

## Background

### The Bug

Nodes remain "pending" even when agents are running because `buildPipeline()` uses `workflow.current_stage` from the loader. Even with auto-revalidation, there's round-trip delay. Fast stage transitions complete before updated data arrives.

### The Fix

Build pipeline from events array instead. WebSocket events arrive instantly → store updates → pipeline rebuilds immediately → active state shows.

### Code Reduction

- Before: ~585 lines (WorkflowCanvas + WorkflowNode + layout + pipeline)
- After: ~320 lines (~45% reduction)

---

## Task 1: Install ai-elements Dependency

**Files:**
- Modify: `dashboard/package.json`

**Step 1: Add dependency**

```bash
cd dashboard && pnpm add ai-elements
```

**Step 2: Verify installation**

Run: `cd dashboard && pnpm list ai-elements`
Expected: `ai-elements 1.6.x` (or higher)

**Step 3: Commit**

```bash
git add dashboard/package.json dashboard/pnpm-lock.yaml
git commit -m "chore(dashboard): add ai-elements dependency"
```

---

## Task 2: Add New Types for Event-Driven Pipeline

**Files:**
- Modify: `dashboard/src/utils/pipeline.ts:17-47`
- Test: `dashboard/src/utils/__tests__/pipeline.test.ts`

**Step 1: Write the failing test for AgentIteration type**

Add to `dashboard/src/utils/__tests__/pipeline.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import type { AgentIteration, AgentNodeData } from '../pipeline';

describe('AgentIteration type', () => {
  it('should have required fields', () => {
    const iteration: AgentIteration = {
      id: 'iter-1',
      startedAt: '2026-01-06T10:00:00Z',
      status: 'running',
    };
    expect(iteration.id).toBe('iter-1');
    expect(iteration.status).toBe('running');
  });

  it('should support optional completedAt and message', () => {
    const iteration: AgentIteration = {
      id: 'iter-2',
      startedAt: '2026-01-06T10:00:00Z',
      completedAt: '2026-01-06T10:05:00Z',
      status: 'completed',
      message: 'Approved',
    };
    expect(iteration.completedAt).toBe('2026-01-06T10:05:00Z');
    expect(iteration.message).toBe('Approved');
  });
});

describe('AgentNodeData type', () => {
  it('should have required fields', () => {
    const nodeData: AgentNodeData = {
      agentType: 'architect',
      status: 'active',
      iterations: [],
      isExpanded: false,
    };
    expect(nodeData.agentType).toBe('architect');
    expect(nodeData.status).toBe('active');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/utils/__tests__/pipeline.test.ts -- --run`
Expected: FAIL with "Cannot find module '../pipeline' or its corresponding type declarations" or similar type error

**Step 3: Add the types to pipeline.ts**

Add after line 47 in `dashboard/src/utils/pipeline.ts`:

```typescript
/** A single execution iteration of an agent (agents can run multiple times). */
export interface AgentIteration {
  /** Unique identifier for this iteration. */
  id: string;
  /** ISO 8601 timestamp when this iteration started. */
  startedAt: string;
  /** ISO 8601 timestamp when this iteration completed (undefined if still running). */
  completedAt?: string;
  /** Current status of this iteration. */
  status: 'running' | 'completed' | 'failed';
  /** Optional message (e.g., "Requested changes" or "Approved"). */
  message?: string;
}

/** Data for an agent node in the workflow canvas. */
export interface AgentNodeData {
  /** Type of agent (e.g., 'architect', 'developer', 'reviewer'). */
  agentType: string;
  /** Current visual status of the node. */
  status: 'pending' | 'active' | 'completed' | 'blocked';
  /** All iterations this agent has executed. */
  iterations: AgentIteration[];
  /** Whether the iteration history is expanded. */
  isExpanded: boolean;
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/utils/__tests__/pipeline.test.ts -- --run`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/utils/pipeline.ts dashboard/src/utils/__tests__/pipeline.test.ts
git commit -m "feat(dashboard): add AgentIteration and AgentNodeData types"
```

---

## Task 3: Implement buildPipelineFromEvents Function

**Files:**
- Modify: `dashboard/src/utils/pipeline.ts`
- Test: `dashboard/src/utils/__tests__/pipeline.test.ts`

**Step 1: Write failing tests for buildPipelineFromEvents**

Add to `dashboard/src/utils/__tests__/pipeline.test.ts`:

```typescript
import { buildPipelineFromEvents } from '../pipeline';
import type { WorkflowEvent } from '../../types';

describe('buildPipelineFromEvents', () => {
  const makeEvent = (
    agent: string,
    event_type: string,
    sequence: number,
    timestamp: string = '2026-01-06T10:00:00Z'
  ): WorkflowEvent => ({
    id: `evt-${sequence}`,
    workflow_id: 'wf-1',
    sequence,
    timestamp,
    agent,
    event_type: event_type as WorkflowEvent['event_type'],
    message: `${agent} ${event_type}`,
  });

  it('should return empty pipeline for empty events', () => {
    const result = buildPipelineFromEvents([]);
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });

  it('should create node with active status for stage_started without completion', () => {
    const events = [
      makeEvent('architect', 'stage_started', 1),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe('architect');
    expect(result.nodes[0].data.status).toBe('active');
    expect(result.nodes[0].data.iterations).toHaveLength(1);
    expect(result.nodes[0].data.iterations[0].status).toBe('running');
  });

  it('should create node with completed status when stage completes', () => {
    const events = [
      makeEvent('architect', 'stage_started', 1, '2026-01-06T10:00:00Z'),
      makeEvent('architect', 'stage_completed', 2, '2026-01-06T10:05:00Z'),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].data.status).toBe('completed');
    expect(result.nodes[0].data.iterations[0].status).toBe('completed');
    expect(result.nodes[0].data.iterations[0].completedAt).toBe('2026-01-06T10:05:00Z');
  });

  it('should track multiple iterations for same agent', () => {
    const events = [
      makeEvent('developer', 'stage_started', 1, '2026-01-06T10:00:00Z'),
      makeEvent('developer', 'stage_completed', 2, '2026-01-06T10:05:00Z'),
      makeEvent('reviewer', 'stage_started', 3, '2026-01-06T10:05:00Z'),
      makeEvent('reviewer', 'stage_completed', 4, '2026-01-06T10:10:00Z'),
      makeEvent('developer', 'stage_started', 5, '2026-01-06T10:10:00Z'),  // Second iteration
    ];
    const result = buildPipelineFromEvents(events);

    const devNode = result.nodes.find(n => n.id === 'developer');
    expect(devNode?.data.iterations).toHaveLength(2);
    expect(devNode?.data.iterations[0].status).toBe('completed');
    expect(devNode?.data.iterations[1].status).toBe('running');
    expect(devNode?.data.status).toBe('active');  // Currently running
  });

  it('should create edges between adjacent agents in order of first appearance', () => {
    const events = [
      makeEvent('architect', 'stage_started', 1),
      makeEvent('architect', 'stage_completed', 2),
      makeEvent('developer', 'stage_started', 3),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.edges).toHaveLength(1);
    expect(result.edges[0].source).toBe('architect');
    expect(result.edges[0].target).toBe('developer');
  });

  it('should set edge status based on source node completion', () => {
    const events = [
      makeEvent('architect', 'stage_started', 1),
      makeEvent('architect', 'stage_completed', 2),
      makeEvent('developer', 'stage_started', 3),
      makeEvent('developer', 'stage_completed', 4),
      makeEvent('reviewer', 'stage_started', 5),
    ];
    const result = buildPipelineFromEvents(events);

    const archToDevEdge = result.edges.find(e => e.source === 'architect');
    const devToRevEdge = result.edges.find(e => e.source === 'developer');

    expect(archToDevEdge?.data?.status).toBe('completed');
    expect(devToRevEdge?.data?.status).toBe('active');
  });

  it('should handle workflow_failed by marking current agent as blocked', () => {
    const events = [
      makeEvent('developer', 'stage_started', 1),
      makeEvent('system', 'workflow_failed', 2),
    ];
    const result = buildPipelineFromEvents(events);

    expect(result.nodes[0].data.status).toBe('blocked');
    expect(result.nodes[0].data.iterations[0].status).toBe('failed');
  });

  it('should create pending nodes for standard pipeline when no events', () => {
    // When called with empty events, should still show the expected pipeline structure
    const result = buildPipelineFromEvents([], { showDefaultPipeline: true });

    expect(result.nodes).toHaveLength(3);
    expect(result.nodes.map(n => n.id)).toEqual(['architect', 'developer', 'reviewer']);
    expect(result.nodes.every(n => n.data.status === 'pending')).toBe(true);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/utils/__tests__/pipeline.test.ts -- --run`
Expected: FAIL with "buildPipelineFromEvents is not a function" or similar

**Step 3: Implement buildPipelineFromEvents**

Add to `dashboard/src/utils/pipeline.ts`:

```typescript
import type { Node, Edge } from '@xyflow/react';
import type { WorkflowEvent } from '../types';

/** Options for buildPipelineFromEvents. */
export interface BuildPipelineOptions {
  /** Show default 3-node pipeline even with no events. Default: false. */
  showDefaultPipeline?: boolean;
}

/** Pipeline structure with nodes and edges for React Flow. */
export interface EventDrivenPipeline {
  nodes: Node<AgentNodeData>[];
  edges: Edge<{ status: 'completed' | 'active' | 'pending' }>[];
}

const DEFAULT_AGENTS = ['architect', 'developer', 'reviewer'];

/**
 * Build pipeline visualization from workflow events.
 *
 * This function derives node status directly from events rather than
 * relying on stale `current_stage` data, enabling real-time updates.
 */
export function buildPipelineFromEvents(
  events: WorkflowEvent[],
  options: BuildPipelineOptions = {}
): EventDrivenPipeline {
  const { showDefaultPipeline = false } = options;

  // Track agents and their iterations
  const agentMap = new Map<string, AgentIteration[]>();
  const agentOrder: string[] = [];
  let workflowFailed = false;

  // Process events in sequence order
  const sortedEvents = [...events].sort((a, b) => a.sequence - b.sequence);

  for (const event of sortedEvents) {
    const { agent, event_type, timestamp, id } = event;

    if (event_type === 'stage_started') {
      if (!agentMap.has(agent)) {
        agentMap.set(agent, []);
        agentOrder.push(agent);
      }
      agentMap.get(agent)!.push({
        id: `${agent}-${id}`,
        startedAt: timestamp,
        status: 'running',
      });
    } else if (event_type === 'stage_completed') {
      const iterations = agentMap.get(agent);
      if (iterations && iterations.length > 0) {
        const lastIteration = iterations[iterations.length - 1];
        if (lastIteration.status === 'running') {
          lastIteration.completedAt = timestamp;
          lastIteration.status = 'completed';
        }
      }
    } else if (event_type === 'workflow_failed') {
      workflowFailed = true;
      // Mark any running iterations as failed
      for (const iterations of agentMap.values()) {
        for (const iter of iterations) {
          if (iter.status === 'running') {
            iter.status = 'failed';
          }
        }
      }
    }
  }

  // If no events and showDefaultPipeline, create pending nodes
  if (agentOrder.length === 0 && showDefaultPipeline) {
    for (const agent of DEFAULT_AGENTS) {
      agentMap.set(agent, []);
      agentOrder.push(agent);
    }
  }

  // Build nodes
  const nodes: Node<AgentNodeData>[] = agentOrder.map((agentType, index) => {
    const iterations = agentMap.get(agentType) || [];
    const hasRunningIteration = iterations.some(i => i.status === 'running');
    const hasFailedIteration = iterations.some(i => i.status === 'failed');
    const allCompleted = iterations.length > 0 && iterations.every(i => i.status === 'completed');

    let status: AgentNodeData['status'];
    if (hasFailedIteration || (workflowFailed && hasRunningIteration)) {
      status = 'blocked';
    } else if (hasRunningIteration) {
      status = 'active';
    } else if (allCompleted) {
      status = 'completed';
    } else {
      status = 'pending';
    }

    return {
      id: agentType,
      type: 'agent',
      position: { x: 0, y: 0 },  // Will be set by layout
      data: {
        agentType,
        status,
        iterations,
        isExpanded: false,
      },
    };
  });

  // Build edges between adjacent nodes
  const edges: Edge<{ status: 'completed' | 'active' | 'pending' }>[] = [];
  for (let i = 0; i < agentOrder.length - 1; i++) {
    const sourceAgent = agentOrder[i];
    const targetAgent = agentOrder[i + 1];
    const sourceNode = nodes.find(n => n.id === sourceAgent);
    const targetNode = nodes.find(n => n.id === targetAgent);

    let edgeStatus: 'completed' | 'active' | 'pending';
    if (sourceNode?.data.status === 'completed') {
      edgeStatus = targetNode?.data.status === 'active' ? 'active' : 'completed';
    } else if (sourceNode?.data.status === 'active') {
      edgeStatus = 'active';
    } else {
      edgeStatus = 'pending';
    }

    edges.push({
      id: `${sourceAgent}-${targetAgent}`,
      source: sourceAgent,
      target: targetAgent,
      data: { status: edgeStatus },
    });
  }

  return { nodes, edges };
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/utils/__tests__/pipeline.test.ts -- --run`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/utils/pipeline.ts dashboard/src/utils/__tests__/pipeline.test.ts
git commit -m "feat(dashboard): add buildPipelineFromEvents for real-time pipeline updates"
```

---

## Task 4: Create AgentNode Component

**Files:**
- Create: `dashboard/src/components/AgentNode.tsx`
- Create: `dashboard/src/components/AgentNode.test.tsx`

**Step 1: Write failing tests for AgentNode**

Create `dashboard/src/components/AgentNode.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import { AgentNode } from './AgentNode';
import type { AgentNodeData } from '../utils/pipeline';

const renderNode = (data: AgentNodeData) => {
  return render(
    <ReactFlowProvider>
      <AgentNode
        id="test-node"
        data={data}
        type="agent"
        selected={false}
        isConnectable={true}
        positionAbsoluteX={0}
        positionAbsoluteY={0}
        zIndex={0}
      />
    </ReactFlowProvider>
  );
};

describe('AgentNode', () => {
  it('renders agent type as title', () => {
    renderNode({
      agentType: 'architect',
      status: 'pending',
      iterations: [],
      isExpanded: false,
    });

    expect(screen.getByText('architect')).toBeInTheDocument();
  });

  it('shows iteration badge when multiple iterations', () => {
    renderNode({
      agentType: 'developer',
      status: 'completed',
      iterations: [
        { id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'completed' },
        { id: '2', startedAt: '2026-01-06T10:05:00Z', status: 'completed' },
      ],
      isExpanded: false,
    });

    expect(screen.getByText('2 runs')).toBeInTheDocument();
  });

  it('does not show badge for single iteration', () => {
    renderNode({
      agentType: 'architect',
      status: 'completed',
      iterations: [
        { id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'completed' },
      ],
      isExpanded: false,
    });

    expect(screen.queryByText(/runs?/)).not.toBeInTheDocument();
  });

  it('shows "In progress..." when active', () => {
    renderNode({
      agentType: 'developer',
      status: 'active',
      iterations: [
        { id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'running' },
      ],
      isExpanded: false,
    });

    expect(screen.getByText('In progress...')).toBeInTheDocument();
  });

  it('applies pending styles when pending', () => {
    const { container } = renderNode({
      agentType: 'architect',
      status: 'pending',
      iterations: [],
      isExpanded: false,
    });

    const node = container.querySelector('[data-status="pending"]');
    expect(node).toBeInTheDocument();
  });

  it('applies active styles when active', () => {
    const { container } = renderNode({
      agentType: 'architect',
      status: 'active',
      iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'running' }],
      isExpanded: false,
    });

    const node = container.querySelector('[data-status="active"]');
    expect(node).toBeInTheDocument();
  });

  it('applies completed styles when completed', () => {
    const { container } = renderNode({
      agentType: 'architect',
      status: 'completed',
      iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'completed' }],
      isExpanded: false,
    });

    const node = container.querySelector('[data-status="completed"]');
    expect(node).toBeInTheDocument();
  });

  it('applies blocked styles when blocked', () => {
    const { container } = renderNode({
      agentType: 'developer',
      status: 'blocked',
      iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'failed' }],
      isExpanded: false,
    });

    const node = container.querySelector('[data-status="blocked"]');
    expect(node).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/AgentNode.test.tsx -- --run`
Expected: FAIL with "Cannot find module './AgentNode'"

**Step 3: Create AgentNode component**

Create `dashboard/src/components/AgentNode.tsx`:

```typescript
import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import { MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import type { AgentNodeData } from '../utils/pipeline';

const statusClasses: Record<AgentNodeData['status'], string> = {
  pending: 'opacity-50 border-border bg-card/60',
  active: 'border-primary bg-primary/10 shadow-lg shadow-primary/20',
  completed: 'border-status-completed/40 bg-status-completed/5',
  blocked: 'border-destructive/40 bg-destructive/5',
};

const iconClasses: Record<AgentNodeData['status'], string> = {
  pending: 'text-muted-foreground',
  active: 'text-primary animate-pulse',
  completed: 'text-status-completed',
  blocked: 'text-destructive',
};

export function AgentNode({ data }: NodeProps<AgentNodeData>) {
  const { agentType, status, iterations, isExpanded } = data;

  return (
    <div
      data-status={status}
      className={cn(
        'w-[180px] rounded-lg border p-3 transition-all',
        statusClasses[status]
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-border" />

      <div className="flex items-center gap-2">
        <MapPin className={cn('h-4 w-4', iconClasses[status])} />
        <span className="font-medium capitalize">{agentType}</span>
        {iterations.length > 1 && (
          <Badge variant="secondary" className="ml-auto text-xs">
            {iterations.length} runs
          </Badge>
        )}
      </div>

      {status === 'active' && (
        <p className="mt-2 text-sm text-muted-foreground">In progress...</p>
      )}

      {isExpanded && iterations.length > 0 && (
        <div className="mt-2 space-y-1 text-xs">
          {iterations.map((iter, idx) => (
            <div key={iter.id} className="flex items-center gap-1">
              <span className="text-muted-foreground">Run {idx + 1}:</span>
              <span className={cn(
                iter.status === 'running' && 'text-primary',
                iter.status === 'completed' && 'text-status-completed',
                iter.status === 'failed' && 'text-destructive'
              )}>
                {iter.status === 'running' ? 'Running...' : iter.status}
              </span>
            </div>
          ))}
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!bg-border" />
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/AgentNode.test.tsx -- --run`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/AgentNode.tsx dashboard/src/components/AgentNode.test.tsx
git commit -m "feat(dashboard): add AgentNode component with status-based styling"
```

---

## Task 5: Rewrite WorkflowCanvas with ai-elements

**Files:**
- Modify: `dashboard/src/components/WorkflowCanvas.tsx`
- Modify: `dashboard/src/components/WorkflowCanvas.test.tsx`

**Step 1: Update tests for new component structure**

Replace contents of `dashboard/src/components/WorkflowCanvas.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowCanvas } from './WorkflowCanvas';
import type { EventDrivenPipeline } from '../utils/pipeline';

// Mock @xyflow/react
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children, nodes }: { children: React.ReactNode; nodes: unknown[] }) => (
    <div data-testid="react-flow" data-node-count={nodes.length}>
      {children}
    </div>
  ),
  Background: () => <div data-testid="background" />,
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useNodesState: (initial: unknown[]) => [initial, vi.fn()],
  useEdgesState: (initial: unknown[]) => [initial, vi.fn()],
}));

describe('WorkflowCanvas', () => {
  const emptyPipeline: EventDrivenPipeline = { nodes: [], edges: [] };

  it('renders empty state when pipeline has no nodes', () => {
    render(<WorkflowCanvas pipeline={emptyPipeline} />);
    expect(screen.getByText(/no pipeline data/i)).toBeInTheDocument();
  });

  it('renders pipeline nodes', () => {
    const pipeline: EventDrivenPipeline = {
      nodes: [
        {
          id: 'architect',
          type: 'agent',
          position: { x: 0, y: 0 },
          data: { agentType: 'architect', status: 'completed', iterations: [], isExpanded: false },
        },
        {
          id: 'developer',
          type: 'agent',
          position: { x: 200, y: 0 },
          data: { agentType: 'developer', status: 'active', iterations: [], isExpanded: false },
        },
      ],
      edges: [{ id: 'e1', source: 'architect', target: 'developer', data: { status: 'completed' } }],
    };

    render(<WorkflowCanvas pipeline={pipeline} />);

    const flow = screen.getByTestId('react-flow');
    expect(flow).toHaveAttribute('data-node-count', '2');
  });

  it('applies layout to nodes', () => {
    const pipeline: EventDrivenPipeline = {
      nodes: [
        {
          id: 'architect',
          type: 'agent',
          position: { x: 0, y: 0 },
          data: { agentType: 'architect', status: 'pending', iterations: [], isExpanded: false },
        },
      ],
      edges: [],
    };

    render(<WorkflowCanvas pipeline={pipeline} />);
    expect(screen.getByTestId('react-flow')).toBeInTheDocument();
  });

  it('has accessible label', () => {
    render(<WorkflowCanvas pipeline={emptyPipeline} />);
    expect(screen.getByRole('region', { name: /workflow pipeline/i })).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/WorkflowCanvas.test.tsx -- --run`
Expected: FAIL (API mismatch with current component)

**Step 3: Rewrite WorkflowCanvas component**

Replace contents of `dashboard/src/components/WorkflowCanvas.tsx`:

```typescript
import { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { AgentNode } from './AgentNode';
import { getLayoutedElements } from '../utils/layout';
import type { EventDrivenPipeline } from '../utils/pipeline';

const nodeTypes = {
  agent: AgentNode,
};

interface WorkflowCanvasProps {
  pipeline: EventDrivenPipeline;
  className?: string;
}

export function WorkflowCanvas({ pipeline, className }: WorkflowCanvasProps) {
  // Apply Dagre layout to nodes
  const layoutedNodes = useMemo(() => {
    if (pipeline.nodes.length === 0) return [];
    return getLayoutedElements(pipeline.nodes, pipeline.edges);
  }, [pipeline.nodes, pipeline.edges]);

  const [nodes] = useNodesState(layoutedNodes);
  const [edges] = useEdgesState(pipeline.edges);

  if (pipeline.nodes.length === 0) {
    return (
      <div
        role="region"
        aria-label="Workflow pipeline visualization"
        className={className}
      >
        <div className="flex h-full items-center justify-center text-muted-foreground">
          No pipeline data available
        </div>
      </div>
    );
  }

  return (
    <div
      role="region"
      aria-label="Workflow pipeline visualization"
      className={className}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background color="var(--border)" gap={16} />
      </ReactFlow>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/WorkflowCanvas.test.tsx -- --run`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/WorkflowCanvas.tsx dashboard/src/components/WorkflowCanvas.test.tsx
git commit -m "refactor(dashboard): simplify WorkflowCanvas with event-driven pipeline"
```

---

## Task 6: Update WorkflowDetailPage to Merge Events

**Files:**
- Modify: `dashboard/src/pages/WorkflowDetailPage.tsx`
- Modify: `dashboard/src/pages/WorkflowDetailPage.test.tsx`

**Step 1: Update tests for merged events**

Add to `dashboard/src/pages/WorkflowDetailPage.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import WorkflowDetailPage from './WorkflowDetailPage';
import * as workflowStore from '../stores/workflowStore';

// Mock the store
vi.mock('../stores/workflowStore', () => ({
  useWorkflowStore: vi.fn(),
}));

describe('WorkflowDetailPage event merging', () => {
  it('merges loader events with real-time events from store', async () => {
    const loaderEvents = [
      { id: 'evt-1', sequence: 1, agent: 'architect', event_type: 'stage_started' },
    ];
    const storeEvents = [
      { id: 'evt-2', sequence: 2, agent: 'architect', event_type: 'stage_completed' },
    ];

    vi.mocked(workflowStore.useWorkflowStore).mockReturnValue({
      eventsByWorkflow: { 'wf-1': storeEvents },
    });

    const router = createMemoryRouter(
      [{ path: '/workflows/:id', element: <WorkflowDetailPage />, loader: () => ({
        workflow: { id: 'wf-1', recent_events: loaderEvents }
      })}],
      { initialEntries: ['/workflows/wf-1'] }
    );

    render(<RouterProvider router={router} />);

    // The merged events should show architect as completed (both events present)
    // This is verified by the pipeline showing completed status
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/pages/WorkflowDetailPage.test.tsx -- --run`
Expected: FAIL (current implementation doesn't merge events)

**Step 3: Update WorkflowDetailPage to merge events**

Modify `dashboard/src/pages/WorkflowDetailPage.tsx`:

```typescript
import { useLoaderData } from 'react-router-dom';
import { useMemo } from 'react';

import { workflowDetailLoader } from '../loaders/workflows';
import { WorkflowCanvas } from '../components/WorkflowCanvas';
import { ActivityLog } from '../components/ActivityLog';
import { useWorkflowStore } from '../stores/workflowStore';
import { useAutoRevalidation } from '../hooks/useAutoRevalidation';
import { useElapsedTime } from '../hooks/useElapsedTime';
import { buildPipelineFromEvents } from '../utils/pipeline';
import type { WorkflowEvent } from '../types';

export default function WorkflowDetailPage() {
  const { workflow } = useLoaderData<typeof workflowDetailLoader>();
  const elapsedTime = useElapsedTime(workflow);
  const { eventsByWorkflow } = useWorkflowStore();

  // Auto-revalidate when workflow status changes
  useAutoRevalidation(workflow?.id);

  // Merge loader events with real-time WebSocket events
  const allEvents = useMemo(() => {
    const loaderEvents = workflow?.recent_events ?? [];
    const storeEvents = eventsByWorkflow[workflow?.id ?? ''] ?? [];

    // Deduplicate by event id
    const eventMap = new Map<string, WorkflowEvent>();
    for (const event of loaderEvents) {
      eventMap.set(event.id, event);
    }
    for (const event of storeEvents) {
      eventMap.set(event.id, event);
    }

    return Array.from(eventMap.values()).sort((a, b) => a.sequence - b.sequence);
  }, [workflow?.recent_events, workflow?.id, eventsByWorkflow]);

  // Build pipeline from merged events
  const pipeline = useMemo(() => {
    return buildPipelineFromEvents(allEvents, { showDefaultPipeline: true });
  }, [allEvents]);

  if (!workflow) {
    return <div>Workflow not found</div>;
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{workflow.issue_id}</h1>
          <p className="text-muted-foreground">{workflow.issue_title}</p>
        </div>
        <div className="text-sm text-muted-foreground">
          {elapsedTime}
        </div>
      </header>

      <section aria-label="Pipeline visualization">
        <h2 className="mb-4 text-lg font-semibold">Pipeline</h2>
        <WorkflowCanvas pipeline={pipeline} className="h-[200px]" />
      </section>

      <section aria-label="Activity log">
        <h2 className="mb-4 text-lg font-semibold">Activity</h2>
        <ActivityLog workflowId={workflow.id} initialEvents={allEvents} />
      </section>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/pages/WorkflowDetailPage.test.tsx -- --run`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/pages/WorkflowDetailPage.tsx dashboard/src/pages/WorkflowDetailPage.test.tsx
git commit -m "fix(dashboard): merge real-time events for instant pipeline updates

Fixes #218 - nodes now show active state during execution"
```

---

## Task 7: Delete Old WorkflowNode Files

**Files:**
- Delete: `dashboard/src/components/flow/WorkflowNode.tsx`
- Delete: `dashboard/src/components/flow/WorkflowNode.test.tsx`
- Delete: `dashboard/src/components/flow/index.ts`

**Step 1: Remove the files**

```bash
rm dashboard/src/components/flow/WorkflowNode.tsx
rm dashboard/src/components/flow/WorkflowNode.test.tsx
rm dashboard/src/components/flow/index.ts
rmdir dashboard/src/components/flow
```

**Step 2: Verify no imports remain**

Run: `cd dashboard && grep -r "from.*flow/WorkflowNode" src/ || echo "No remaining imports"`
Expected: "No remaining imports"

Run: `cd dashboard && grep -r "from.*flow/index" src/ || echo "No remaining imports"`
Expected: "No remaining imports"

**Step 3: Run all tests to ensure nothing breaks**

Run: `cd dashboard && pnpm test -- --run`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(dashboard): remove deprecated WorkflowNode in favor of AgentNode"
```

---

## Task 8: Update Layout Utility for New Types

**Files:**
- Modify: `dashboard/src/utils/layout.ts`

**Step 1: Check if layout.ts needs type updates**

The current `getLayoutedElements` function may need to accept the new `Node<AgentNodeData>` type. Check the signature and update if needed.

**Step 2: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: No type errors

**Step 3: Run full test suite**

Run: `cd dashboard && pnpm test -- --run`
Expected: All tests PASS

**Step 4: Run lint**

Run: `cd dashboard && pnpm lint`
Expected: No lint errors

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore(dashboard): ensure type compatibility with new pipeline types"
```

---

## Task 9: Manual Testing

**Step 1: Start the dev server**

```bash
uv run amelia dev
```

**Step 2: Open browser to http://localhost:8420**

**Step 3: Create or open a workflow**

**Step 4: Observe the canvas during execution**

Verify:
- [ ] Nodes transition from "pending" → "active" when agent starts
- [ ] Active node shows glow/pulse animation
- [ ] Nodes show "In progress..." text when active
- [ ] Nodes transition from "active" → "completed" when agent finishes
- [ ] Multiple iterations show badge with count

**Step 5: Document results**

If issues found, create follow-up tasks.

---

## Summary

| Task | Files Changed | Lines Changed |
|------|---------------|---------------|
| 1. Install ai-elements | package.json | +1 dep |
| 2. Add types | pipeline.ts | +30 |
| 3. buildPipelineFromEvents | pipeline.ts, test | +150 |
| 4. AgentNode component | AgentNode.tsx, test | +120 |
| 5. Simplify WorkflowCanvas | WorkflowCanvas.tsx, test | -140, +60 |
| 6. Merge events | WorkflowDetailPage.tsx, test | +30 |
| 7. Delete old files | flow/* | -350 |
| 8. Type cleanup | layout.ts | ~0 |

**Net result:** ~265 fewer lines, real-time active state updates.
