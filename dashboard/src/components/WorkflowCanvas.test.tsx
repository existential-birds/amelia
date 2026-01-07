import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowCanvas } from './WorkflowCanvas';
import type { EventDrivenPipeline } from '../utils/pipeline';

// Mock @xyflow/react - simplified since component uses controlled state
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children, nodes }: { children: React.ReactNode; nodes: unknown[] }) => (
    <div data-testid="react-flow" data-node-count={nodes.length}>
      {children}
    </div>
  ),
  Background: () => <div data-testid="background" />,
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
});
