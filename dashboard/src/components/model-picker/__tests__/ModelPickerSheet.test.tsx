import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelPickerSheet } from '../ModelPickerSheet';
import { useModelsStore } from '@/store/useModelsStore';
import type { ModelInfo } from '../types';

// Mock the store with selector support
vi.mock('@/store/useModelsStore');

// Mock useRecentModels hook
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: [],
    addRecentModel: vi.fn(),
  }),
}));

describe('ModelPickerSheet', () => {
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
  ];

  const createMockStore = (overrides: Partial<ReturnType<typeof useModelsStore>> = {}) => {
    const state = {
      models: mockModels,
      providers: ['anthropic'],
      isLoading: false,
      error: null,
      lastFetched: Date.now(),
      fetchModels: vi.fn(),
      refreshModels: vi.fn(),
      getModelsForAgent: vi.fn().mockReturnValue(mockModels),
      ...overrides,
    };
    return (selector: (s: typeof state) => unknown) => selector(state);
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useModelsStore).mockImplementation(createMockStore());
  });

  it('should render trigger and open sheet on click', async () => {
    render(
      <ModelPickerSheet
        agentKey="architect"
        currentModel={null}
        onSelect={vi.fn()}
        trigger={<button>Browse models</button>}
      />
    );

    fireEvent.click(screen.getByText('Browse models'));

    await waitFor(() => {
      expect(screen.getByText(/select model for architect/i)).toBeInTheDocument();
    });
  });

  it('should fetch models when opened', async () => {
    const fetchModels = vi.fn();
    vi.mocked(useModelsStore).mockImplementation(
      createMockStore({
        models: [],
        providers: [],
        lastFetched: null,
        fetchModels,
      })
    );

    render(
      <ModelPickerSheet
        agentKey="architect"
        currentModel={null}
        onSelect={vi.fn()}
        trigger={<button>Browse</button>}
      />
    );

    fireEvent.click(screen.getByText('Browse'));

    await waitFor(() => {
      expect(fetchModels).toHaveBeenCalled();
    });
  });

  it('should call onSelect and close when model selected', async () => {
    const onSelect = vi.fn();

    render(
      <ModelPickerSheet
        agentKey="architect"
        currentModel={null}
        onSelect={onSelect}
        trigger={<button>Browse</button>}
      />
    );

    // Open sheet
    fireEvent.click(screen.getByText('Browse'));

    await waitFor(() => {
      expect(screen.getByText('Claude Sonnet 4')).toBeInTheDocument();
    });

    // Expand and select
    fireEvent.click(screen.getByRole('button', { name: /expand/i }));
    fireEvent.click(screen.getByRole('button', { name: /select/i }));

    expect(onSelect).toHaveBeenCalledWith('claude-sonnet-4');
  });

  it('should filter models by search query', async () => {
    const user = userEvent.setup();
    const moreModels: ModelInfo[] = [
      ...mockModels,
      {
        id: 'gpt-4o',
        name: 'GPT-4o',
        provider: 'openai',
        capabilities: { tool_call: true, reasoning: false, structured_output: true },
        cost: { input: 2.5, output: 10 },
        limit: { context: 200000, output: 16384 },
        modalities: { input: ['text'], output: ['text'] },
      },
    ];

    vi.mocked(useModelsStore).mockImplementation(
      createMockStore({
        models: moreModels,
        providers: ['anthropic', 'openai'],
      })
    );

    render(
      <ModelPickerSheet
        agentKey="developer"
        currentModel={null}
        onSelect={vi.fn()}
        trigger={<button>Browse</button>}
      />
    );

    fireEvent.click(screen.getByText('Browse'));

    await waitFor(() => {
      expect(screen.getByText('Claude Sonnet 4')).toBeInTheDocument();
      expect(screen.getByText('GPT-4o')).toBeInTheDocument();
    });

    // Search for "claude"
    await user.type(screen.getByPlaceholderText(/search/i), 'claude');

    await waitFor(() => {
      expect(screen.getByText('Claude Sonnet 4')).toBeInTheDocument();
      expect(screen.queryByText('GPT-4o')).not.toBeInTheDocument();
    });
  });

  it('should show refresh button in header', async () => {
    const refreshModels = vi.fn();
    vi.mocked(useModelsStore).mockImplementation(
      createMockStore({ refreshModels })
    );

    render(
      <ModelPickerSheet
        agentKey="architect"
        currentModel={null}
        onSelect={vi.fn()}
        trigger={<button>Browse</button>}
      />
    );

    fireEvent.click(screen.getByText('Browse'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /refresh/i }));

    expect(refreshModels).toHaveBeenCalled();
  });
});
