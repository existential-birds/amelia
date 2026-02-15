/**
 * @fileoverview Tests for SetPlanModal component.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SetPlanModal } from '../SetPlanModal';
import { api, ApiError } from '@/api/client';
import type { SetPlanResponse } from '@/types';
import { toast } from 'sonner';

// Mock the API client
vi.mock('@/api/client', () => ({
  api: {
    setPlan: vi.fn(),
    listFiles: vi.fn().mockResolvedValue({ files: [], directory: '' }),
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
  const defaultProps: React.ComponentProps<typeof SetPlanModal> = {
    open: true,
    onOpenChange: vi.fn(),
    workflowId: 'wf-123',
    worktreePath: '/path/to/repo',
    planOutputDir: undefined,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.setPlan).mockResolvedValue({
      status: 'validating',
      goal: 'Test goal',
      key_files: ['src/main.ts'],
      total_tasks: 3,
    });
  });

  afterEach(() => {
    // Ensure cleanup happens before moving to next test
    cleanup();
  });

  /**
   * Helper to render the modal and wait for initial effects to settle.
   * This prevents act() warnings from useEffect in PlanImportSection.
   */
  async function renderAndWaitForInit(props = defaultProps) {
    const result = render(<SetPlanModal {...props} />);
    // Wait for PlanImportSection's useEffect to run (the one that updates on mount)
    // If open, the component renders and effects run
    if (props.open !== false) {
      await waitFor(() => {
        // Just waiting a tick for effects to settle
        expect(result.container).toBeInTheDocument();
      });
    }
    return result;
  }

  describe('rendering', () => {
    it('renders modal with title when open', async () => {
      await renderAndWaitForInit();
      expect(screen.getByText(/set plan/i)).toBeInTheDocument();
    });

    it('does not render when closed', () => {
      // When modal is closed, no async operations occur
      render(<SetPlanModal {...defaultProps} open={false} />);
      expect(screen.queryByText(/set plan/i)).not.toBeInTheDocument();
    });

    it('renders PlanImportSection expanded', async () => {
      await renderAndWaitForInit();
      // PlanImportSection content should be visible
      expect(screen.getByPlaceholderText(/relative path/i)).toBeInTheDocument();
    });

    it('renders Cancel and Apply buttons', async () => {
      await renderAndWaitForInit();
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /apply/i })).toBeInTheDocument();
    });
  });

  describe('overwrite checkbox', () => {
    it('does not show overwrite checkbox when hasPlan is false', async () => {
      await renderAndWaitForInit({ ...defaultProps, hasPlan: false });
      expect(screen.queryByLabelText(/overwrite/i)).not.toBeInTheDocument();
    });

    it('shows overwrite checkbox when hasPlan is true', async () => {
      await renderAndWaitForInit({ ...defaultProps, hasPlan: true });
      expect(screen.getByLabelText(/overwrite/i)).toBeInTheDocument();
    });

    it('overwrite checkbox is unchecked by default', async () => {
      await renderAndWaitForInit({ ...defaultProps, hasPlan: true });
      const checkbox = screen.getByLabelText(/overwrite/i);
      expect(checkbox).not.toBeChecked();
    });
  });

  describe('submission', () => {
    it('Apply button is disabled when no plan data entered', async () => {
      await renderAndWaitForInit();
      expect(screen.getByRole('button', { name: /apply/i })).toBeDisabled();
    });

    it('Apply button is enabled when plan file path is entered', async () => {
      const user = userEvent.setup();
      await renderAndWaitForInit();

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /apply/i })).not.toBeDisabled();
      });
    });

    it('calls api.setPlan with plan_file when file path is provided', async () => {
      const user = userEvent.setup();
      await renderAndWaitForInit();

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
      await renderAndWaitForInit();

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
      await renderAndWaitForInit({ ...defaultProps, hasPlan: true });

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
        status: 'validating',
        goal: 'Implement authentication',
        key_files: ['src/auth.ts'],
        total_tasks: 5,
      });

      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      await renderAndWaitForInit({ ...defaultProps, onOpenChange });

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
        status: 'validating',
        goal: 'Some goal',
        key_files: [],
        total_tasks: 0,
      });

      const user = userEvent.setup();
      await renderAndWaitForInit();

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Plan imported, validating...');
      });
    });

    it('shows inline error on API error', async () => {
      const user = userEvent.setup();
      vi.mocked(api.setPlan).mockRejectedValueOnce(
        new ApiError('Plan file not found', 'PLAN_NOT_FOUND', 404)
      );

      await renderAndWaitForInit();

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => {
        expect(screen.getByText('Plan file not found')).toBeInTheDocument();
      });
    });

    it('shows loading state during submission', async () => {
      const user = userEvent.setup();
      let resolvePromise: (value: SetPlanResponse) => void;
      vi.mocked(api.setPlan).mockReturnValueOnce(
        new Promise((resolve) => {
          resolvePromise = resolve;
        })
      );

      await renderAndWaitForInit();

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /apply/i }));

      // Check for loading indicator
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /applying/i })).toBeInTheDocument();
      });

      // Resolve the promise and wait for the submission to complete
      await act(async () => {
        resolvePromise!({ status: 'validating', goal: 'Test', key_files: [], total_tasks: 1 });
      });
    });
  });

  describe('cancel', () => {
    it('closes modal when Cancel button is clicked', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      await renderAndWaitForInit({ ...defaultProps, onOpenChange });

      await user.click(screen.getByRole('button', { name: /cancel/i }));

      await waitFor(() => {
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });

    it('closes modal when close button is clicked', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      await renderAndWaitForInit({ ...defaultProps, onOpenChange });

      // Close button has sr-only text "Close"
      await user.click(screen.getByRole('button', { name: /close/i }));

      await waitFor(() => {
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });
  });
});
