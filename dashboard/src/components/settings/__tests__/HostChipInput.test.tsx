import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileEditModal } from '../ProfileEditModal';
import { useModelsStore } from '@/store/useModelsStore';

vi.mock('@/store/useModelsStore');
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: [],
    addRecentModel: vi.fn(),
  }),
}));

describe('HostChipInput via Sandbox tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const state = {
      models: [],
      providers: [],
      isLoading: false,
      error: null,
      lastFetched: Date.now(),
      fetchModels: vi.fn().mockResolvedValue(undefined),
      refreshModels: vi.fn().mockResolvedValue(undefined),
      getModelsForAgent: vi.fn().mockReturnValue([]),
    };
    vi.mocked(useModelsStore).mockImplementation(
      (selector?: (s: typeof state) => unknown) => selector ? selector(state) : state
    );
  });

  const renderSandboxTab = async () => {
    const user = userEvent.setup();
    const profile = {
      id: 'test',
      tracker: 'noop',
      working_dir: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {},
      sandbox: {
        mode: 'container' as const,
        image: 'amelia-sandbox:latest',
        network_allowlist_enabled: true,
        network_allowed_hosts: ['api.anthropic.com'],
      },
    };
    render(
      <ProfileEditModal open={true} onOpenChange={vi.fn()} profile={profile} onSaved={vi.fn()} />
    );
    await user.click(screen.getByRole('tab', { name: /sandbox/i }));
    return user;
  };

  it('should add a host when pressing Enter', async () => {
    const user = await renderSandboxTab();
    const input = screen.getByPlaceholderText('api.example.com');
    await user.type(input, 'openrouter.ai{Enter}');
    expect(screen.getByText('openrouter.ai')).toBeInTheDocument();
  });

  it('should add a host when clicking Add button', async () => {
    const user = await renderSandboxTab();
    const input = screen.getByPlaceholderText('api.example.com');
    await user.type(input, 'github.com');
    await user.click(screen.getByRole('button', { name: /^add$/i }));
    expect(screen.getByText('github.com')).toBeInTheDocument();
  });

  it('should remove a host when clicking the remove button', async () => {
    const user = await renderSandboxTab();
    expect(screen.getByText('api.anthropic.com')).toBeInTheDocument();
    await user.click(screen.getByLabelText('Remove api.anthropic.com'));
    expect(screen.queryByText('api.anthropic.com')).not.toBeInTheDocument();
  });

  it('should show error for invalid hostname', async () => {
    const user = await renderSandboxTab();
    const input = screen.getByPlaceholderText('api.example.com');
    await user.type(input, 'not a valid host!{Enter}');
    expect(screen.getByText('Invalid hostname')).toBeInTheDocument();
  });

  it('should show error for duplicate hostname', async () => {
    const user = await renderSandboxTab();
    const input = screen.getByPlaceholderText('api.example.com');
    await user.type(input, 'api.anthropic.com{Enter}');
    expect(screen.getByText('Host already added')).toBeInTheDocument();
  });
});
