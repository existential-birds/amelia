import React from 'react';
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

    it('renders Cancel, Queue, Plan & Queue, and Start buttons', () => {
      render(<QuickShotModal {...defaultProps} />);
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^queue$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /plan.*queue/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^start$/i })).toBeInTheDocument();
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

    it('disables submit buttons until required fields are valid', async () => {
      render(<QuickShotModal {...defaultProps} />);
      expect(screen.getByRole('button', { name: /^queue$/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /plan.*queue/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /^start$/i })).toBeDisabled();
    });

    it('enables submit buttons when required fields are filled', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^queue$/i })).not.toBeDisabled();
        expect(screen.getByRole('button', { name: /plan.*queue/i })).not.toBeDisabled();
        expect(screen.getByRole('button', { name: /^start$/i })).not.toBeDisabled();
      });
    });
  });

  describe('submission', () => {
    it('calls createWorkflow API with start=true on Start button click', async () => {
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

      await user.click(screen.getByRole('button', { name: /^start$/i }));

      await waitFor(() => {
        expect(mockCreateWorkflow).toHaveBeenCalledWith({
          issue_id: 'TASK-001',
          worktree_path: '/Users/me/repo',
          profile: undefined,
          task_title: 'Test title',
          task_description: undefined,
          start: true,
          plan_now: false,
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

      await user.click(screen.getByRole('button', { name: /^start$/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalled();
        // Verify the JSX content includes a link to the workflow
        const calls = vi.mocked(toast.success).mock.calls;
        expect(calls.length).toBeGreaterThan(0);
        const callArg = calls[0]?.[0] as React.ReactElement;
        expect(callArg).toBeDefined();
        // Find the anchor element in children (may be nested)
        const children = React.Children.toArray(callArg.props.children);
        const link = children.find(
          (child): child is React.ReactElement =>
            React.isValidElement(child) && child.type === 'a'
        );
        expect(link).toBeDefined();
        expect(link?.props.href).toBe('/workflows/wf-abc123');
        expect(link?.props.children).toBe('wf-abc123');
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

      await user.click(screen.getByRole('button', { name: /^start$/i }));

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

      await user.click(screen.getByRole('button', { name: /^start$/i }));

      // Wait for the launching state to appear (after 400ms ripple animation)
      await waitFor(() => {
        expect(screen.getByText(/launching/i)).toBeInTheDocument();
      });

      resolvePromise!({ id: 'wf-123', status: 'pending', message: 'ok' });
    });
  });
});
