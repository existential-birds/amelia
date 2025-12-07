import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowEdge } from './WorkflowEdge';

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
    const { container } = render(
      <svg>
        <WorkflowEdge {...baseProps} />
      </svg>
    );
    expect(container.querySelector('path')).toBeInTheDocument();
  });

  it('renders time label', () => {
    render(
      <svg>
        <WorkflowEdge {...baseProps} />
      </svg>
    );
    expect(screen.getByText('0:24')).toBeInTheDocument();
  });

  it('uses solid line for completed status', () => {
    const { container } = render(
      <svg>
        <WorkflowEdge {...baseProps} />
      </svg>
    );
    const path = container.querySelector('path');
    expect(path).toHaveAttribute('data-status', 'completed');
    expect(path).not.toHaveAttribute('stroke-dasharray');
  });

  it('uses dashed line for pending status', () => {
    const pendingProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'pending' as const },
    };
    const { container } = render(
      <svg>
        <WorkflowEdge {...pendingProps} />
      </svg>
    );
    const path = container.querySelector('path');
    expect(path).toHaveAttribute('data-status', 'pending');
    expect(path).toHaveAttribute('stroke-dasharray');
  });

  it('shows animated circle for active edges', () => {
    const activeProps = {
      ...baseProps,
      data: { ...baseProps.data, status: 'active' as const },
    };
    const { container } = render(
      <svg>
        <WorkflowEdge {...activeProps} />
      </svg>
    );
    expect(container.querySelector('circle')).toBeInTheDocument();
  });
});
