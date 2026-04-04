/**
 * @fileoverview Tests for DevelopPage.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { api } from '@/api/client';
import DevelopPage from '../DevelopPage';

// Mock api client
vi.mock('@/api/client', () => ({
  api: {
    getConfig: vi.fn(),
    createWorkflow: vi.fn(),
    validatePath: vi.fn(),
    getGitHubIssues: vi.fn(),
    condenseDescription: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    constructor(message: string, public code: string, public status: number) {
      super(message);
      this.name = 'ApiError';
    }
  },
}));

// Mock ProfileSelect to simplify - it fetches its own data
vi.mock('@/components/ProfileSelect', () => ({
  ProfileSelect: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string) => void;
  }) => (
    <select
      data-testid="profile-select"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">None</option>
      <option value="test">test</option>
    </select>
  ),
}));

// Mock PlanImportSection
vi.mock('@/components/PlanImportSection', () => ({
  PlanImportSection: () => <div data-testid="plan-import-section" />,
}));

const LONG_BODY = 'x'.repeat(2001);

// Mock GitHubIssueCombobox
vi.mock('@/components/GitHubIssueCombobox', () => ({
  GitHubIssueCombobox: ({
    onSelect,
    onClear,
    value,
  }: {
    profile: string;
    onSelect: (issue: { number: number; title: string; body: string }) => void;
    onClear?: () => void;
    value?: { number: number; title: string } | null;
  }) => (
    <div>
      <button
        data-testid="issue-combobox"
        onClick={() => onSelect({ number: 42, title: 'Fix login bug', body: 'Login crashes on submit' })}
      >
        {value ? `#${value.number} — ${value.title}` : 'mock combobox'}
      </button>
      <button
        data-testid="issue-combobox-long"
        onClick={() => onSelect({ number: 99, title: 'Long issue', body: LONG_BODY })}
      >
        select long issue
      </button>
      {value && onClear && (
        <button data-testid="clear-issue-btn" onClick={onClear}>
          Clear
        </button>
      )}
    </div>
  ),
}));

// Mock settings API for profile tracker lookup
vi.mock('@/api/settings', () => ({
  getProfiles: vi.fn().mockResolvedValue([
    { id: 'test', tracker: 'github', repo_root: '/tmp/repo', is_active: true },
  ]),
}));

// Mock toast
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <DevelopPage />
    </MemoryRouter>,
  );
}

describe('DevelopPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getConfig).mockResolvedValue({
      repo_root: '/tmp/repo',
      active_profile: 'test',
      max_concurrent: 3,
      active_profile_info: { name: 'test', driver: 'cli:claude', model: 'opus' },
    });
    vi.mocked(api.validatePath).mockResolvedValue({
      exists: true,
      is_git_repo: true,
      branch: 'main',
      message: 'Valid',
    });
    vi.mocked(api.createWorkflow).mockResolvedValue({
      id: 'wf-1',
      status: 'pending',
      message: 'Created',
    });
  });

  it('renders the page title', async () => {
    renderPage();
    expect(screen.getByText(/develop/i)).toBeInTheDocument();
  });

  it('renders form fields', async () => {
    renderPage();
    expect(screen.getByTestId('profile-select')).toBeInTheDocument();
    expect(screen.getByLabelText(/task id/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/task title/i)).toBeInTheDocument();
  });

  it('shows issue combobox when github profile selected', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByTestId('profile-select'), 'test');

    await waitFor(() => {
      expect(screen.getByTestId('issue-combobox')).toBeInTheDocument();
    });
  });

  it('pre-fills form and makes fields read-only when issue selected', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByTestId('profile-select'), 'test');
    await waitFor(() => expect(screen.getByTestId('issue-combobox')).toBeInTheDocument());

    await user.click(screen.getByTestId('issue-combobox'));

    await waitFor(() => {
      expect(screen.getByLabelText(/task id/i)).toHaveValue('42');
      expect(screen.getByLabelText(/task title/i)).toHaveValue('Fix login bug');
      expect(screen.getByLabelText(/description/i)).toHaveValue('Login crashes on submit');
    });

    // Fields should be read-only after issue selection
    expect(screen.getByLabelText(/task id/i)).toHaveAttribute('readonly');
    expect(screen.getByLabelText(/task title/i)).toHaveAttribute('readonly');
    expect(screen.getByLabelText(/description/i)).toHaveAttribute('readonly');
  });

  it('renders Start and Queue buttons', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /start/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /queue/i })).toBeInTheDocument();
  });

  it('clears issue selection when clear button clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByTestId('profile-select'), 'test');
    await waitFor(() => expect(screen.getByTestId('issue-combobox')).toBeInTheDocument());

    // Select an issue
    await user.click(screen.getByTestId('issue-combobox'));

    await waitFor(() => {
      expect(screen.getByLabelText(/task id/i)).toHaveValue('42');
      expect(screen.getByLabelText(/task id/i)).toHaveAttribute('readonly');
    });

    // Click the clear button exposed by mock
    await user.click(screen.getByTestId('clear-issue-btn'));

    await waitFor(() => {
      expect(screen.getByLabelText(/task id/i)).toHaveValue('');
      expect(screen.getByLabelText(/task id/i)).not.toHaveAttribute('readonly');
    });
  });

  it('shows condense button when issue selected with long description', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByTestId('profile-select'), 'test');
    await waitFor(() => expect(screen.getByTestId('issue-combobox-long')).toBeInTheDocument());

    await user.click(screen.getByTestId('issue-combobox-long'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /condense with ai/i })).toBeInTheDocument();
    });
  });

  it('condense button calls API and updates description', async () => {
    const user = userEvent.setup();
    vi.mocked(api.condenseDescription).mockResolvedValue({ condensed: 'Condensed result' });
    renderPage();

    await user.selectOptions(screen.getByTestId('profile-select'), 'test');
    await waitFor(() => expect(screen.getByTestId('issue-combobox-long')).toBeInTheDocument());

    await user.click(screen.getByTestId('issue-combobox-long'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /condense with ai/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /condense with ai/i }));

    await waitFor(() => {
      expect(api.condenseDescription).toHaveBeenCalledWith(LONG_BODY, 'test');
      expect(screen.getByLabelText(/description/i)).toHaveValue('Condensed result');
    });
  });
});
