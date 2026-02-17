import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApiModelSelect } from '../ApiModelSelect';
import { useModelsStore } from '@/store/useModelsStore';
import { useRecentModels } from '@/hooks/useRecentModels';
import type { ModelInfo } from '../types';

// Mock the store
vi.mock('@/store/useModelsStore');

// Mock useRecentModels hook with vi.fn() so it can be overridden per-test
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: vi.fn(),
}));

const mockUseRecentModels = vi.mocked(useRecentModels);

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

  let mockFetchModels: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();

    // Default useRecentModels return value; override per-test as needed
    mockUseRecentModels.mockReturnValue({
      recentModelIds: ['claude-sonnet-4'],
      addRecentModel: vi.fn(),
      hasParseError: false,
    });

    mockFetchModels = vi.fn();
    const mockStore = {
      models: mockModels,
      providers: ['anthropic', 'openai'],
      isLoading: false,
      error: null,
      lastFetched: Date.now(),
      fetchModels: mockFetchModels,
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

  it('should render browse all models link inside dropdown', () => {
    render(
      <ApiModelSelect
        agentKey="architect"
        value=""
        onChange={vi.fn()}
      />
    );

    // "Browse all models..." is now inside SelectContent, so open the dropdown first
    fireEvent.click(screen.getByRole('combobox'));

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

    // "Browse all models..." is a SelectItem inside the dropdown
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(screen.getByText(/browse all models/i));

    await waitFor(() => {
      expect(screen.getByText(/select model for architect/i)).toBeInTheDocument();
    });
  });

  it('should display current model even when not in recent models list', () => {
    // Recent models only include claude-sonnet-4, but value is gpt-4o
    mockUseRecentModels.mockReturnValue({
      recentModelIds: ['claude-sonnet-4'],
      addRecentModel: vi.fn(),
      hasParseError: false,
    });

    render(
      <ApiModelSelect
        agentKey="architect"
        value="gpt-4o"
        onChange={vi.fn()}
      />
    );

    // The trigger should show "GPT-4o" from the store lookup, not be blank
    expect(screen.getByText('GPT-4o')).toBeInTheDocument();
  });

  it('should show fallback raw ID when model not in store', () => {
    render(
      <ApiModelSelect
        agentKey="architect"
        value="unknown/model-123"
        onChange={vi.fn()}
      />
    );

    // When the model ID isn't in the store, it should display the raw ID as fallback
    expect(screen.getByText('unknown/model-123')).toBeInTheDocument();
  });

  it('should call fetchModels on mount', () => {
    render(
      <ApiModelSelect
        agentKey="architect"
        value=""
        onChange={vi.fn()}
      />
    );

    expect(mockFetchModels).toHaveBeenCalled();
  });

  it('should not call onChange when browse sentinel selected', () => {
    const onChange = vi.fn();
    render(
      <ApiModelSelect
        agentKey="architect"
        value=""
        onChange={onChange}
      />
    );

    // Open dropdown and click "Browse all models..."
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(screen.getByText(/browse all models/i));

    // onChange should NOT have been called — the browse sentinel opens the sheet instead
    expect(onChange).not.toHaveBeenCalled();
  });
});
