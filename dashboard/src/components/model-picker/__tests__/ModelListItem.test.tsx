import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ModelListItem } from '../ModelListItem';
import type { ModelInfo } from '../types';

describe('ModelListItem', () => {
  const mockModel: ModelInfo = {
    id: 'claude-sonnet-4',
    name: 'Claude Sonnet 4',
    provider: 'anthropic',
    capabilities: { tool_call: true, reasoning: true, structured_output: true },
    cost: { input: 3, output: 15 },
    limit: { context: 200000, output: 16000 },
    modalities: { input: ['text', 'image'], output: ['text'] },
    release_date: '2025-05-14',
    knowledge: '2025-04',
  };

  it('should render model name and provider', () => {
    render(<ModelListItem model={mockModel} onSelect={vi.fn()} />);

    expect(screen.getByText('Claude Sonnet 4')).toBeInTheDocument();
    expect(screen.getByText('anthropic')).toBeInTheDocument();
  });

  it('should render context size', () => {
    render(<ModelListItem model={mockModel} onSelect={vi.fn()} />);

    expect(screen.getByText('200K')).toBeInTheDocument();
  });

  it('should render price tier badge', () => {
    render(<ModelListItem model={mockModel} onSelect={vi.fn()} />);

    // $15 output cost = premium tier
    expect(screen.getByText('Premium')).toBeInTheDocument();
  });

  it('should render capability icons', () => {
    render(<ModelListItem model={mockModel} onSelect={vi.fn()} />);

    // Check for capability indicators (using aria-labels)
    expect(screen.getByLabelText('Tool calling')).toBeInTheDocument();
    expect(screen.getByLabelText('Reasoning')).toBeInTheDocument();
    expect(screen.getByLabelText('Structured output')).toBeInTheDocument();
  });

  it('should expand on click to show details', () => {
    render(<ModelListItem model={mockModel} onSelect={vi.fn()} />);

    // Initially collapsed - no pricing visible
    expect(screen.queryByText('$3.00 / 1M')).not.toBeInTheDocument();

    // Click to expand
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));

    // Now shows pricing details
    expect(screen.getByText('$3.00 / 1M')).toBeInTheDocument();
    expect(screen.getByText('$15.00 / 1M')).toBeInTheDocument();
  });

  it('should call onSelect when select button clicked', () => {
    const onSelect = vi.fn();
    render(<ModelListItem model={mockModel} onSelect={onSelect} />);

    // Expand first
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));

    // Click select
    fireEvent.click(screen.getByRole('button', { name: /select/i }));

    expect(onSelect).toHaveBeenCalledWith('claude-sonnet-4');
  });

  it('should show selected state', () => {
    render(<ModelListItem model={mockModel} onSelect={vi.fn()} isSelected />);

    expect(screen.getByRole('button', { name: /expand/i })).toHaveAttribute(
      'data-selected',
      'true'
    );
  });
});
