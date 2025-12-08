import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowCanvas } from './WorkflowCanvas';

describe('WorkflowCanvas', () => {
  const mockPipeline = {
    nodes: [
      { id: 'issue', label: 'Issue', status: 'completed' as const },
      { id: 'architect', label: 'Architect', subtitle: 'Planning', status: 'completed' as const, tokens: '12.4k' },
      { id: 'developer', label: 'Developer', subtitle: 'Implementation', status: 'active' as const, tokens: '48.2k' },
    ],
    edges: [
      { from: 'issue', to: 'architect', label: '0:08', status: 'completed' as const },
      { from: 'architect', to: 'developer', label: '0:24', status: 'active' as const },
    ],
  };

  it('renders empty state when no pipeline provided', () => {
    render(<WorkflowCanvas />);
    expect(screen.getByText('Select a workflow to view pipeline')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'No workflow selected');
  });

  it('renders loading state when isLoading is true', () => {
    render(<WorkflowCanvas isLoading={true} />);
    expect(screen.getByText('Loading pipeline...')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Loading pipeline');
  });

  it('renders pipeline nodes when data provided', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    expect(screen.getByText('Issue')).toBeInTheDocument();
    expect(screen.getByText('Architect')).toBeInTheDocument();
    expect(screen.getByText('Developer')).toBeInTheDocument();
  });

  it('has proper ARIA label for active pipeline', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    const canvas = screen.getByRole('img');
    expect(canvas.getAttribute('aria-label')).toContain('pipeline');
  });
});
