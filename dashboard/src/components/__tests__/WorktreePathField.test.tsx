/**
 * @fileoverview Tests for WorktreePathField component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorktreePathField } from '../WorktreePathField';
import { api } from '@/api/client';

// Mock the API client
vi.mock('@/api/client', () => ({
  api: {
    validatePath: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public code: string,
      public status: number
    ) {
      super(message);
    }
  },
}));

describe('WorktreePathField', () => {
  const defaultProps = {
    value: '',
    onChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders the input field with placeholder', () => {
      render(<WorktreePathField {...defaultProps} />);
      expect(
        screen.getByPlaceholderText('/Users/me/projects/my-repo')
      ).toBeInTheDocument();
    });

    it('renders the label', () => {
      render(<WorktreePathField {...defaultProps} />);
      expect(screen.getByText('Worktree Path')).toBeInTheDocument();
    });

    it('displays error message when provided', () => {
      render(
        <WorktreePathField {...defaultProps} error="Must be an absolute path" />
      );
      expect(screen.getByText('Must be an absolute path')).toBeInTheDocument();
    });

    it('renders Recent button when recentPaths provided', () => {
      render(
        <WorktreePathField
          {...defaultProps}
          recentPaths={['/path/one', '/path/two']}
        />
      );
      expect(
        screen.getByRole('button', { name: /recent/i })
      ).toBeInTheDocument();
    });

    it('does not render Recent button when no paths available', () => {
      render(<WorktreePathField {...defaultProps} />);
      expect(
        screen.queryByRole('button', { name: /recent/i })
      ).not.toBeInTheDocument();
    });
  });

  describe('path input', () => {
    it('calls onChange when user types', async () => {
      const onChange = vi.fn();
      const user = userEvent.setup();

      render(<WorktreePathField {...defaultProps} onChange={onChange} />);

      const input = screen.getByPlaceholderText('/Users/me/projects/my-repo');
      await user.type(input, '/test/path');

      expect(onChange).toHaveBeenCalled();
    });

    it('displays current value', () => {
      render(<WorktreePathField {...defaultProps} value="/my/repo/path" />);

      const input = screen.getByPlaceholderText(
        '/Users/me/projects/my-repo'
      ) as HTMLInputElement;
      expect(input.value).toBe('/my/repo/path');
    });
  });

  describe('path validation', () => {
    it('validates path after debounce delay', async () => {
      vi.mocked(api.validatePath).mockResolvedValue({
        exists: true,
        is_git_repo: true,
        branch: 'main',
        repo_name: 'test-repo',
        has_changes: false,
        message: 'Git repository on branch main',
      });

      render(<WorktreePathField {...defaultProps} value="/valid/git/repo" />);

      // Wait for validation to complete
      await waitFor(
        () => {
          expect(api.validatePath).toHaveBeenCalledWith('/valid/git/repo', expect.any(AbortSignal));
        },
        { timeout: 1000 }
      );
    });

    it('shows valid status for git repository', async () => {
      vi.mocked(api.validatePath).mockResolvedValue({
        exists: true,
        is_git_repo: true,
        branch: 'main',
        repo_name: 'test-repo',
        has_changes: false,
        message: 'Git repository on branch main',
      });

      render(<WorktreePathField {...defaultProps} value="/valid/git/repo" />);

      await waitFor(() => {
        expect(
          screen.getByText(/Git repository on branch main/i)
        ).toBeInTheDocument();
      });
    });

    it('shows warning for non-git directory', async () => {
      vi.mocked(api.validatePath).mockResolvedValue({
        exists: true,
        is_git_repo: false,
        repo_name: 'some-dir',
        message: 'Directory exists but is not a git repository',
      });

      render(<WorktreePathField {...defaultProps} value="/some/directory" />);

      await waitFor(() => {
        expect(
          screen.getByText(/not a git repository/i)
        ).toBeInTheDocument();
      });
    });

    it('shows error for nonexistent path', async () => {
      vi.mocked(api.validatePath).mockResolvedValue({
        exists: false,
        is_git_repo: false,
        message: 'Path does not exist',
      });

      render(
        <WorktreePathField {...defaultProps} value="/nonexistent/path" />
      );

      await waitFor(() => {
        expect(screen.getByText(/does not exist/i)).toBeInTheDocument();
      });
    });

    it('shows branch and changes indicator for valid repo', async () => {
      vi.mocked(api.validatePath).mockResolvedValue({
        exists: true,
        is_git_repo: true,
        branch: 'feature-branch',
        repo_name: 'my-repo',
        has_changes: true,
        message: 'Git repository on branch feature-branch with uncommitted changes',
      });

      render(<WorktreePathField {...defaultProps} value="/path/to/repo" />);

      await waitFor(() => {
        expect(screen.getByText('feature-branch')).toBeInTheDocument();
      });
    });

    it('handles API errors gracefully', async () => {
      const { ApiError } = await import('@/api/client');
      vi.mocked(api.validatePath).mockRejectedValue(
        new ApiError('Not found', 'NOT_FOUND', 404)
      );

      render(<WorktreePathField {...defaultProps} value="/some/path" />);

      // Wait for validation to be called
      await waitFor(() => {
        expect(api.validatePath).toHaveBeenCalled();
      });

      // Should fall back to idle state - no validation status message shown
      // The help text is shown when status is idle and no validation/error
      await waitFor(() => {
        expect(
          screen.getByText('Absolute path to git repository where agents will operate')
        ).toBeInTheDocument();
      });

      // No error message should be displayed for 404 (endpoint doesn't exist case)
      expect(screen.queryByText(/could not validate path/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/does not exist/i)).not.toBeInTheDocument();
    });

    it('does not validate relative paths', async () => {
      vi.useFakeTimers();
      render(<WorktreePathField {...defaultProps} value="relative/path" />);

      // Advance past debounce delay to ensure no validation was triggered
      await vi.advanceTimersByTimeAsync(600);

      expect(api.validatePath).not.toHaveBeenCalled();
      vi.useRealTimers();
    });

    it('does not validate empty paths', async () => {
      vi.useFakeTimers();
      render(<WorktreePathField {...defaultProps} value="" />);

      // Advance past debounce delay to ensure no validation was triggered
      await vi.advanceTimersByTimeAsync(600);

      expect(api.validatePath).not.toHaveBeenCalled();
      vi.useRealTimers();
    });
  });

  describe('recent paths dropdown', () => {
    it('shows server default with special indicator', async () => {
      const user = userEvent.setup();

      render(
        <WorktreePathField
          {...defaultProps}
          serverWorkingDir="/server/working/dir"
          recentPaths={['/recent/path']}
        />
      );

      // Open dropdown
      const recentButton = screen.getByRole('button', { name: /recent/i });
      await user.click(recentButton);

      await waitFor(() => {
        expect(screen.getByText('Server Default')).toBeInTheDocument();
      });
    });

    it('calls onChange when selecting a path', async () => {
      const onChange = vi.fn();
      const user = userEvent.setup();
      vi.mocked(api.validatePath).mockResolvedValue({
        exists: true,
        is_git_repo: true,
        branch: 'main',
        message: 'Git repository',
      });

      render(
        <WorktreePathField
          {...defaultProps}
          onChange={onChange}
          recentPaths={['/recent/path']}
        />
      );

      // Open dropdown
      const recentButton = screen.getByRole('button', { name: /recent/i });
      await user.click(recentButton);

      // Click on the recent path
      const pathOption = await screen.findByText('/recent/path');
      await user.click(pathOption);

      expect(onChange).toHaveBeenCalledWith('/recent/path');
    });
  });

  describe('breadcrumb display', () => {
    it('shows path segments as breadcrumbs', () => {
      render(
        <WorktreePathField {...defaultProps} value="/Users/test/projects/repo" />
      );

      // Should show last 3 segments plus ellipsis
      expect(screen.getByText('...')).toBeInTheDocument();
      expect(screen.getByText('test')).toBeInTheDocument();
      expect(screen.getByText('projects')).toBeInTheDocument();
      expect(screen.getByText('repo')).toBeInTheDocument();
    });

    it('highlights last segment', () => {
      render(<WorktreePathField {...defaultProps} value="/a/b/repo" />);

      // The last segment should be highlighted with primary color
      const repoSegment = screen.getByText('repo');
      expect(repoSegment).toHaveClass('text-primary');
    });
  });

  describe('accessibility', () => {
    it('has proper label association', () => {
      render(<WorktreePathField {...defaultProps} id="test-worktree" />);

      const input = screen.getByPlaceholderText('/Users/me/projects/my-repo');
      expect(input).toHaveAttribute('id', 'test-worktree');
    });

    it('shows aria-invalid when error present', () => {
      render(
        <WorktreePathField {...defaultProps} error="Invalid path" />
      );

      const input = screen.getByPlaceholderText('/Users/me/projects/my-repo');
      expect(input).toHaveAttribute('aria-invalid', 'true');
    });

    it('disables input when disabled prop is true', () => {
      render(<WorktreePathField {...defaultProps} disabled />);

      const input = screen.getByPlaceholderText('/Users/me/projects/my-repo');
      expect(input).toBeDisabled();
    });
  });
});
