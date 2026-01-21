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
    driver: 'cli:claude',
    model: 'opus',
    is_active: true,
    working_dir: '/repo',
    validator_model: 'haiku',
    tracker: 'noop',
    plan_output_dir: 'docs/plans',
    plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
    max_review_iterations: 3,
    max_task_review_iterations: 5,
    auto_approve_reviews: false,
  },
  {
    id: 'prod',
    driver: 'api:openrouter',
    model: 'gpt-4',
    is_active: false,
    working_dir: '/prod',
    validator_model: 'haiku',
    tracker: 'jira',
    plan_output_dir: 'docs/plans',
    plan_path_pattern: 'docs/plans/{date}-{issue_key}.md',
    max_review_iterations: 3,
    max_task_review_iterations: 5,
    auto_approve_reviews: false,
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

    expect(await screen.findByText(/No profiles configured/)).toBeInTheDocument();
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
    expect(screen.queryByText('prod')).not.toBeInTheDocument();
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

    // dev uses cli:claude, should be visible
    expect(screen.getByText('dev')).toBeInTheDocument();
    // prod uses api:openrouter, should be hidden
    expect(screen.queryByText('prod')).not.toBeInTheDocument();
  });

  it('shows no match message when search has no results', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    const searchInput = screen.getByPlaceholderText('Search profiles...');
    fireEvent.change(searchInput, { target: { value: 'nonexistent' } });

    expect(screen.getByText(/No profiles match your search/)).toBeInTheDocument();
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
    expect(await screen.findByText('cli:claude')).toBeInTheDocument();
    expect(screen.getByText('api:openrouter')).toBeInTheDocument();
  });

  it('sorts active profile first', async () => {
    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    const cards = await screen.findAllByText(/dev|prod/);
    // Active profile (dev) should come first
    expect(cards[0].textContent).toBe('dev');
  });
});

describe('SettingsProfilesPage actions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useLoaderData).mockReturnValue({ profiles: mockProfiles });
  });

  it('calls activateProfile when Set Active is clicked', async () => {
    const user = userEvent.setup();
    vi.mocked(settingsApi.activateProfile).mockResolvedValue(mockProfiles[1]);

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Find all dropdown triggers (h-8 w-8 buttons)
    const dropdownTriggers = screen.getAllByRole('button').filter(
      (btn) => btn.className.includes('h-8 w-8')
    );

    // Click the second dropdown (prod profile, which is not active)
    await user.click(dropdownTriggers[1]);

    // Wait for dropdown menu to appear and click Set Active
    const setActiveItem = await screen.findByRole('menuitem', { name: /set active/i });
    await user.click(setActiveItem);

    await waitFor(() => {
      expect(settingsApi.activateProfile).toHaveBeenCalledWith('prod');
    });
    expect(toast.success).toHaveBeenCalledWith('Profile "prod" is now active');
  });

  it('calls deleteProfile when Delete is clicked and confirmed', async () => {
    const user = userEvent.setup();
    vi.mocked(settingsApi.deleteProfile).mockResolvedValue();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Find all dropdown triggers
    const dropdownTriggers = screen.getAllByRole('button').filter(
      (btn) => btn.className.includes('h-8 w-8')
    );

    // Click the first dropdown (dev profile)
    await user.click(dropdownTriggers[0]);

    // Wait for dropdown menu to appear and click Delete
    const deleteItem = await screen.findByRole('menuitem', { name: /delete/i });
    await user.click(deleteItem);

    await waitFor(() => {
      expect(settingsApi.deleteProfile).toHaveBeenCalledWith('dev');
    });
    expect(toast.success).toHaveBeenCalledWith('Profile deleted');
  });

  it('does not delete when confirm is cancelled', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Find all dropdown triggers
    const dropdownTriggers = screen.getAllByRole('button').filter(
      (btn) => btn.className.includes('h-8 w-8')
    );

    // Click the first dropdown
    await user.click(dropdownTriggers[0]);

    // Wait for dropdown menu to appear and click Delete
    const deleteItem = await screen.findByRole('menuitem', { name: /delete/i });
    await user.click(deleteItem);

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

    // Find all dropdown triggers
    const dropdownTriggers = screen.getAllByRole('button').filter(
      (btn) => btn.className.includes('h-8 w-8')
    );

    // Click the second dropdown (prod profile)
    await user.click(dropdownTriggers[1]);

    // Wait for dropdown menu to appear and click Set Active
    const setActiveItem = await screen.findByRole('menuitem', { name: /set active/i });
    await user.click(setActiveItem);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to activate profile');
    });
  });

  it('shows error toast when delete fails', async () => {
    const user = userEvent.setup();
    vi.mocked(settingsApi.deleteProfile).mockRejectedValue(new Error('API error'));
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(
      <MemoryRouter>
        <SettingsProfilesPage />
      </MemoryRouter>
    );

    // Find all dropdown triggers
    const dropdownTriggers = screen.getAllByRole('button').filter(
      (btn) => btn.className.includes('h-8 w-8')
    );

    // Click the first dropdown
    await user.click(dropdownTriggers[0]);

    // Wait for dropdown menu to appear and click Delete
    const deleteItem = await screen.findByRole('menuitem', { name: /delete/i });
    await user.click(deleteItem);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to delete profile');
    });
  });
});
