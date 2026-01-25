/**
 * @fileoverview Tests for SettingsProfilesPage.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import SettingsProfilesPage from '../SettingsProfilesPage';
import * as settingsApi from '../../api/settings';
import * as toast from '../../components/Toast';

// Mock React Router
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...mod,
    useLoaderData: vi.fn(),
    useRevalidator: () => ({ revalidate: vi.fn(), state: 'idle' }),
  };
});

// Mock the API
vi.mock('../../api/settings', () => ({
  deleteProfile: vi.fn(),
  activateProfile: vi.fn(),
}));

// Mock toast
vi.mock('../../components/Toast', () => ({
  success: vi.fn(),
  error: vi.fn(),
}));

import { useLoaderData } from 'react-router-dom';

const mockProfiles = [
  {
    id: 'dev',
    is_active: true,
    working_dir: '/repo',
    tracker: 'none',
    plan_output_dir: 'docs/plans',
    plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
    auto_approve_reviews: false,
    agents: {
      architect: { driver: 'cli', model: 'opus', options: {} },
      developer: { driver: 'cli', model: 'opus', options: {} },
      reviewer: { driver: 'cli', model: 'haiku', options: {} },
    },
  },
  {
    id: 'prod',
    is_active: false,
    working_dir: '/prod',
    tracker: 'jira',
    plan_output_dir: 'docs/plans',
    plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
    auto_approve_reviews: false,
    agents: {
      architect: { driver: 'api', model: 'gpt-4', options: {} },
      developer: { driver: 'api', model: 'gpt-4', options: {} },
      reviewer: { driver: 'api', model: 'gpt-4', options: {} },
    },
  },
];

describe('SettingsProfilesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useLoaderData).mockReturnValue({ profiles: mockProfiles });
  });

  it('renders profile cards', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('dev')).toBeInTheDocument();
    expect(screen.getByText('prod')).toBeInTheDocument();
  });

  it('shows active badge on active profile', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('Active')).toBeInTheDocument();
  });

  it('shows empty state when no profiles', async () => {
    vi.mocked(useLoaderData).mockReturnValue({ profiles: [] });

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/Configure Your Agent Team/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create Your First Profile/i })).toBeInTheDocument();
  });

  it('filters profiles by search', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    const searchInput = screen.getByPlaceholderText('Search profiles...');
    fireEvent.change(searchInput, { target: { value: 'dev' } });

    expect(screen.getByText('dev')).toBeInTheDocument();
    // Wait for animation to complete - filtered items are removed after exit animation
    await waitFor(() => {
      expect(screen.queryByText('prod')).not.toBeInTheDocument();
    });
  });

  it('filters profiles by driver type', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Click the CLI filter
    const cliButton = screen.getByRole('radio', { name: 'CLI' });
    fireEvent.click(cliButton);

    // dev uses cli, should be visible
    expect(screen.getByText('dev')).toBeInTheDocument();
    // prod uses api, should be hidden after animation
    await waitFor(() => {
      expect(screen.queryByText('prod')).not.toBeInTheDocument();
    });
  });

  it('shows no match message when search has no results', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    const searchInput = screen.getByPlaceholderText('Search profiles...');
    fireEvent.change(searchInput, { target: { value: 'nonexistent' } });

    expect(screen.getByText(/No profiles found/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Clear filters/i })).toBeInTheDocument();
  });

  it('renders Create Profile button', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    expect(screen.getByRole('button', { name: /create profile/i })).toBeInTheDocument();
  });

  it('displays driver badges with correct colors', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Check that driver badges are rendered
    expect(await screen.findByText('cli')).toBeInTheDocument();
    expect(screen.getByText('api')).toBeInTheDocument();
  });

  it('sorts active profile first', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    const cards = await screen.findAllByText(/dev|prod/);
    // Active profile (dev) should come first
    expect(cards[0]?.textContent).toBe('dev');
  });
});

describe('SettingsProfilesPage actions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useLoaderData).mockReturnValue({ profiles: mockProfiles });
  });

  it('calls activateProfile when clicking inactive profile card', async () => {
    const user = userEvent.setup();
    const prodProfile = mockProfiles[1];
    if (!prodProfile) throw new Error('Test setup error: prodProfile not found');
    vi.mocked(settingsApi.activateProfile).mockResolvedValue(prodProfile);

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Click on the prod profile card (inactive) to activate it
    const prodCard = screen.getByText('prod').closest('[class*="cursor-pointer"]');
    if (!prodCard) throw new Error('Test setup error: prod card not found');
    await user.click(prodCard);

    await waitFor(() => {
      expect(settingsApi.activateProfile).toHaveBeenCalledWith('prod');
    });
    expect(toast.success).toHaveBeenCalledWith('Profile "prod" is now active');
  });

  it('calls deleteProfile when trash button is clicked and confirmed', async () => {
    const user = userEvent.setup();
    vi.mocked(settingsApi.deleteProfile).mockResolvedValue();

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Find the dev profile card, then find the trash button within it
    const devCard = screen.getByText('dev').closest('[class*="cursor-pointer"]');
    if (!devCard) throw new Error('Test setup error: dev card not found');

    // Find the button with hover:text-destructive class (trash button)
    const trashButton = devCard.querySelector('button[class*="hover:text-destructive"]');
    if (!trashButton) throw new Error('Test setup error: trash button not found');
    await user.click(trashButton);

    // Wait for the AlertDialog to appear and click the Delete button
    const deleteButton = await screen.findByRole('button', { name: 'Delete' });
    await user.click(deleteButton);

    await waitFor(() => {
      expect(settingsApi.deleteProfile).toHaveBeenCalledWith('dev');
    });
    expect(toast.success).toHaveBeenCalledWith('Profile deleted');
  });

  it('does not delete when confirm is cancelled', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Find the dev profile card, then find the trash button within it
    const devCard = screen.getByText('dev').closest('[class*="cursor-pointer"]');
    if (!devCard) throw new Error('Test setup error: dev card not found');

    // Find the button with hover:text-destructive class (trash button)
    const trashButton = devCard.querySelector('button[class*="hover:text-destructive"]');
    if (!trashButton) throw new Error('Test setup error: trash button not found');
    await user.click(trashButton);

    // Wait for the AlertDialog to appear and click the Cancel button
    const cancelButton = await screen.findByRole('button', { name: 'Cancel' });
    await user.click(cancelButton);

    expect(settingsApi.deleteProfile).not.toHaveBeenCalled();
  });

  it('shows error toast when activation fails', async () => {
    const user = userEvent.setup();
    vi.mocked(settingsApi.activateProfile).mockRejectedValue(new Error('API error'));

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Click on the prod profile card (inactive) to try activating it
    const prodCard = screen.getByText('prod').closest('[class*="cursor-pointer"]');
    if (!prodCard) throw new Error('Test setup error: prod card not found');
    await user.click(prodCard);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to activate profile');
    });
  });

  it('shows error toast when delete fails', async () => {
    const user = userEvent.setup();
    vi.mocked(settingsApi.deleteProfile).mockRejectedValue(new Error('API error'));

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Find the dev profile card, then find the trash button within it
    const devCard = screen.getByText('dev').closest('[class*="cursor-pointer"]');
    if (!devCard) throw new Error('Test setup error: dev card not found');

    // Find the button with hover:text-destructive class (trash button)
    const trashButton = devCard.querySelector('button[class*="hover:text-destructive"]');
    if (!trashButton) throw new Error('Test setup error: trash button not found');
    await user.click(trashButton);

    // Wait for the AlertDialog to appear and click the Delete button
    const deleteButton = await screen.findByRole('button', { name: 'Delete' });
    await user.click(deleteButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to delete profile');
    });
  });
});
