import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApiModelSelect } from '../ApiModelSelect';
import { useModelsStore } from '@/store/useModelsStore';
import type { ModelInfo } from '../types';

// Mock the store
vi.mock('@/store/useModelsStore');

// Mock useRecentModels hook
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: ['claude-sonnet-4'],
    addRecentModel: vi.fn(),
  }),
}));

describe('ApiModelSelect', () => {
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

  beforeEach(() => {
    vi.clearAllMocks();
    const mockStore = {
      models: mockModels,
      providers: ['anthropic', 'openai'],
      isLoading: false,
      error: null,
      lastFetched: Date.now(),
      fetchModels: vi.fn(),
      refreshModels: vi.fn(),
      getModelsForAgent: vi.fn().mockReturnValue(mockModels),
    };
    // Support both selector pattern and direct call pattern
    vi.mocked(useModelsStore).mockImplementation((selector?: unknown) =>
      typeof selector === 'function' ? selector(mockStore) : mockStore
    );
  });

  it('should render current model value', () => {
    render(
      <ApiModelSelect
        agentKey="architect"
        value="claude-sonnet-4"
        onChange={vi.fn()}
      />
    );

    // When a model is selected, the Select shows the model name from the matching SelectItem
    expect(screen.getByText('Claude Sonnet 4')).toBeInTheDocument();
  });

  it('should render placeholder when no value', () => {
    render(
      <ApiModelSelect
        agentKey="architect"
        value=""
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText(/select model/i)).toBeInTheDocument();
  });

  it('should show recent models in dropdown', () => {
    render(
      <ApiModelSelect
        agentKey="architect"
        value=""
        onChange={vi.fn()}
      />
    );

    // Open dropdown
    fireEvent.click(screen.getByRole('combobox'));

    expect(screen.getByText('Claude Sonnet 4')).toBeInTheDocument();
  });

  it('should call onChange when recent model selected', () => {
    const onChange = vi.fn();
    render(
      <ApiModelSelect
        agentKey="architect"
        value=""
        onChange={onChange}
      />
    );

    // Open dropdown
    fireEvent.click(screen.getByRole('combobox'));

    // Select model
    fireEvent.click(screen.getByText('Claude Sonnet 4'));

    expect(onChange).toHaveBeenCalledWith('claude-sonnet-4');
  });

  it('should render browse all models link', () => {
    render(
      <ApiModelSelect
        agentKey="architect"
        value=""
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText(/browse all models/i)).toBeInTheDocument();
  });

  it('should open sheet when browse link clicked', async () => {
    render(
      <ApiModelSelect
        agentKey="architect"
        value=""
        onChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText(/browse all models/i));

    await waitFor(() => {
      expect(screen.getByText(/select model for architect/i)).toBeInTheDocument();
    });
  });
});
