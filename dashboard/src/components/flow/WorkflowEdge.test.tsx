import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import { WorkflowEdge } from './WorkflowEdge';

const renderEdge = (props: any) => {
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
    expect(container.querySelector('path')).toBeInTheDocument();
  });

  it.each([
    { status: 'completed' as const, hasDash: false },
    { status: 'pending' as const, hasDash: true },
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

  it('applies dashed style for active edges', () => {
    const activeProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'active' as const },
    };
    const { container } = renderEdge(activeProps);
    const path = container.querySelector('path');
    expect(path).toHaveAttribute('data-status', 'active');
    expect(path).toHaveAttribute('stroke-dasharray');
  });

  it('includes arrow marker on edge end', () => {
    const { container } = renderEdge(baseProps);
    const path = container.querySelector('path');
    expect(path).toHaveAttribute('marker-end');
  });
});
