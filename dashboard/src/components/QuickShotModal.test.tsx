import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QuickShotModal } from './QuickShotModal';
import { api, ApiError } from '@/api/client';
import { toast } from 'sonner';

// Mock the API client
vi.mock('@/api/client', () => ({
  api: {
    createWorkflow: vi.fn(),
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

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('QuickShotModal', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders modal with title when open', () => {
      render(<QuickShotModal {...defaultProps} />);
      expect(screen.getByText('QUICK SHOT')).toBeInTheDocument();
    });

    it('renders all form fields', () => {
      render(<QuickShotModal {...defaultProps} />);
      expect(screen.getByLabelText(/task id/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/worktree path/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/profile/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/task title/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    });

    it('renders Cancel and Start Workflow buttons', () => {
      render(<QuickShotModal {...defaultProps} />);
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /start workflow/i })).toBeInTheDocument();
    });

    it('does not render when closed', () => {
      render(<QuickShotModal open={false} onOpenChange={vi.fn()} />);
      expect(screen.queryByText('QUICK SHOT')).not.toBeInTheDocument();
    });
  });

  describe('validation', () => {
    it('shows error when task ID is empty after focusing and leaving field', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      // Focus task ID and then blur without entering anything
      const taskIdField = screen.getByLabelText(/task id/i);
      await user.click(taskIdField);
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText(/task id is required/i)).toBeInTheDocument();
      });
    });

    it('shows error when worktree path is not absolute', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/worktree path/i), 'relative/path');
      // Blur to trigger validation
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText(/must be an absolute path/i)).toBeInTheDocument();
      });
    });

    it('shows error when task ID has invalid characters', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK@001!');
      // Blur to trigger validation
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText(/only letters, numbers, hyphens/i)).toBeInTheDocument();
      });
    });

    it('disables submit button until required fields are valid', async () => {
      render(<QuickShotModal {...defaultProps} />);
      const submitButton = screen.getByRole('button', { name: /start workflow/i });
      expect(submitButton).toBeDisabled();
    });

    it('enables submit button when required fields are filled', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      await waitFor(() => {
        const submitButton = screen.getByRole('button', { name: /start workflow/i });
        expect(submitButton).not.toBeDisabled();
      });
    });
  });

  describe('submission', () => {
    it('calls createWorkflow API on valid submit', async () => {
      const user = userEvent.setup();
      const mockCreateWorkflow = vi.mocked(api.createWorkflow);
      mockCreateWorkflow.mockResolvedValueOnce({
        id: 'wf-abc123',
        status: 'pending',
        message: 'Workflow created',
      });

      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      await user.click(screen.getByRole('button', { name: /start workflow/i }));

      await waitFor(() => {
        expect(mockCreateWorkflow).toHaveBeenCalledWith({
          issue_id: 'TASK-001',
          worktree_path: '/Users/me/repo',
          profile: undefined,
          task_title: 'Test title',
          task_description: undefined,
        });
      });
    });

    it('shows success toast and closes modal on success', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      const mockCreateWorkflow = vi.mocked(api.createWorkflow);
      mockCreateWorkflow.mockResolvedValueOnce({
        id: 'wf-abc123',
        status: 'pending',
        message: 'Workflow created',
      });

      render(<QuickShotModal open={true} onOpenChange={onOpenChange} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      await user.click(screen.getByRole('button', { name: /start workflow/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          expect.stringContaining('wf-abc123')
        );
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });

    it('shows error toast on API error', async () => {
      const user = userEvent.setup();
      const mockCreateWorkflow = vi.mocked(api.createWorkflow);
      mockCreateWorkflow.mockRejectedValueOnce(
        new ApiError('Worktree in use', 'WORKTREE_IN_USE', 409)
      );

      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      await user.click(screen.getByRole('button', { name: /start workflow/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Worktree in use');
      });
    });

    it('shows loading state during submission', async () => {
      const user = userEvent.setup();
      const mockCreateWorkflow = vi.mocked(api.createWorkflow);
      let resolvePromise: (value: { id: string; status: string; message: string }) => void;
      mockCreateWorkflow.mockReturnValueOnce(
        new Promise((resolve) => {
          resolvePromise = resolve;
        })
      );

      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      await user.click(screen.getByRole('button', { name: /start workflow/i }));

      // Wait for the launching state to appear (after 400ms ripple animation)
      await waitFor(() => {
        expect(screen.getByText(/launching/i)).toBeInTheDocument();
      });

      resolvePromise!({ id: 'wf-123', status: 'pending', message: 'ok' });
    });
  });
});
