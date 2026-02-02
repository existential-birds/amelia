import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ModelList } from '../ModelList';
import type { ModelInfo } from '../types';

describe('ModelList', () => {
  const mockModels: ModelInfo[] = [
    {
      id: 'claude-sonnet-4',
      name: 'Claude Sonnet 4',
      provider: 'anthropic',
      capabilities: { tool_call: true, reasoning: true, structured_output: true },
      cost: { input: 3, output: 15 },
      limit: { context: 200000, output: 16000 },
      modalities: { input: ['text'], output: ['text'] },
    },
    {
      id: 'gpt-4o',
      name: 'GPT-4o',
      provider: 'openai',
      capabilities: { tool_call: true, reasoning: false, structured_output: true },
      cost: { input: 2.5, output: 10 },
      limit: { context: 128000, output: 16384 },
      modalities: { input: ['text'], output: ['text'] },
    },
  ];

  it('should render all models', () => {
    render(
      <ModelList
        models={mockModels}
        recentModelIds={[]}
        onSelect={vi.fn()}
        selectedModelId={null}
      />
    );

    expect(screen.getByText('Claude Sonnet 4')).toBeInTheDocument();
    expect(screen.getByText('GPT-4o')).toBeInTheDocument();
  });

  it('should show recent models section when recent IDs provided', () => {
    render(
      <ModelList
        models={mockModels}
        recentModelIds={['claude-sonnet-4']}
        onSelect={vi.fn()}
        selectedModelId={null}
      />
    );

    expect(screen.getByText('Recent')).toBeInTheDocument();
  });

  it('should not duplicate models in Recent and All Models sections', () => {
    render(
      <ModelList
        models={mockModels}
        recentModelIds={['claude-sonnet-4']}
        onSelect={vi.fn()}
        selectedModelId={null}
      />
    );

    // Model should only appear once (in Recent section, not in All Models)
    const sonnetItems = screen.getAllByText('Claude Sonnet 4');
    expect(sonnetItems).toHaveLength(1);
  });

  it('should not show recent models section when empty', () => {
    render(
      <ModelList
        models={mockModels}
        recentModelIds={[]}
        onSelect={vi.fn()}
        selectedModelId={null}
      />
    );

    expect(screen.queryByText('Recent')).not.toBeInTheDocument();
  });

  it('should show empty state when no models match', () => {
    render(
      <ModelList
        models={[]}
        recentModelIds={[]}
        onSelect={vi.fn()}
        selectedModelId={null}
      />
    );

    expect(screen.getByText(/no models match/i)).toBeInTheDocument();
  });

  it('should show loading state', () => {
    render(
      <ModelList
        models={[]}
        recentModelIds={[]}
        onSelect={vi.fn()}
        selectedModelId={null}
        isLoading
      />
    );

    expect(screen.getAllByTestId('model-skeleton')).toHaveLength(5);
  });

  it('should show error state', () => {
    render(
      <ModelList
        models={[]}
        recentModelIds={[]}
        onSelect={vi.fn()}
        selectedModelId={null}
        error="Failed to load models"
        onRetry={vi.fn()}
      />
    );

    expect(screen.getByText(/failed to load models/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
