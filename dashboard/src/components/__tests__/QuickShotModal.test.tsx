/**
 * @fileoverview Tests for QuickShotModal functionality.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QuickShotModal } from '../QuickShotModal';
import { api, ApiError } from '@/api/client';
import { toast } from 'sonner';

// Mock the API client
vi.mock('@/api/client', () => ({
  api: {
    createWorkflow: vi.fn(),
    getConfig: vi.fn().mockResolvedValue({ working_dir: '', max_concurrent: 5, active_profile: 'test' }),
    readFile: vi.fn().mockResolvedValue({
      content: '# Test Design\n\n## Problem\n\nTest problem.',
      filename: 'test-design.md',
    }),
    validatePath: vi.fn().mockResolvedValue({
      exists: true,
      is_git_repo: true,
      branch: 'main',
      repo_name: 'repo',
      has_changes: false,
      message: 'Git repository on branch main',
    }),
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
    vi.mocked(api.createWorkflow).mockResolvedValue({
      id: 'wf-123',
      status: 'pending',
      message: 'Workflow created',
    });
  });

  /**
   * Create a mock markdown file with File.text() support (not available in jsdom).
   */
  function createMockMarkdownFile(
    content: string,
    filename: string
  ): File & { text: () => Promise<string> } {
    const file = new File([content], filename, { type: 'text/markdown' });
    (file as File & { text: () => Promise<string> }).text = () =>
      Promise.resolve(content);
    return file as File & { text: () => Promise<string> };
  }

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

    it('disables all submit buttons when form is invalid', () => {
      render(<QuickShotModal {...defaultProps} />);

      // Form is initially invalid (empty required fields)
      expect(screen.getByRole('button', { name: /^queue$/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /plan.*queue/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /^start$/i })).toBeDisabled();
    });

    it('enables submit buttons when form is valid', async () => {
      render(<QuickShotModal {...defaultProps} />);

      await fillRequiredFields();

      expect(screen.getByRole('button', { name: /^queue$/i })).not.toBeDisabled();
      expect(screen.getByRole('button', { name: /plan.*queue/i })).not.toBeDisabled();
      expect(screen.getByRole('button', { name: /^start$/i })).not.toBeDisabled();
    });
  });

  describe('submission', () => {
    it('calls api.createWorkflow with start=false for Queue button', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      await fillRequiredFields();

      const queueButton = screen.getByRole('button', { name: /^queue$/i });
      await user.click(queueButton);

      await waitFor(() => {
        expect(api.createWorkflow).toHaveBeenCalledWith(
          expect.objectContaining({
            start: false,
            plan_now: false,
          })
        );
      });
    });

    it('calls api.createWorkflow with plan_now=true for Plan & Queue button', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      await fillRequiredFields();

      const planQueueButton = screen.getByRole('button', { name: /plan.*queue/i });
      await user.click(planQueueButton);

      await waitFor(() => {
        expect(api.createWorkflow).toHaveBeenCalledWith(
          expect.objectContaining({
            start: false,
            plan_now: true,
          })
        );
      });
    });

    it('calls api.createWorkflow with start=true and all fields on Start button click', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      await user.click(screen.getByRole('button', { name: /^start$/i }));

      await waitFor(() => {
        expect(api.createWorkflow).toHaveBeenCalledWith({
          issue_id: 'TASK-001',
          worktree_path: '/Users/me/repo',
          profile: undefined,
          task_title: 'Test title',
          task_description: undefined,
          start: true,
          plan_now: false,
          plan_file: undefined,
          plan_content: undefined,
        });
      });
    });

    it('shows success toast with workflow link and closes modal on success', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      vi.mocked(api.createWorkflow).mockResolvedValueOnce({
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
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });

    it('closes modal after successful Queue submission', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      render(<QuickShotModal open={true} onOpenChange={onOpenChange} />);

      await fillRequiredFields();

      const queueButton = screen.getByRole('button', { name: /^queue$/i });
      await user.click(queueButton);

      await waitFor(() => {
        expect(api.createWorkflow).toHaveBeenCalled();
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });

    it('closes modal after successful Plan & Queue submission', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      render(<QuickShotModal open={true} onOpenChange={onOpenChange} />);

      await fillRequiredFields();

      const planQueueButton = screen.getByRole('button', { name: /plan.*queue/i });
      await user.click(planQueueButton);

      await waitFor(() => {
        expect(api.createWorkflow).toHaveBeenCalled();
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });

    it('shows error toast on API error', async () => {
      const user = userEvent.setup();
      vi.mocked(api.createWorkflow).mockRejectedValueOnce(
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
      let resolvePromise: (value: { id: string; status: string; message: string }) => void;
      vi.mocked(api.createWorkflow).mockReturnValueOnce(
        new Promise((resolve) => {
          resolvePromise = resolve;
        })
      );

      render(<QuickShotModal {...defaultProps} />);

      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      await user.click(screen.getByRole('button', { name: /^start$/i }));

      // Wait for the launching state to appear
      await waitFor(() => {
        expect(screen.getByText(/launching/i)).toBeInTheDocument();
      });

      resolvePromise!({ id: 'wf-123', status: 'pending', message: 'ok' });
    });
  });

  describe('Import Zone', () => {
    beforeEach(() => {
      vi.mocked(api.getConfig).mockResolvedValue({ working_dir: '/tmp/repo', max_concurrent: 5, active_profile: 'test', active_profile_info: null });
      vi.mocked(api.readFile).mockResolvedValue({
        content: '# Test Design\n\n## Problem\n\nTest problem.',
        filename: 'test-design.md',
      });
    });

    it('renders drop zone for design doc import', () => {
      render(<QuickShotModal {...defaultProps} />);

      expect(screen.getByText(/drop or click to import design doc/i)).toBeInTheDocument();
    });

    it('populates form fields when importing via drag-drop', async () => {
      render(<QuickShotModal {...defaultProps} />);

      const dropZone = screen.getByTestId('import-zone');

      const content = '# Test Design\n\n## Problem\n\nTest problem.';
      const file = createMockMarkdownFile(content, 'test-design.md');

      const dataTransfer = { files: [file], types: ['Files'] };
      expect(dropZone).toBeInTheDocument();
      fireEvent.drop(dropZone, { dataTransfer });

      // Check form fields are populated
      await waitFor(() => {
        const titleInput = screen.getByLabelText(/task title/i);
        expect(titleInput).toHaveValue('Test');
      });
    });

    it('shows error toast for non-markdown files on drag-drop', async () => {
      render(<QuickShotModal {...defaultProps} />);

      const dropZone = screen.getByTestId('import-zone');

      const file = new File(['content'], 'test.txt', { type: 'text/plain' });
      const dataTransfer = { files: [file], types: ['Files'] };

      expect(dropZone).toBeInTheDocument();
      fireEvent.drop(dropZone, { dataTransfer });

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('.md'));
      });
    });

    it('shows filename in drop zone after successful drag-drop', async () => {
      render(<QuickShotModal {...defaultProps} />);

      // Get the Card element with the drop handler (parent of the inner content)
      const dropZone = screen.getByTestId('import-zone');

      const content = '# My Design Doc\n\nContent here.';
      const file = createMockMarkdownFile(content, 'my-design.md');

      const dataTransfer = { files: [file], types: ['Files'] };
      expect(dropZone).toBeInTheDocument();
      fireEvent.drop(dropZone, { dataTransfer });

      // Filename is displayed in a span element, not an input
      await waitFor(() => {
        expect(screen.getByText('my-design.md')).toBeInTheDocument();
      });
    });
  });

  describe('Config Integration', () => {
    it('pre-fills worktree path from server config', async () => {
      vi.mocked(api.getConfig).mockResolvedValue({ working_dir: '/tmp/repo', max_concurrent: 5, active_profile: 'test', active_profile_info: null });
      render(<QuickShotModal {...defaultProps} />);

      await waitFor(() => {
        const worktreeInput = screen.getByLabelText(/worktree path/i);
        expect(worktreeInput).toHaveValue('/tmp/repo');
      });
    });
  });

  describe('External Plan', () => {
    it('renders External Plan collapsible section', () => {
      render(<QuickShotModal {...defaultProps} />);
      expect(screen.getByText(/external plan/i)).toBeInTheDocument();
    });

    it('External Plan section is collapsed by default', () => {
      render(<QuickShotModal {...defaultProps} />);
      // The plan file input should not be visible when collapsed
      expect(screen.queryByPlaceholderText(/relative path to plan file/i)).not.toBeInTheDocument();
    });

    it('expands External Plan section when clicked', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      await user.click(screen.getByText(/external plan/i));

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/relative path to plan file/i)).toBeInTheDocument();
      });
    });

    it('disables Plan & Queue button when external plan is provided', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      // Fill required fields
      await fillRequiredFields();

      // Expand External Plan and add a plan file
      await user.click(screen.getByText(/external plan/i));
      const planInput = screen.getByPlaceholderText(/relative path to plan file/i);
      await user.type(planInput, 'docs/plan.md');

      // Plan & Queue should be disabled since we have an external plan
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /plan.*queue/i })).toBeDisabled();
      });

      // Queue and Start should still work
      expect(screen.getByRole('button', { name: /^queue$/i })).not.toBeDisabled();
      expect(screen.getByRole('button', { name: /^start$/i })).not.toBeDisabled();
    });

    it('passes plan_file to api.createWorkflow when provided', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      // Fill required fields
      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      // Expand External Plan and add a plan file
      await user.click(screen.getByText(/external plan/i));
      const planInput = screen.getByPlaceholderText(/relative path to plan file/i);
      await user.type(planInput, 'docs/plan.md');

      // Click Queue
      await user.click(screen.getByRole('button', { name: /^queue$/i }));

      await waitFor(() => {
        expect(api.createWorkflow).toHaveBeenCalledWith(
          expect.objectContaining({
            plan_file: 'docs/plan.md',
          })
        );
      });
    });

    it('passes plan_content to api.createWorkflow when pasting content', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      // Fill required fields
      await user.type(screen.getByLabelText(/task id/i), 'TASK-001');
      await user.type(screen.getByLabelText(/worktree path/i), '/Users/me/repo');
      await user.type(screen.getByLabelText(/task title/i), 'Test title');

      // Expand External Plan and switch to paste mode
      await user.click(screen.getByText(/external plan/i));
      await user.click(screen.getByRole('radio', { name: /paste/i }));

      const textarea = screen.getByPlaceholderText(/paste.*plan.*markdown/i);
      await user.type(textarea, '# My Plan');

      // Click Start
      await user.click(screen.getByRole('button', { name: /^start$/i }));

      await waitFor(() => {
        expect(api.createWorkflow).toHaveBeenCalledWith(
          expect.objectContaining({
            plan_content: '# My Plan',
          })
        );
      });
    });

    it('passes worktree_path to PlanImportSection for file preview', async () => {
      const user = userEvent.setup();
      render(<QuickShotModal {...defaultProps} />);

      // Fill worktree path field
      await user.type(screen.getByLabelText(/worktree path/i), '/test/repo');

      // Expand PlanImportSection and enter file path
      await user.click(screen.getByText(/external plan/i));
      await user.type(screen.getByPlaceholderText(/relative path/i), 'plan.md');

      // Preview button should be visible (only appears when worktreePath is provided)
      expect(screen.getByRole('button', { name: /preview/i })).toBeInTheDocument();
    });
  });
});
