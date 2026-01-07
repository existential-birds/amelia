import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowCanvas } from './WorkflowCanvas';
import type { EventDrivenPipeline } from '../utils/pipeline';

// Create a mock fitView function we can spy on - use vi.hoisted for proper hoisting
const { mockFitView } = vi.hoisted(() => ({
  mockFitView: vi.fn(),
}));

// Mock ai-elements Canvas - it wraps ReactFlow
vi.mock('./ai-elements/canvas', () => ({
  Canvas: ({ children, nodes }: { children: React.ReactNode; nodes: unknown[] }) => (
    <div data-testid="react-flow" data-node-count={nodes.length}>
      {children}
    </div>
  ),
}));

// Mock useReactFlow for FitViewOnChange component
vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    fitView: mockFitView,
  }),
}));

describe('WorkflowCanvas', () => {
  const emptyPipeline: EventDrivenPipeline = { nodes: [], edges: [] };

  beforeEach(() => {
    mockFitView.mockClear();
  });

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

  it('re-renders with new node count when pipeline changes', () => {
    const initialPipeline: EventDrivenPipeline = {
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

    const { rerender } = render(<WorkflowCanvas pipeline={initialPipeline} />);
    expect(screen.getByTestId('react-flow')).toHaveAttribute('data-node-count', '1');

    // Update pipeline with additional node
    const updatedPipeline: EventDrivenPipeline = {
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

    rerender(<WorkflowCanvas pipeline={updatedPipeline} />);

    // Controlled state: component should immediately reflect the new props
    expect(screen.getByTestId('react-flow')).toHaveAttribute('data-node-count', '2');
  });

  describe('FitViewOnChange', () => {
    it('calls fitView on initial render with nodes', () => {
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

      expect(mockFitView).toHaveBeenCalledWith({ padding: 0.2 });
    });

    it('calls fitView when node count changes', () => {
      const initialPipeline: EventDrivenPipeline = {
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

      const { rerender } = render(<WorkflowCanvas pipeline={initialPipeline} />);

      // Reset mock to track only subsequent calls
      mockFitView.mockClear();

      // Update pipeline with additional node
      const updatedPipeline: EventDrivenPipeline = {
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

      rerender(<WorkflowCanvas pipeline={updatedPipeline} />);

      // fitView should be called again when node count changes
      expect(mockFitView).toHaveBeenCalledWith({ padding: 0.2 });
    });

    it('does not call fitView when only node status changes', () => {
      const initialPipeline: EventDrivenPipeline = {
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

      const { rerender } = render(<WorkflowCanvas pipeline={initialPipeline} />);

      // Reset mock to track only subsequent calls
      mockFitView.mockClear();

      // Update pipeline with same node count but different status
      const updatedPipeline: EventDrivenPipeline = {
        nodes: [
          {
            id: 'architect',
            type: 'agent',
            position: { x: 0, y: 0 },
            data: { agentType: 'architect', status: 'completed', iterations: [], isExpanded: false },
          },
        ],
        edges: [],
      };

      rerender(<WorkflowCanvas pipeline={updatedPipeline} />);

      // fitView should NOT be called when only status changes (same node count)
      expect(mockFitView).not.toHaveBeenCalled();
    });
  });
});
