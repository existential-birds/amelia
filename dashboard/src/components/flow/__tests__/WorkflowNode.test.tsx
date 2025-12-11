/**
 * @fileoverview Tests for WorkflowNode component.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider, type NodeProps } from '@xyflow/react';
import { WorkflowNode, type WorkflowNodeType, type WorkflowNodeData } from '../WorkflowNode';

describe('WorkflowNode', () => {
  const createNodeProps = (
    data: WorkflowNodeData
  ): NodeProps<WorkflowNodeType> => ({
    id: 'test-node',
    type: 'workflow',
    data,
    draggable: true,
    selected: false,
    dragging: false,
    zIndex: 0,
    selectable: true,
    deletable: false,
    isConnectable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  });

  const defaultData: WorkflowNodeData = {
    label: 'Test Task',
    status: 'pending',
  };

  const renderWithProvider = (data: WorkflowNodeData = defaultData) => {
    return render(
      <ReactFlowProvider>
        <WorkflowNode {...createNodeProps(data)} />
      </ReactFlowProvider>
    );
  };

  describe('rendering', () => {
    it('renders the label', () => {
      renderWithProvider();
      expect(screen.getByText('Test Task')).toBeInTheDocument();
    });

    it('renders subtitle when provided', () => {
      renderWithProvider({
        ...defaultData,
        subtitle: 'Task Subtitle',
      });
      expect(screen.getByText('Task Subtitle')).toBeInTheDocument();
    });

    it('renders tokens when provided', () => {
      renderWithProvider({
        ...defaultData,
        tokens: '1.2k',
      });
      expect(screen.getByText('1.2k tokens')).toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('has correct aria-label', () => {
      renderWithProvider();
      const card = screen.getByRole('img');
      expect(card).toHaveAttribute(
        'aria-label',
        'Workflow stage: Test Task (pending)'
      );
    });

    it('includes subtitle in aria-label when provided', () => {
      renderWithProvider({
        ...defaultData,
        subtitle: 'Sub',
      });
      const card = screen.getByRole('img');
      expect(card).toHaveAttribute(
        'aria-label',
        'Workflow stage: Test Task - Sub (pending)'
      );
    });
  });

  describe('status styles', () => {
    it.each([
      ['completed', 'border-status-completed/40'],
      ['active', 'border-primary/60'],
      ['pending', 'border-border'],
      ['blocked', 'border-destructive/40'],
    ] as const)('applies correct border class for %s status', (status, expectedClass) => {
      renderWithProvider({
        ...defaultData,
        status,
      });
      const card = screen.getByTestId('workflow-node-card');
      expect(card).toHaveClass(expectedClass);
    });
  });
});
