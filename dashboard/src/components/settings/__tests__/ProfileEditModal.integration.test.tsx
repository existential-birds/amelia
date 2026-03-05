// dashboard/src/components/settings/__tests__/ProfileEditModal.integration.test.tsx

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileEditModal } from '../ProfileEditModal';
import { useModelsStore } from '@/store/useModelsStore';
import { makeMockModelsStore } from '@/test/mocks/modelsStore';
import { createProfile, updateProfile } from '@/api/settings';
import * as toast from '@/components/Toast';

// Mock the models store
vi.mock('@/store/useModelsStore');

// Mock settings API
vi.mock('@/api/settings', () => ({
  createProfile: vi.fn(),
  updateProfile: vi.fn(),
}));

// Mock toast notifications
vi.mock('@/components/Toast', async () => {
  const actual = await vi.importActual<typeof import('@/components/Toast')>('@/components/Toast');
  return { ...actual, error: vi.fn(), success: vi.fn() };
});

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

  it('should show simple select with Claude model options when driver is claude (default)', async () => {
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

    // Default is Claude driver - should NOT show "Browse all models" link
    expect(screen.queryByText(/Browse all models/i)).not.toBeInTheDocument();
    // Should see opus/sonnet/haiku options in the simple select
    // These are the Claude model options
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
        developer: { driver: 'claude', model: 'opus', options: {} },
        reviewer: { driver: 'claude', model: 'sonnet', options: {} },
        plan_validator: { driver: 'claude', model: 'haiku', options: {} },
        task_reviewer: { driver: 'claude', model: 'haiku', options: {} },
        evaluator: { driver: 'claude', model: 'haiku', options: {} },
        brainstormer: { driver: 'claude', model: 'haiku', options: {} },
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

  it('should show codex model options when driver is codex', async () => {
    const user = userEvent.setup();
    const profileWithCodexDriver = {
      id: 'codex-profile',
      tracker: 'noop',
      repo_root: '/test',
      plan_output_dir: 'docs/plans',
      plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
      is_active: false,
      agents: {
        architect: { driver: 'codex', model: 'gpt-5.3-codex', options: {} },
        developer: { driver: 'codex', model: 'gpt-5.3-codex', options: {} },
        reviewer: { driver: 'codex', model: 'gpt-5.3-codex', options: {} },
        plan_validator: { driver: 'codex', model: 'gpt-5.3-codex', options: {} },
        task_reviewer: { driver: 'codex', model: 'gpt-5.3-codex', options: {} },
        evaluator: { driver: 'codex', model: 'gpt-5.3-codex', options: {} },
        brainstormer: { driver: 'codex', model: 'gpt-5.3-codex', options: {} },
      },
    };

    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={profileWithCodexDriver}
        onSaved={vi.fn()}
      />
    );

    // Switch to Agents tab to see agent configuration
    await user.click(screen.getByRole('tab', { name: /agents/i }));

    // Should NOT show "Browse all models" link (not api driver)
    expect(screen.queryByText(/Browse all models/i)).not.toBeInTheDocument();
    // Should see codex model options in the simple select
    expect(screen.getAllByText('gpt-5.3-codex').length).toBeGreaterThan(0);
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
        plan_validator: { driver: 'claude', model: 'haiku', options: {} },
        task_reviewer: { driver: 'claude', model: 'haiku', options: {} },
        evaluator: { driver: 'claude', model: 'haiku', options: {} },
        brainstormer: { driver: 'claude', model: 'haiku', options: {} },
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

// =============================================================================
// Save Flow Tests
// =============================================================================

describe('ProfileEditModal save flow', () => {
  const testProfile = {
    id: 'test-profile',
    tracker: 'noop',
    repo_root: '/original/path',
    plan_output_dir: 'docs/plans',
    plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
    is_active: false,
    agents: {
      architect: { driver: 'claude', model: 'opus', options: {} },
      developer: { driver: 'claude', model: 'opus', options: {} },
      reviewer: { driver: 'claude', model: 'sonnet', options: {} },
      plan_validator: { driver: 'claude', model: 'haiku', options: {} },
      task_reviewer: { driver: 'claude', model: 'haiku', options: {} },
      evaluator: { driver: 'claude', model: 'haiku', options: {} },
      brainstormer: { driver: 'claude', model: 'haiku', options: {} },
    },
  };

  /** Profile-shaped return value for mocked API calls */
  const savedProfile = { ...testProfile, is_active: false };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useModelsStore).mockImplementation(makeMockModelsStore());
    vi.mocked(updateProfile).mockResolvedValue(savedProfile);
    vi.mocked(createProfile).mockResolvedValue(savedProfile);
  });

  it('should call updateProfile and close modal when saving in edit mode', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const onOpenChange = vi.fn();

    render(
      <ProfileEditModal
        open={true}
        onOpenChange={onOpenChange}
        profile={testProfile}
        onSaved={onSaved}
      />
    );

    // Change repo_root to a new absolute path
    const repoRootInput = screen.getByRole('textbox', { name: /repository root/i });
    await user.clear(repoRootInput);
    await user.type(repoRootInput, '/new/repo/path');

    // Click Save
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(updateProfile).toHaveBeenCalledTimes(1);
    });

    // Verify the payload contains the new repo_root
    const call = vi.mocked(updateProfile).mock.calls[0]!;
    expect(call[0]).toBe('test-profile');
    expect(call[1].repo_root).toBe('/new/repo/path');

    // Modal should close
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('should call createProfile and close modal when saving in create mode', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const onOpenChange = vi.fn();

    render(
      <ProfileEditModal
        open={true}
        onOpenChange={onOpenChange}
        profile={null}
        onSaved={onSaved}
      />
    );

    // Fill required fields
    const nameInput = screen.getByRole('textbox', { name: /profile name/i });
    await user.type(nameInput, 'new-profile');

    const repoRootInput = screen.getByRole('textbox', { name: /repository root/i });
    await user.type(repoRootInput, '/home/user/repo');

    // Click Create
    await user.click(screen.getByRole('button', { name: /create profile/i }));

    await waitFor(() => {
      expect(createProfile).toHaveBeenCalledTimes(1);
    });

    const payload = vi.mocked(createProfile).mock.calls[0]![0];
    expect(payload.id).toBe('new-profile');
    expect(payload.repo_root).toBe('/home/user/repo');

    // Modal should close
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('should not call any API when validation fails (empty repo_root)', async () => {
    const user = userEvent.setup();

    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={null}
        onSaved={vi.fn()}
      />
    );

    // Fill profile name but leave repo_root empty
    const nameInput = screen.getByRole('textbox', { name: /profile name/i });
    await user.type(nameInput, 'valid-name');

    // Click Create without filling repo_root
    await user.click(screen.getByRole('button', { name: /create profile/i }));

    expect(createProfile).not.toHaveBeenCalled();
    expect(updateProfile).not.toHaveBeenCalled();
  });

  it('should show error toast with backend error message', async () => {
    const user = userEvent.setup();
    vi.mocked(updateProfile).mockRejectedValue(new Error('Validation failed: repo_root invalid'));

    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={testProfile}
        onSaved={vi.fn()}
      />
    );

    // Make a change so the form is dirty and submittable
    const repoRootInput = screen.getByRole('textbox', { name: /repository root/i });
    await user.clear(repoRootInput);
    await user.type(repoRootInput, '/another/path');

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Validation failed: repo_root invalid');
    });
  });

  it('should show inline error when a relative path is entered and field is blurred', async () => {
    const user = userEvent.setup();

    render(
      <ProfileEditModal
        open={true}
        onOpenChange={vi.fn()}
        profile={null}
        onSaved={vi.fn()}
      />
    );

    const repoRootInput = screen.getByRole('textbox', { name: /repository root/i });
    await user.type(repoRootInput, 'my-repo');
    await user.tab(); // blur the field

    await waitFor(() => {
      expect(screen.getByText('Repository root must be an absolute path')).toBeInTheDocument();
    });
  });
});
