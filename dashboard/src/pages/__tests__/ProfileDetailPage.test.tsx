import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import ProfileDetailPage from '../ProfileDetailPage';
import { createMockProfile } from '@/__tests__/fixtures';
import type { Profile } from '@/api/settings';
import { useModelsStore } from '@/store/useModelsStore';
import { makeMockModelsStore } from '@/test/mocks/modelsStore';
import { activateProfile } from '@/api/settings';

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
