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
  describe('display names', () => {
    it.each([
      { agentType: 'architect', displayName: 'Architect' },
      { agentType: 'developer', displayName: 'Developer' },
      { agentType: 'reviewer', displayName: 'Reviewer' },
      { agentType: 'plan_validator', displayName: 'Plan Validator' },
      { agentType: 'human_approval', displayName: 'Human Approval' },
    ])('renders "$displayName" for $agentType', ({ agentType, displayName }) => {
      renderNode({
        agentType,
        status: 'pending',
        iterations: [],
        isExpanded: false,
      });

      expect(screen.getByText(displayName)).toBeInTheDocument();
    });

    it('converts underscores to spaces for unknown agent types', () => {
      renderNode({
        agentType: 'some_unknown_agent',
        status: 'pending',
        iterations: [],
        isExpanded: false,
      });

      expect(screen.getByText('some unknown agent')).toBeInTheDocument();
    });
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

  describe('agent-specific active colors', () => {
    it.each([
      { agentType: 'architect', expectedClass: 'border-agent-architect' },
      { agentType: 'developer', expectedClass: 'border-agent-developer' },
      { agentType: 'reviewer', expectedClass: 'border-agent-reviewer' },
      { agentType: 'plan_validator', expectedClass: 'border-agent-pm' },
      { agentType: 'human_approval', expectedClass: 'border-destructive' },
    ])('applies $expectedClass for active $agentType', ({ agentType, expectedClass }) => {
      const { container } = renderNode({
        agentType,
        status: 'active',
        iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'running' }],
        isExpanded: false,
      });

      const node = container.querySelector('[data-status="active"]');
      expect(node).toHaveClass(expectedClass);
    });

    it('applies default primary color for unknown agent type when active', () => {
      const { container } = renderNode({
        agentType: 'unknown-agent',
        status: 'active',
        iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'running' }],
        isExpanded: false,
      });

      const node = container.querySelector('[data-status="active"]');
      expect(node).toHaveClass('border-primary');
    });
  });

  describe('agent-specific completed colors', () => {
    it.each([
      { agentType: 'architect', expectedClass: 'border-agent-architect/40' },
      { agentType: 'developer', expectedClass: 'border-agent-developer/40' },
      { agentType: 'reviewer', expectedClass: 'border-agent-reviewer/40' },
      { agentType: 'plan_validator', expectedClass: 'border-agent-pm/40' },
      { agentType: 'human_approval', expectedClass: 'border-destructive/40' },
    ])('applies $expectedClass for completed $agentType', ({ agentType, expectedClass }) => {
      const { container } = renderNode({
        agentType,
        status: 'completed',
        iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'completed' }],
        isExpanded: false,
      });

      const node = container.querySelector('[data-status="completed"]');
      expect(node).toHaveClass(expectedClass);
    });

    it('applies default primary color for unknown agent type when completed', () => {
      const { container } = renderNode({
        agentType: 'unknown-agent',
        status: 'completed',
        iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'completed' }],
        isExpanded: false,
      });

      const node = container.querySelector('[data-status="completed"]');
      expect(node).toHaveClass('border-primary/40');
    });
  });

  describe('agent-specific icons', () => {
    it.each([
      { agentType: 'architect', iconTestId: 'compass' },
      { agentType: 'developer', iconTestId: 'code' },
      { agentType: 'reviewer', iconTestId: 'eye' },
      { agentType: 'plan_validator', iconTestId: 'clipboard-check' },
      { agentType: 'human_approval', iconTestId: 'hand' },
    ])('renders $iconTestId icon for $agentType', ({ agentType, iconTestId }) => {
      const { container } = renderNode({
        agentType,
        status: 'pending',
        iterations: [],
        isExpanded: false,
      });

      // Lucide icons render as SVG with class matching the icon name
      const icon = container.querySelector(`svg.lucide-${iconTestId}`);
      expect(icon).toBeInTheDocument();
    });

    it('renders fallback icon for unknown agent type', () => {
      const { container } = renderNode({
        agentType: 'unknown-agent',
        status: 'pending',
        iterations: [],
        isExpanded: false,
      });

      const icon = container.querySelector('svg.lucide-circle-dot');
      expect(icon).toBeInTheDocument();
    });
  });

  describe('agent-specific icon colors when active', () => {
    it.each([
      { agentType: 'architect', expectedClass: 'text-agent-architect' },
      { agentType: 'developer', expectedClass: 'text-agent-developer' },
      { agentType: 'reviewer', expectedClass: 'text-agent-reviewer' },
      { agentType: 'plan_validator', expectedClass: 'text-agent-pm' },
      { agentType: 'human_approval', expectedClass: 'text-destructive' },
    ])('applies $expectedClass to icon for active $agentType', ({ agentType, expectedClass }) => {
      const { container } = renderNode({
        agentType,
        status: 'active',
        iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'running' }],
        isExpanded: false,
      });

      const icon = container.querySelector('svg');
      expect(icon).toHaveClass(expectedClass);
    });

    it('applies default primary color to icon for unknown agent type when active', () => {
      const { container } = renderNode({
        agentType: 'unknown-agent',
        status: 'active',
        iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'running' }],
        isExpanded: false,
      });

      const icon = container.querySelector('svg');
      expect(icon).toHaveClass('text-primary');
    });
  });

  describe('agent-specific icon colors when completed', () => {
    it.each([
      { agentType: 'architect', expectedClass: 'text-agent-architect/70' },
      { agentType: 'developer', expectedClass: 'text-agent-developer/70' },
      { agentType: 'reviewer', expectedClass: 'text-agent-reviewer/70' },
      { agentType: 'plan_validator', expectedClass: 'text-agent-pm/70' },
      { agentType: 'human_approval', expectedClass: 'text-destructive/70' },
    ])('applies $expectedClass to icon for completed $agentType', ({ agentType, expectedClass }) => {
      const { container } = renderNode({
        agentType,
        status: 'completed',
        iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'completed' }],
        isExpanded: false,
      });

      const icon = container.querySelector('svg');
      expect(icon).toHaveClass(expectedClass);
    });

    it('applies default primary color to icon for unknown agent type when completed', () => {
      const { container } = renderNode({
        agentType: 'unknown-agent',
        status: 'completed',
        iterations: [{ id: '1', startedAt: '2026-01-06T10:00:00Z', status: 'completed' }],
        isExpanded: false,
      });

      const icon = container.querySelector('svg');
      expect(icon).toHaveClass('text-primary/70');
    });
  });

});
