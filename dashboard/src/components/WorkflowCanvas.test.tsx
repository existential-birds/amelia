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
  });

  it('renders loading state when isLoading is true', () => {
    render(<WorkflowCanvas isLoading={true} />);
    expect(screen.getByText('Loading pipeline...')).toBeInTheDocument();
  });

  it('renders pipeline nodes when data provided', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    expect(screen.getByText('Issue')).toBeInTheDocument();
    expect(screen.getByText('Architect')).toBeInTheDocument();
    expect(screen.getByText('Developer')).toBeInTheDocument();
  });

  it('has proper ARIA label for active pipeline', () => {
    render(<WorkflowCanvas pipeline={mockPipeline} />);
    const canvas = screen.getByRole('img', { name: /pipeline/i });
    expect(canvas.getAttribute('aria-label')).toContain('pipeline');
    expect(canvas.getAttribute('aria-label')).toContain('3 stages');
    expect(canvas.getAttribute('aria-label')).toContain('Developer');
  });

  describe('zoom configuration', () => {
    it('renders large pipelines with many nodes', () => {
      const largePipeline = {
        nodes: Array.from({ length: 10 }, (_, i) => ({
          id: `task-${i}`,
          label: `Task ${i}`,
          status: 'pending' as const,
        })),
        edges: Array.from({ length: 9 }, (_, i) => ({
          from: `task-${i}`,
          to: `task-${i + 1}`,
          label: '',
          status: 'pending' as const,
        })),
      };

      render(<WorkflowCanvas pipeline={largePipeline} />);

      // All 10 nodes should render (fitView with low minZoom allows this)
      for (let i = 0; i < 10; i++) {
        expect(screen.getByText(`Task ${i}`)).toBeInTheDocument();
      }
    });
  });
});
