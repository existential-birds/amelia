/**
 * @fileoverview Tests for GitHubIssueCombobox component.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { api } from '@/api/client';
import { GitHubIssueCombobox } from '../GitHubIssueCombobox';
import type { GitHubIssueSummary } from '@/types';

vi.mock('@/api/client', () => ({
  api: {
    getGitHubIssues: vi.fn(),
  },
}));

const mockIssues: GitHubIssueSummary[] = [
  {
    number: 42,
    title: 'Fix login bug',
    labels: [{ name: 'bug', color: 'd73a4a' }],
    assignee: 'alice',
    created_at: '2026-03-01T10:00:00Z',
    state: 'OPEN',
  },
  {
    number: 17,
    title: 'Add dark mode',
    labels: [],
    assignee: null,
    created_at: '2026-02-15T08:00:00Z',
    state: 'OPEN',
  },
];

describe('GitHubIssueCombobox', () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getGitHubIssues).mockResolvedValue({ issues: mockIssues });
  });

  it('renders trigger button', () => {
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);
    expect(screen.getByRole('combobox', { name: /select issue/i })).toBeInTheDocument();
  });

  it('fetches and displays issues when opened', async () => {
    const user = userEvent.setup();
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);

    await user.click(screen.getByRole('combobox', { name: /select issue/i }));

    await waitFor(() => {
      expect(screen.getByText('#42')).toBeInTheDocument();
      expect(screen.getByText('Fix login bug')).toBeInTheDocument();
      expect(screen.getByText('#17')).toBeInTheDocument();
    });
  });

  it('calls onSelect with issue data when item clicked', async () => {
    const user = userEvent.setup();
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);

    await user.click(screen.getByRole('combobox', { name: /select issue/i }));
    await waitFor(() => expect(screen.getByText('#42')).toBeInTheDocument());

    await user.click(screen.getByText('Fix login bug'));

    expect(onSelect).toHaveBeenCalledWith(mockIssues[0]!);
  });

  it('shows empty state when no issues found', async () => {
    vi.mocked(api.getGitHubIssues).mockResolvedValue({ issues: [] });
    const user = userEvent.setup();
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);

    await user.click(screen.getByRole('combobox', { name: /select issue/i }));

    await waitFor(() => {
      expect(screen.getByText(/no issues found/i)).toBeInTheDocument();
    });
  });

  it('refetches when profile changes', async () => {
    const { rerender } = render(
      <GitHubIssueCombobox profile="first" onSelect={onSelect} />
    );
    expect(api.getGitHubIssues).toHaveBeenCalledWith('first', undefined, expect.any(AbortSignal));

    rerender(<GitHubIssueCombobox profile="second" onSelect={onSelect} />);
    expect(api.getGitHubIssues).toHaveBeenCalledWith('second', undefined, expect.any(AbortSignal));
  });

  it('displays label badges', async () => {
    const user = userEvent.setup();
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);

    await user.click(screen.getByRole('combobox', { name: /select issue/i }));

    await waitFor(() => {
      expect(screen.getByText('bug')).toBeInTheDocument();
    });
  });
});
