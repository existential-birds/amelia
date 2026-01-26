/**
 * @fileoverview Tests for SetPlanModal component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SetPlanModal } from '../SetPlanModal';
import { api, ApiError } from '@/api/client';
import { toast } from 'sonner';

// Mock the API client
vi.mock('@/api/client', () => ({
  api: {
    setPlan: vi.fn(),
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

describe('SetPlanModal', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    workflowId: 'wf-123',
    worktreePath: '/path/to/repo',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.setPlan).mockResolvedValue({
      goal: 'Test goal',
      key_files: ['src/main.ts'],
      total_tasks: 3,
    });
  });

  describe('rendering', () => {
    it('renders modal with title when open', () => {
      render(<SetPlanModal {...defaultProps} />);
      expect(screen.getByText(/set plan/i)).toBeInTheDocument();
    });

    it('does not render when closed', () => {
      render(<SetPlanModal {...defaultProps} open={false} />);
      expect(screen.queryByText(/set plan/i)).not.toBeInTheDocument();
    });

    it('renders PlanImportSection expanded', () => {
      render(<SetPlanModal {...defaultProps} />);
      // PlanImportSection content should be visible
      expect(screen.getByPlaceholderText(/relative path/i)).toBeInTheDocument();
    });

    it('renders Cancel and Apply buttons', () => {
      render(<SetPlanModal {...defaultProps} />);
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /apply/i })).toBeInTheDocument();
    });
  });

  describe('overwrite checkbox', () => {
    it('does not show overwrite checkbox when hasPlan is false', () => {
      render(<SetPlanModal {...defaultProps} hasPlan={false} />);
      expect(screen.queryByLabelText(/overwrite/i)).not.toBeInTheDocument();
    });

    it('shows overwrite checkbox when hasPlan is true', () => {
      render(<SetPlanModal {...defaultProps} hasPlan={true} />);
      expect(screen.getByLabelText(/overwrite/i)).toBeInTheDocument();
    });

    it('overwrite checkbox is unchecked by default', () => {
      render(<SetPlanModal {...defaultProps} hasPlan={true} />);
      const checkbox = screen.getByLabelText(/overwrite/i);
      expect(checkbox).not.toBeChecked();
    });
  });

  describe('submission', () => {
    it('Apply button is disabled when no plan data entered', () => {
      render(<SetPlanModal {...defaultProps} />);
      expect(screen.getByRole('button', { name: /apply/i })).toBeDisabled();
    });

    it('Apply button is enabled when plan file path is entered', async () => {
      const user = userEvent.setup();
      render(<SetPlanModal {...defaultProps} />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');

      expect(screen.getByRole('button', { name: /apply/i })).not.toBeDisabled();
    });

    it('calls api.setPlan with plan_file when file path is provided', async () => {
      const user = userEvent.setup();
      render(<SetPlanModal {...defaultProps} />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => {
        expect(api.setPlan).toHaveBeenCalledWith('wf-123', {
          plan_file: 'docs/plan.md',
          force: false,
        });
      });
    });

    it('calls api.setPlan with plan_content when content is pasted', async () => {
      const user = userEvent.setup();
      render(<SetPlanModal {...defaultProps} />);

      // Switch to paste mode
      await user.click(screen.getByRole('radio', { name: /paste/i }));

      const textarea = screen.getByPlaceholderText(/paste.*plan.*markdown/i);
      await user.type(textarea, '# My Plan');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => {
        expect(api.setPlan).toHaveBeenCalledWith('wf-123', {
          plan_content: '# My Plan',
          force: false,
        });
      });
    });

    it('includes force=true when overwrite is checked', async () => {
      const user = userEvent.setup();
      render(<SetPlanModal {...defaultProps} hasPlan={true} />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');

      const checkbox = screen.getByLabelText(/overwrite/i);
      await user.click(checkbox);

      await user.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => {
        expect(api.setPlan).toHaveBeenCalledWith('wf-123', {
          plan_file: 'docs/plan.md',
          force: true,
        });
      });
    });

    it('shows success toast with task count from response', async () => {
      vi.mocked(api.setPlan).mockResolvedValue({
        goal: 'Implement authentication',
        key_files: ['src/auth.ts'],
        total_tasks: 5,
      });

      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      render(<SetPlanModal {...defaultProps} onOpenChange={onOpenChange} />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          expect.stringContaining('5 tasks')
        );
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });

    it('shows generic success toast when total_tasks is 0', async () => {
      vi.mocked(api.setPlan).mockResolvedValue({
        goal: 'Some goal',
        key_files: [],
        total_tasks: 0,
      });

      const user = userEvent.setup();
      render(<SetPlanModal {...defaultProps} />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Plan applied successfully');
      });
    });

    it('shows inline error on API error', async () => {
      const user = userEvent.setup();
      vi.mocked(api.setPlan).mockRejectedValueOnce(
        new ApiError('Plan file not found', 'PLAN_NOT_FOUND', 404)
      );

      render(<SetPlanModal {...defaultProps} />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => {
        expect(screen.getByText('Plan file not found')).toBeInTheDocument();
      });
    });

    it('shows loading state during submission', async () => {
      const user = userEvent.setup();
      let resolvePromise: (value: { goal: string; key_files: string[]; total_tasks: number }) => void;
      vi.mocked(api.setPlan).mockReturnValueOnce(
        new Promise((resolve) => {
          resolvePromise = resolve;
        })
      );

      render(<SetPlanModal {...defaultProps} />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      // Check for loading indicator
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /applying/i })).toBeInTheDocument();
      });

      resolvePromise!({ goal: 'Test', key_files: [], total_tasks: 1 });
    });
  });

  describe('cancel', () => {
    it('closes modal when Cancel button is clicked', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      render(<SetPlanModal {...defaultProps} onOpenChange={onOpenChange} />);

      await user.click(screen.getByRole('button', { name: /cancel/i }));

      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it('closes modal when close button is clicked', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      render(<SetPlanModal {...defaultProps} onOpenChange={onOpenChange} />);

      // Close button has sr-only text "Close"
      await user.click(screen.getByRole('button', { name: /close/i }));

      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
