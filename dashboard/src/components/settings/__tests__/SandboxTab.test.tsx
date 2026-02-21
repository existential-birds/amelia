import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileEditModal } from '../ProfileEditModal';
import { useModelsStore } from '@/store/useModelsStore';
import { makeMockModelsStore } from '@/test/mocks/modelsStore';

vi.mock('@/store/useModelsStore');
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: [],
    addRecentModel: vi.fn(),
  }),
}));

describe('Sandbox tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useModelsStore).mockImplementation(
      makeMockModelsStore({
        models: [],
        providers: [],
        fetchModels: vi.fn().mockResolvedValue(undefined),
        refreshModels: vi.fn().mockResolvedValue(undefined),
        getModelsForAgent: vi.fn().mockReturnValue([]),
      })
    );
  });

  const renderWithSandboxTab = async (profile: Parameters<typeof ProfileEditModal>[0]['profile'] = null) => {
    const user = userEvent.setup();
    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={profile}
        onSaved={vi.fn()}
      />
    );
    // Click the Sandbox tab
    await user.click(screen.getByRole('tab', { name: /sandbox/i }));
    return user;
  };

  it('should show sandbox mode dropdown defaulting to None', async () => {
    await renderWithSandboxTab();
    // Radix Select renders both a visible span and a native option for "None"
    expect(screen.getAllByText('None').length).toBeGreaterThanOrEqual(1);
    // Verify the description text for "none" mode
    expect(screen.getByText('Code runs directly on the host machine.')).toBeInTheDocument();
  });

  it('should not show container fields when mode is None', async () => {
    await renderWithSandboxTab();
    expect(screen.queryByLabelText(/docker image/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/network allowlist/i)).not.toBeInTheDocument();
  });

  it('should show container fields when mode is Container', async () => {
    const profile = {
      id: 'test',
      tracker: 'noop',
      repo_root: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {},
      sandbox: {
        mode: 'container' as const,
        image: 'amelia-sandbox:latest',
        network_allowlist_enabled: false,
        network_allowed_hosts: [],
      },
    };

    await renderWithSandboxTab(profile);
    expect(screen.getByDisplayValue('amelia-sandbox:latest')).toBeInTheDocument();
  });

  it('should show allowed hosts when network allowlist is enabled', async () => {
    const profile = {
      id: 'test',
      tracker: 'noop',
      repo_root: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {},
      sandbox: {
        mode: 'container' as const,
        image: 'amelia-sandbox:latest',
        network_allowlist_enabled: true,
        network_allowed_hosts: ['api.anthropic.com', 'github.com'],
      },
    };

    await renderWithSandboxTab(profile);
    expect(screen.getByText('api.anthropic.com')).toBeInTheDocument();
    expect(screen.getByText('github.com')).toBeInTheDocument();
  });
});
