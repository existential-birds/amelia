import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import { AgentNode, type AgentNodeType } from './AgentNode';
import type { AgentNodeData } from '../utils/pipeline';

const renderNode = (data: AgentNodeData) => {
  // Provide all required NodeProps for testing
  const props: NodeProps<AgentNodeType> = {
    id: 'test-node',
    data,
    type: 'agent',
    selected: false,
    isConnectable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
    dragging: false,
    draggable: false,
    deletable: false,
    selectable: false,
    parentId: undefined,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    dragHandle: undefined,
    width: 180,
    height: 100,
  };

  return render(
    <ReactFlowProvider>
      <AgentNode {...props} />
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
