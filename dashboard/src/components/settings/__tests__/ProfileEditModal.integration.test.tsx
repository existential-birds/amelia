// dashboard/src/components/settings/__tests__/ProfileEditModal.integration.test.tsx

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileEditModal } from '../ProfileEditModal';
import { useModelsStore } from '@/store/useModelsStore';
import { makeMockModelsStore } from '@/test/mocks/modelsStore';

// Mock the models store
vi.mock('@/store/useModelsStore');

// Mock useRecentModels with a recent model to show dropdown with "Browse all models" link
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: ['claude-sonnet-4'],
    addRecentModel: vi.fn(),
  }),
}));

describe('ProfileEditModal model selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useModelsStore).mockImplementation(makeMockModelsStore());
  });

  it('should show simple select with CLI model options when driver is cli (default)', async () => {
    const user = userEvent.setup();
    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={null}
        onSaved={vi.fn()}
      />
    );

    // Switch to Agents tab to see agent configuration
    await user.click(screen.getByRole('tab', { name: /agents/i }));

    // Default is CLI driver - should NOT show "Browse all models" link
    expect(screen.queryByText(/Browse all models/i)).not.toBeInTheDocument();
    // Should see opus/sonnet/haiku options in the simple select
    // These are the CLI model options
    expect(screen.getAllByText('sonnet').length).toBeGreaterThan(0);
  });

  it('should show ApiModelSelect with browse link when driver is api', async () => {
    const user = userEvent.setup();
    const profileWithApiDriver = {
      id: 'test-profile',
      tracker: 'noop',
      repo_root: '/test',
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

    // Switch to Agents tab to see agent configuration
    await user.click(screen.getByRole('tab', { name: /agents/i }));

    // Since architect has api driver, should show Browse all models link
    await waitFor(() => {
      expect(screen.getByText(/Browse all models/i)).toBeInTheDocument();
    });
  });

  it('should show multiple ApiModelSelect components when multiple agents use api driver', async () => {
    const user = userEvent.setup();
    const profileWithMultipleApiDrivers = {
      id: 'multi-api-profile',
      tracker: 'noop',
      repo_root: '/test',
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

    // Switch to Agents tab to see agent configuration
    await user.click(screen.getByRole('tab', { name: /agents/i }));

    // Three primary agents have api driver, so should show 3 "Browse all models" links
    await waitFor(() => {
      const browseLinks = screen.getAllByText(/Browse all models/i);
      expect(browseLinks.length).toBe(3);
    });
  });
});
