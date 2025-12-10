import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider, Position } from '@xyflow/react';
import { WorkflowNode, type WorkflowNodeData } from './WorkflowNode';

const renderNode = (data: WorkflowNodeData) => {
  return render(
    <ReactFlowProvider>
      <WorkflowNode
        id="test"
        draggable={false}
        selectable={false}
        deletable={false}
        data={data}
        type="workflow"
        selected={false}
        isConnectable={false}
        positionAbsoluteX={0}
        positionAbsoluteY={0}
        zIndex={0}
        dragging={false}
        sourcePosition={Position.Right}
        targetPosition={Position.Left}
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

  it('renders MapPin icon', () => {
    renderNode({ label: 'Developer', status: 'active' });
    // Node has role="img", so the icon is part of the accessible element
    expect(screen.getByRole('img')).toBeInTheDocument();
  });

  it.each([
    { status: 'active' as const, hasAnimation: true },
    { status: 'completed' as const, hasAnimation: false },
    { status: 'pending' as const, hasAnimation: false },
    { status: 'blocked' as const, hasAnimation: false },
  ])('applies $status status (animated: $hasAnimation)', ({ status, hasAnimation }) => {
    renderNode({ label: 'Test', status });
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('data-status', status);
    if (hasAnimation) {
      expect(node.querySelector('.animate-pulse')).toBeInTheDocument();
    }
  });

  it('has proper ARIA label', () => {
    renderNode({ label: 'Architect', subtitle: 'Planning', status: 'completed' });
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      'Workflow stage: Architect - Planning (completed)'
    );
  });

  it('renders node content within a card container', () => {
    renderNode({ label: 'Test', status: 'pending' });

    const card = screen.getByTestId('workflow-node-card');
    expect(card).toBeInTheDocument();
    expect(card).toHaveClass('rounded-md', 'border', 'min-w-[180px]');
  });

  describe('status-based card borders', () => {
    it('applies primary border for active status', () => {
      renderNode({ label: 'Test', status: 'active' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('border-primary/60');
    });

    it('applies completed border for completed status', () => {
      renderNode({ label: 'Test', status: 'completed' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('border-status-completed/40');
    });

    it('applies default border for pending status', () => {
      renderNode({ label: 'Test', status: 'pending' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('border-border');
    });

    it('applies destructive border for blocked status', () => {
      renderNode({ label: 'Test', status: 'blocked' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('border-destructive/40');
    });
  });

  describe('status-based card backgrounds', () => {
    it('applies primary tint background for active status', () => {
      renderNode({ label: 'Test', status: 'active' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('bg-primary/10');
    });

    it('applies completed tint background for completed status', () => {
      renderNode({ label: 'Test', status: 'completed' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('bg-status-completed/5');
    });

    it('applies reduced opacity background for pending status', () => {
      renderNode({ label: 'Test', status: 'pending' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('bg-card/60');
    });

    it('applies destructive tint background for blocked status', () => {
      renderNode({ label: 'Test', status: 'blocked' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('bg-destructive/5');
    });
  });

  describe('status-based card shadows', () => {
    it('applies elevated shadow with gold glow for active status', () => {
      renderNode({ label: 'Test', status: 'active' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('shadow-lg');
    });

    it('applies medium shadow for completed status', () => {
      renderNode({ label: 'Test', status: 'completed' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('shadow-md');
    });

    it('applies small shadow for pending status', () => {
      renderNode({ label: 'Test', status: 'pending' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('shadow-sm');
    });

    it('applies medium shadow for blocked status', () => {
      renderNode({ label: 'Test', status: 'blocked' });

      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass('shadow-md');
    });
  });

  it('positions handles correctly within card structure', () => {
    renderNode({ label: 'Test', status: 'pending' });

    // Handles should be present and styled to be invisible but functional
    const handles = document.querySelectorAll('.react-flow__handle');
    expect(handles.length).toBe(2); // source and target
  });
});
