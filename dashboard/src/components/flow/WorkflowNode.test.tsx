import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import { WorkflowNode } from './WorkflowNode';

const renderNode = (data: any) => {
  return render(
    <ReactFlowProvider>
      <WorkflowNode
        id="test"
        data={data}
        type="workflow"
        selected={false}
        isConnectable={false}
        positionAbsoluteX={0}
        positionAbsoluteY={0}
        zIndex={0}
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
    const { container } = renderNode({ label: 'Developer', status: 'active' });
    expect(container.querySelector('svg.lucide-map-pin')).toBeInTheDocument();
  });

  it('applies active status with pulse animation', () => {
    const { container } = renderNode({ label: 'Developer', status: 'active' });
    expect(container.querySelector('[data-status="active"]')).toBeInTheDocument();
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('applies completed status', () => {
    const { container } = renderNode({ label: 'Architect', status: 'completed' });
    expect(container.querySelector('[data-status="completed"]')).toBeInTheDocument();
  });

  it('applies pending status', () => {
    const { container } = renderNode({ label: 'Reviewer', status: 'pending' });
    expect(container.querySelector('[data-status="pending"]')).toBeInTheDocument();
  });

  it('has proper ARIA label', () => {
    renderNode({ label: 'Architect', subtitle: 'Planning', status: 'completed' });
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      'Workflow stage: Architect - Planning (completed)'
    );
  });

  it('renders connection handles', () => {
    const { container } = renderNode({ label: 'Test', status: 'pending' });
    expect(container.querySelectorAll('.react-flow__handle')).toHaveLength(2);
  });
});
