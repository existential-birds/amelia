import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import ProfileDetailPage from '../ProfileDetailPage';
import { createMockProfile } from '@/__tests__/fixtures';
import type { Profile } from '@/api/settings';
import { useModelsStore } from '@/store/useModelsStore';
import { makeMockModelsStore } from '@/test/mocks/modelsStore';
import { activateProfile, createProfile, updateProfile } from '@/api/settings';
import * as toast from '@/components/Toast';

// Mock the models store
vi.mock('@/store/useModelsStore');

// Mock settings API
vi.mock('@/api/settings', () => ({
  createProfile: vi.fn(),
  updateProfile: vi.fn(),
  activateProfile: vi.fn(),
  getProfile: vi.fn(),
}));

// Mock toast notifications
vi.mock('@/components/Toast', async () => {
  const actual = await vi.importActual<typeof import('@/components/Toast')>('@/components/Toast');
  return { ...actual, error: vi.fn(), success: vi.fn() };
});

// Mock useRecentModels
vi.mock('@/hooks/useRecentModels', () => ({
  useRecentModels: () => ({
    recentModelIds: ['claude-sonnet-4'],
    addRecentModel: vi.fn(),
  }),
}));

/**
 * Pattern P1 — render ProfileDetailPage through a memory data-router so the
 * loader and useBlocker work. Mirrors WorkflowDetailPage.test.tsx.
 */
function renderPage(profile: Profile | null, initial = '/settings/profiles/p') {
  const router = createMemoryRouter(
    [
      {
        path: '/settings/profiles/:id',
        element: <ProfileDetailPage />,
        loader: () => ({ profile }),
        HydrateFallback: () => null,
      },
      { path: '/settings/profiles', element: <div>LIST</div> },
    ],
    { initialEntries: [initial] }
  );
  return render(<RouterProvider router={router} />);
}

describe('ProfileDetailPage shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useModelsStore).mockImplementation(makeMockModelsStore());
  });

  it('renders the profile id in edit mode and defaults to Identity', async () => {
    renderPage(createMockProfile({ id: 'dev', repo_root: '/r' }), '/settings/profiles/dev');
    expect(await screen.findByRole('heading', { name: /dev/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /repository root/i })).toHaveValue('/r');
  });

  it('shows create UI when profile is null', async () => {
    renderPage(null, '/settings/profiles/new');
    expect(await screen.findByRole('button', { name: /create profile/i })).toBeInTheDocument();
  });

  it('switches sections via the rail', async () => {
    const user = userEvent.setup();
    renderPage(createMockProfile(), '/settings/profiles/dev');
    await user.click(await screen.findByRole('button', { name: /sandbox/i }));
    expect(screen.getByText(/sandbox mode/i)).toBeInTheDocument();
  });

  it('activates from the header', async () => {
    const user = userEvent.setup();
    vi.mocked(activateProfile).mockResolvedValue(createMockProfile({ is_active: true }));
    renderPage(createMockProfile({ id: 'dev', is_active: false }), '/settings/profiles/dev');
    await user.click(await screen.findByRole('button', { name: /set active/i }));
    await waitFor(() => expect(activateProfile).toHaveBeenCalledWith('dev'));
  });
});

describe('ProfileDetailPage save flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useModelsStore).mockImplementation(makeMockModelsStore());
    vi.mocked(updateProfile).mockResolvedValue(createMockProfile());
    vi.mocked(createProfile).mockResolvedValue(createMockProfile());
  });

  it('calls updateProfile with the edited payload then navigates to the list', async () => {
    const user = userEvent.setup();
    renderPage(
      createMockProfile({ id: 'test-profile', repo_root: '/original/path' }),
      '/settings/profiles/test-profile'
    );

    const repo = await screen.findByRole('textbox', { name: /repository root/i });
    await user.clear(repo);
    await user.type(repo, '/new/repo/path');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(updateProfile).toHaveBeenCalledTimes(1));
    expect(vi.mocked(updateProfile).mock.calls[0]![0]).toBe('test-profile');
    expect(vi.mocked(updateProfile).mock.calls[0]![1].repo_root).toBe('/new/repo/path');
    expect(await screen.findByText('LIST')).toBeInTheDocument();
  });

  it('creates from /new with the typed name + repo', async () => {
    const user = userEvent.setup();
    renderPage(null, '/settings/profiles/new');

    await user.type(
      await screen.findByRole('textbox', { name: /profile name/i }),
      'new-profile'
    );
    await user.type(
      screen.getByRole('textbox', { name: /repository root/i }),
      '/home/user/repo'
    );
    await user.click(screen.getByRole('button', { name: /create profile/i }));

    await waitFor(() => expect(createProfile).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(createProfile).mock.calls[0]![0];
    expect(payload.id).toBe('new-profile');
    expect(payload.repo_root).toBe('/home/user/repo');
    expect(updateProfile).not.toHaveBeenCalled();
    expect(await screen.findByText('LIST')).toBeInTheDocument();
  });

  it('does not call the API when repo_root is empty', async () => {
    const user = userEvent.setup();
    renderPage(null, '/settings/profiles/new');

    await user.type(
      await screen.findByRole('textbox', { name: /profile name/i }),
      'valid-name'
    );
    await user.click(screen.getByRole('button', { name: /create profile/i }));

    expect(createProfile).not.toHaveBeenCalled();
    expect(updateProfile).not.toHaveBeenCalled();
    expect(screen.queryByText('LIST')).not.toBeInTheDocument();
  });

  it('marks the section rail when save fails validation', async () => {
    const user = userEvent.setup();
    renderPage(null, '/settings/profiles/new');

    await user.type(
      await screen.findByRole('textbox', { name: /profile name/i }),
      'valid-name'
    );
    await user.click(screen.getByRole('button', { name: /create profile/i }));

    expect(createProfile).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /identity/i })).toHaveAttribute(
      'data-has-error',
      'true'
    );
  });

  it('shows the backend error message as a toast', async () => {
    const user = userEvent.setup();
    vi.mocked(updateProfile).mockRejectedValue(
      new Error('Validation failed: repo_root invalid')
    );
    renderPage(
      createMockProfile({ id: 'test-profile', repo_root: '/original/path' }),
      '/settings/profiles/test-profile'
    );

    const repo = await screen.findByRole('textbox', { name: /repository root/i });
    await user.clear(repo);
    await user.type(repo, '/another/path');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Validation failed: repo_root invalid')
    );
    expect(screen.queryByText('LIST')).not.toBeInTheDocument();
  });

  it('shows an inline absolute-path error on blur', async () => {
    const user = userEvent.setup();
    renderPage(null, '/settings/profiles/new');

    const repo = await screen.findByRole('textbox', { name: /repository root/i });
    await user.type(repo, 'my-repo');
    await user.tab();

    await waitFor(() =>
      expect(
        screen.getByText('Repository root must be an absolute path')
      ).toBeInTheDocument()
    );
  });
});
