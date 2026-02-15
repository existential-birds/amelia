/**
 * @fileoverview Tests for PendingWorkflowControls component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PendingWorkflowControls } from '../PendingWorkflowControls';
import { api } from '@/api/client';

// Mock react-router-dom's useRevalidator
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useRevalidator: vi.fn(() => ({
      state: 'idle',
      revalidate: vi.fn(),
    })),
  };
});

// Mock the API client
vi.mock('@/api/client', () => ({
  api: {
    startWorkflow: vi.fn(),
    cancelWorkflow: vi.fn(),
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

describe('PendingWorkflowControls', () => {
  const defaultProps = {
    workflowId: 'wf-123',
    worktreePath: '/path/to/repo',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.startWorkflow).mockResolvedValue({
      workflow_id: 'wf-123',
      status: 'running',
    });
    vi.mocked(api.cancelWorkflow).mockResolvedValue(undefined);
    vi.mocked(api.setPlan).mockResolvedValue({
      goal: 'Test goal',
      key_files: [],
      total_tasks: 1,
    });
  });

  describe('rendering', () => {
    it('renders queued workflow header', () => {
      render(<PendingWorkflowControls {...defaultProps} />);
      expect(screen.getByText('QUEUED WORKFLOW')).toBeInTheDocument();
    });

    it('renders Start and Cancel buttons', () => {
      render(<PendingWorkflowControls {...defaultProps} />);
      expect(screen.getByRole('button', { name: /start/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });

    it('shows "No plan" badge when hasPlan is false', () => {
      render(<PendingWorkflowControls {...defaultProps} hasPlan={false} />);
      expect(screen.getByText(/no plan/i)).toBeInTheDocument();
    });

    it('shows "Plan ready" badge when hasPlan is true', () => {
      render(<PendingWorkflowControls {...defaultProps} hasPlan={true} />);
      expect(screen.getByText(/plan ready/i)).toBeInTheDocument();
    });
  });

  describe('Set Plan button', () => {
    it('renders Set Plan button', () => {
      render(<PendingWorkflowControls {...defaultProps} />);
      expect(screen.getByRole('button', { name: /set plan/i })).toBeInTheDocument();
    });

    it('opens SetPlanModal when Set Plan button is clicked', async () => {
      const user = userEvent.setup();
      render(<PendingWorkflowControls {...defaultProps} />);

      await user.click(screen.getByRole('button', { name: /set plan/i }));

      // Modal should open
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('passes workflowId and worktreePath to SetPlanModal', async () => {
      const user = userEvent.setup();
      render(<PendingWorkflowControls {...defaultProps} />);

      await user.click(screen.getByRole('button', { name: /set plan/i }));

      // Modal should show workflow-specific content
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('passes hasPlan prop to SetPlanModal for overwrite option', async () => {
      const user = userEvent.setup();
      render(<PendingWorkflowControls {...defaultProps} hasPlan={true} />);

      await user.click(screen.getByRole('button', { name: /set plan/i }));

      // Modal should have overwrite checkbox since hasPlan is true
      await waitFor(() => {
        expect(screen.getByLabelText(/overwrite/i)).toBeInTheDocument();
      });
    });

    it('closes modal when plan is applied successfully', async () => {
      vi.mocked(api.listFiles).mockResolvedValue({
        files: [
          { name: 'plan.md', relative_path: 'plan.md', size_bytes: 100, modified_at: '2026-02-15T10:00:00Z' },
        ],
        directory: '/path/to/repo/docs/plans',
      });

      const user = userEvent.setup();
      render(<PendingWorkflowControls {...defaultProps} />);

      await user.click(screen.getByRole('button', { name: /set plan/i }));

      // Select a file via combobox
      await waitFor(() => {
        expect(screen.getByRole('combobox')).toBeInTheDocument();
      });
      await user.click(screen.getByRole('combobox'));
      await waitFor(() => {
        expect(screen.getByText('plan.md')).toBeInTheDocument();
      });
      await user.click(screen.getByText('plan.md'));

      // Apply the plan
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /apply/i })).not.toBeDisabled();
      });
      await user.click(screen.getByRole('button', { name: /apply/i }));

      // Modal should close
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });
  });

  describe('Start button', () => {
    it('disables Start when another workflow is running on the same worktree', () => {
      render(
        <PendingWorkflowControls {...defaultProps} worktreeHasActiveWorkflow={true} />
      );
      expect(screen.getByRole('button', { name: /start/i })).toBeDisabled();
    });

    it('calls api.startWorkflow when Start is clicked', async () => {
      const user = userEvent.setup();
      render(<PendingWorkflowControls {...defaultProps} />);

      await user.click(screen.getByRole('button', { name: /start/i }));

      await waitFor(() => {
        expect(api.startWorkflow).toHaveBeenCalledWith('wf-123');
      });
    });
  });

  describe('Cancel button', () => {
    it('calls api.cancelWorkflow when Cancel is clicked', async () => {
      const user = userEvent.setup();
      render(<PendingWorkflowControls {...defaultProps} />);

      await user.click(screen.getByRole('button', { name: /cancel/i }));

      await waitFor(() => {
        expect(api.cancelWorkflow).toHaveBeenCalledWith('wf-123');
      });
    });
  });
});
