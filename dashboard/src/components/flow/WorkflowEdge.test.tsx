import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ReactFlowProvider, type EdgeProps } from '@xyflow/react';
import { WorkflowEdge, type WorkflowEdgeType } from './WorkflowEdge';

const renderEdge = (props: Partial<EdgeProps<WorkflowEdgeType>>) => {
  return render(
    <ReactFlowProvider>
      <svg>
        <WorkflowEdge {...props} />
      </svg>
    </ReactFlowProvider>
  );
};

describe('WorkflowEdge', () => {
  const baseProps = {
    id: 'e1-2',
    source: 'node1',
    target: 'node2',
    sourceX: 100,
    sourceY: 100,
    targetX: 200,
    targetY: 100,
    sourcePosition: 'right' as const,
    targetPosition: 'left' as const,
    data: { label: '0:24', status: 'completed' as const },
  };

  it('renders edge path', () => {
    const { container } = renderEdge(baseProps);
    // SVG paths don't have semantic roles, querySelector is appropriate here
    const path = container.querySelector('path');
    expect(path).toBeInTheDocument();
  });

  it.each([
    { status: 'completed' as const, hasDash: false },
    { status: 'pending' as const, hasDash: true },
    { status: 'active' as const, hasDash: true },
  ])('applies $status line style (dashed: $hasDash)', ({ status, hasDash }) => {
    const props = { ...baseProps, data: { ...baseProps.data, status } };
    const { container } = renderEdge(props);
    const path = container.querySelector('path');
    expect(path).toHaveAttribute('data-status', status);
    if (hasDash) {
      expect(path).toHaveAttribute('stroke-dasharray');
    } else {
      expect(path).not.toHaveAttribute('stroke-dasharray');
    }
  });

});
