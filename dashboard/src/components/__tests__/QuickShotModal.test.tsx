/**
 * @fileoverview Tests for QuickShotModal queue buttons functionality.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QuickShotModal } from '../QuickShotModal';
import { api } from '@/api/client';

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

describe('QuickShotModal queue buttons', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.createWorkflow).mockResolvedValue({
      id: 'wf-123',
      status: 'pending',
      message: 'Workflow created',
    });
  });

  /**
   * Helper to fill out the required form fields.
   */
  async function fillRequiredFields() {
    const user = userEvent.setup();

    // Fill Task ID
    const taskIdInput = screen.getByPlaceholderText('TASK-001');
    await user.clear(taskIdInput);
    await user.type(taskIdInput, 'ISSUE-123');

    // Fill Worktree Path
    const worktreeInput = screen.getByPlaceholderText(
      '/Users/me/projects/my-repo'
    );
    await user.clear(worktreeInput);
    await user.type(worktreeInput, '/path/to/repo');

    // Fill Task Title
    const titleInput = screen.getByPlaceholderText('Add logout button to navbar');
    await user.clear(titleInput);
    await user.type(titleInput, 'Test task title');
  }

  it('should render Queue button', () => {
    render(<QuickShotModal {...defaultProps} />);
    expect(screen.getByRole('button', { name: /^queue$/i })).toBeInTheDocument();
  });

  it('should render Plan & Queue button', () => {
    render(<QuickShotModal {...defaultProps} />);
    expect(
      screen.getByRole('button', { name: /plan.*queue/i })
    ).toBeInTheDocument();
  });

  it('should render Start button', () => {
    render(<QuickShotModal {...defaultProps} />);
    expect(screen.getByRole('button', { name: /^start$/i })).toBeInTheDocument();
  });

  it('should call api.createWorkflow with start=false for Queue button', async () => {
    render(<QuickShotModal {...defaultProps} />);

    await fillRequiredFields();

    const queueButton = screen.getByRole('button', { name: /^queue$/i });
    fireEvent.click(queueButton);

    await waitFor(() => {
      expect(api.createWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({
          start: false,
          plan_now: false,
        })
      );
    });
  });

  it('should call api.createWorkflow with plan_now=true for Plan & Queue button', async () => {
    render(<QuickShotModal {...defaultProps} />);

    await fillRequiredFields();

    const planQueueButton = screen.getByRole('button', { name: /plan.*queue/i });
    fireEvent.click(planQueueButton);

    await waitFor(() => {
      expect(api.createWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({
          start: false,
          plan_now: true,
        })
      );
    });
  });

  it('should call api.createWorkflow with start=true for Start button', async () => {
    render(<QuickShotModal {...defaultProps} />);

    await fillRequiredFields();

    const startButton = screen.getByRole('button', { name: /^start$/i });
    fireEvent.click(startButton);

    await waitFor(() => {
      expect(api.createWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({
          start: true,
        })
      );
    });
  });

  it('should disable all submit buttons when form is invalid', () => {
    render(<QuickShotModal {...defaultProps} />);

    // Form is initially invalid (empty required fields)
    const queueButton = screen.getByRole('button', { name: /^queue$/i });
    const planQueueButton = screen.getByRole('button', { name: /plan.*queue/i });
    const startButton = screen.getByRole('button', { name: /^start$/i });

    expect(queueButton).toBeDisabled();
    expect(planQueueButton).toBeDisabled();
    expect(startButton).toBeDisabled();
  });

  it('should enable submit buttons when form is valid', async () => {
    render(<QuickShotModal {...defaultProps} />);

    await fillRequiredFields();

    const queueButton = screen.getByRole('button', { name: /^queue$/i });
    const planQueueButton = screen.getByRole('button', { name: /plan.*queue/i });
    const startButton = screen.getByRole('button', { name: /^start$/i });

    expect(queueButton).not.toBeDisabled();
    expect(planQueueButton).not.toBeDisabled();
    expect(startButton).not.toBeDisabled();
  });

  it('should close modal after successful Plan & Queue submission', async () => {
    const onOpenChange = vi.fn();
    render(<QuickShotModal open={true} onOpenChange={onOpenChange} />);

    await fillRequiredFields();

    const planQueueButton = screen.getByRole('button', { name: /plan.*queue/i });
    fireEvent.click(planQueueButton);

    await waitFor(() => {
      expect(api.createWorkflow).toHaveBeenCalled();
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('should close modal after successful Queue submission', async () => {
    const onOpenChange = vi.fn();
    render(<QuickShotModal open={true} onOpenChange={onOpenChange} />);

    await fillRequiredFields();

    const queueButton = screen.getByRole('button', { name: /^queue$/i });
    fireEvent.click(queueButton);

    await waitFor(() => {
      expect(api.createWorkflow).toHaveBeenCalled();
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
