/**
 * @fileoverview Tests for QuickShotModal functionality.
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
    getConfig: vi.fn().mockResolvedValue({ working_dir: '/tmp/repo', max_concurrent: 5 }),
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

  it('should call api.createWorkflow with plan_now=true for Plan & Queue button', async () => {
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

  it('should call api.createWorkflow with start=true for Start button', async () => {
    const user = userEvent.setup();
    render(<QuickShotModal {...defaultProps} />);

    await fillRequiredFields();

    const startButton = screen.getByRole('button', { name: /^start$/i });
    await user.click(startButton);

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

  it('should close modal after successful Queue submission', async () => {
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
});

describe('QuickShotModal Import Zone', () => {
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
    vi.mocked(api.getConfig).mockResolvedValue({ working_dir: '/tmp/repo', max_concurrent: 5 });
    vi.mocked(api.readFile).mockResolvedValue({
      content: '# Test Design\n\n## Problem\n\nTest problem.',
      filename: 'test-design.md',
    });
  });

  it('renders drop zone for design doc import', () => {
    render(<QuickShotModal {...defaultProps} />);

    expect(screen.getByText(/drop design doc here/i)).toBeInTheDocument();
  });

  it('populates form fields when importing via drag-drop', async () => {
    render(<QuickShotModal {...defaultProps} />);

    const dropZone = screen
      .getByText(/drop design doc here/i)
      .closest('[data-slot="card"]');

    const content = '# Test Design\n\n## Problem\n\nTest problem.';
    const file = new File([content], 'test-design.md', {
      type: 'text/markdown',
    });
    file.text = () => Promise.resolve(content);

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
    const { toast } = await import('sonner');
    render(<QuickShotModal {...defaultProps} />);

    const dropZone = screen.getByText(/drop design doc here/i).closest('div');

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
    const dropZone = screen
      .getByText(/drop design doc here/i)
      .closest('[data-slot="card"]');

    // Create file with content that can be read
    const content = '# My Design Doc\n\nContent here.';
    const file = new File([content], 'my-design.md', {
      type: 'text/markdown',
    });

    // Define text() method on the file (not available in jsdom by default)
    file.text = () => Promise.resolve(content);

    const dataTransfer = { files: [file], types: ['Files'] };
    expect(dropZone).toBeInTheDocument();
    fireEvent.drop(dropZone, { dataTransfer });

    // Filename is displayed in a span element, not an input
    await waitFor(() => {
      expect(screen.getByText('my-design.md')).toBeInTheDocument();
    });
  });
});

describe('QuickShotModal Config Integration', () => {
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
    vi.mocked(api.getConfig).mockResolvedValue({ working_dir: '/tmp/repo', max_concurrent: 5 });
  });

  it('pre-fills worktree path from server config', async () => {
    render(<QuickShotModal {...defaultProps} />);

    await waitFor(() => {
      const worktreeInput = screen.getByLabelText(/worktree path/i);
      expect(worktreeInput).toHaveValue('/tmp/repo');
    });
  });
});
