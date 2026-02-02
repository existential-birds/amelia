// dashboard/src/components/settings/__tests__/ProfileEditModal.integration.test.tsx

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ProfileEditModal } from '../ProfileEditModal';
import { useModelsStore } from '@/store/useModelsStore';
import type { ModelInfo } from '@/components/model-picker/types';

// Mock the models store
vi.mock('@/store/useModelsStore');

// Mock useRecentModels
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: [],
    addRecentModel: vi.fn(),
  }),
}));

describe('ProfileEditModal model selection', () => {
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

  // Create a mock store that supports selector functions
  const createMockStore = (
    overrides: Partial<{
      models: ModelInfo[];
      providers: string[];
      isLoading: boolean;
      error: string | null;
      lastFetched: number | null;
      fetchModels: () => Promise<void>;
      refreshModels: () => Promise<void>;
      getModelsForAgent: (agentKey: string) => ModelInfo[];
    }> = {}
  ) => {
    const state = {
      models: mockModels,
      providers: ['anthropic'],
      isLoading: false,
      error: null,
      lastFetched: Date.now(),
      fetchModels: vi.fn().mockResolvedValue(undefined),
      refreshModels: vi.fn().mockResolvedValue(undefined),
      getModelsForAgent: vi.fn().mockReturnValue(mockModels),
      ...overrides,
    };
    // Return a function that handles both selector calls and no-selector calls
    // useModelsStore(selector) returns selector(state)
    // useModelsStore() returns the full state object
    return (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state;
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useModelsStore).mockImplementation(createMockStore());
  });

  it('should show simple select with CLI model options when driver is cli (default)', () => {
    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={null}
        onSaved={vi.fn()}
      />
    );

    // Default is CLI driver - should NOT show "Browse all models" link
    expect(screen.queryByText(/Browse all models/i)).not.toBeInTheDocument();
    // Should see opus/sonnet/haiku options in the simple select
    // These are the CLI model options
    expect(screen.getAllByText('sonnet').length).toBeGreaterThan(0);
  });

  it('should show ApiModelSelect with browse link when driver is api', async () => {
    const profileWithApiDriver = {
      id: 'test-profile',
      tracker: 'none',
      working_dir: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {
        architect: { driver: 'api', model: 'claude-sonnet-4', options: {} },
        developer: { driver: 'cli', model: 'opus', options: {} },
        reviewer: { driver: 'cli', model: 'sonnet', options: {} },
        plan_validator: { driver: 'cli', model: 'haiku', options: {} },
        task_reviewer: { driver: 'cli', model: 'haiku', options: {} },
        evaluator: { driver: 'cli', model: 'haiku', options: {} },
        brainstormer: { driver: 'cli', model: 'haiku', options: {} },
      },
    };

    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={profileWithApiDriver}
        onSaved={vi.fn()}
      />
    );

    // Since architect has api driver, should show Browse all models link
    await waitFor(() => {
      expect(screen.getByText(/Browse all models/i)).toBeInTheDocument();
    });
  });

  it('should show multiple ApiModelSelect components when multiple agents use api driver', async () => {
    const profileWithMultipleApiDrivers = {
      id: 'multi-api-profile',
      tracker: 'none',
      working_dir: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {
        architect: { driver: 'api', model: 'claude-sonnet-4', options: {} },
        developer: { driver: 'api', model: 'claude-sonnet-4', options: {} },
        reviewer: { driver: 'api', model: 'claude-sonnet-4', options: {} },
        plan_validator: { driver: 'cli', model: 'haiku', options: {} },
        task_reviewer: { driver: 'cli', model: 'haiku', options: {} },
        evaluator: { driver: 'cli', model: 'haiku', options: {} },
        brainstormer: { driver: 'cli', model: 'haiku', options: {} },
      },
    };

    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={profileWithMultipleApiDrivers}
        onSaved={vi.fn()}
      />
    );

    // Three primary agents have api driver, so should show 3 "Browse all models" links
    await waitFor(() => {
      const browseLinks = screen.getAllByText(/Browse all models/i);
      expect(browseLinks.length).toBe(3);
    });
  });
});
