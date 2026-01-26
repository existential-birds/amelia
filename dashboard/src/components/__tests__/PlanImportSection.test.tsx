/**
 * @fileoverview Tests for PlanImportSection component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PlanImportSection } from '../PlanImportSection';
import { api, ApiError } from '@/api/client';

// Mock the API client
vi.mock('@/api/client', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/api/client')>();
  return {
    ...mod,
    api: { readFile: vi.fn() },
  };
});

describe('PlanImportSection', () => {
  const defaultProps = {
    onPlanChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders collapsible section with "External Plan" header', () => {
      render(<PlanImportSection {...defaultProps} />);
      expect(screen.getByText(/external plan/i)).toBeInTheDocument();
    });

    it('renders collapsed by default', () => {
      render(<PlanImportSection {...defaultProps} />);
      // Content should not be visible when collapsed
      expect(screen.queryByPlaceholderText(/relative path/i)).not.toBeInTheDocument();
    });

    it('expands when clicking the trigger', async () => {
      const user = userEvent.setup();
      render(<PlanImportSection {...defaultProps} />);

      await user.click(screen.getByText(/external plan/i));

      // Content should now be visible
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/relative path/i)).toBeInTheDocument();
      });
    });

    it('renders with defaultExpanded prop', () => {
      render(<PlanImportSection {...defaultProps} defaultExpanded />);
      expect(screen.getByPlaceholderText(/relative path/i)).toBeInTheDocument();
    });
  });

  describe('input modes', () => {
    it('shows "File Path" mode by default', () => {
      render(<PlanImportSection {...defaultProps} defaultExpanded />);

      // File path input should be visible
      expect(screen.getByPlaceholderText(/relative path/i)).toBeInTheDocument();
      // Textarea should not be visible
      expect(screen.queryByPlaceholderText(/paste.*plan.*markdown/i)).not.toBeInTheDocument();
    });

    it('switches to "Paste Content" mode when toggled', async () => {
      const user = userEvent.setup();
      render(<PlanImportSection {...defaultProps} defaultExpanded />);

      // Click the "Paste" toggle
      await user.click(screen.getByRole('radio', { name: /paste/i }));

      // Textarea should be visible
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/paste.*plan.*markdown/i)).toBeInTheDocument();
      });
      // File path input should not be visible
      expect(screen.queryByPlaceholderText(/relative path/i)).not.toBeInTheDocument();
    });

    it('switches back to "File Path" mode', async () => {
      const user = userEvent.setup();
      render(<PlanImportSection {...defaultProps} defaultExpanded />);

      // Switch to Paste
      await user.click(screen.getByRole('radio', { name: /paste/i }));
      // Switch back to File
      await user.click(screen.getByRole('radio', { name: /file/i }));

      // File path input should be visible again
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/relative path/i)).toBeInTheDocument();
      });
    });
  });

  describe('file path input', () => {
    it('calls onPlanChange with plan_file when path is entered', async () => {
      const user = userEvent.setup();
      const onPlanChange = vi.fn();
      render(<PlanImportSection onPlanChange={onPlanChange} defaultExpanded />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');

      await waitFor(() => {
        expect(onPlanChange).toHaveBeenLastCalledWith({
          plan_file: 'docs/plan.md',
          plan_content: undefined,
        });
      });
    });

    it('calls onPlanChange with undefined when path is cleared', async () => {
      const user = userEvent.setup();
      const onPlanChange = vi.fn();
      render(<PlanImportSection onPlanChange={onPlanChange} defaultExpanded />);

      const input = screen.getByPlaceholderText(/relative path/i);
      await user.type(input, 'docs/plan.md');
      await user.clear(input);

      await waitFor(() => {
        expect(onPlanChange).toHaveBeenLastCalledWith({
          plan_file: undefined,
          plan_content: undefined,
        });
      });
    });
  });

  describe('paste content input', () => {
    it('calls onPlanChange with plan_content when content is pasted', async () => {
      const user = userEvent.setup();
      const onPlanChange = vi.fn();
      render(<PlanImportSection onPlanChange={onPlanChange} defaultExpanded />);

      // Switch to paste mode
      await user.click(screen.getByRole('radio', { name: /paste/i }));

      const textarea = screen.getByPlaceholderText(/paste.*plan.*markdown/i);
      await user.type(textarea, '# Plan\n\n## Goal\nTest goal');

      await waitFor(() => {
        expect(onPlanChange).toHaveBeenLastCalledWith({
          plan_file: undefined,
          plan_content: '# Plan\n\n## Goal\nTest goal',
        });
      });
    });

    it('shows plan preview when valid content is entered', async () => {
      const user = userEvent.setup();
      render(<PlanImportSection {...defaultProps} defaultExpanded />);

      // Switch to paste mode
      await user.click(screen.getByRole('radio', { name: /paste/i }));

      const markdown = `# Plan

## Goal

Implement user authentication.

## Tasks

### Task 1: Create login form
### Task 2: Add validation
`;
      const textarea = screen.getByPlaceholderText(/paste.*plan.*markdown/i);
      await user.type(textarea, markdown);

      // Preview should show extracted info (in the preview card, not textarea)
      await waitFor(() => {
        const preview = screen.getByTestId('plan-preview');
        expect(preview).toHaveTextContent(/implement user authentication/i);
        expect(preview).toHaveTextContent(/2 tasks/i);
      });
    });
  });

  describe('drag and drop', () => {
    /**
     * Create a mock markdown file with File.text() support.
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

    it('accepts dropped .md files and populates content', async () => {
      const onPlanChange = vi.fn();
      render(<PlanImportSection onPlanChange={onPlanChange} defaultExpanded />);

      // Switch to paste mode to enable drop target
      const user = userEvent.setup();
      await user.click(screen.getByRole('radio', { name: /paste/i }));

      const dropZone = screen.getByTestId('plan-import-drop-zone');
      const content = '# Plan\n\n## Goal\n\nTest goal';
      const file = createMockMarkdownFile(content, 'plan.md');

      fireEvent.drop(dropZone, {
        dataTransfer: { files: [file], types: ['Files'] },
      });

      await waitFor(() => {
        expect(onPlanChange).toHaveBeenLastCalledWith({
          plan_file: undefined,
          plan_content: content,
        });
      });
    });

    it('shows visual feedback during drag over', async () => {
      const user = userEvent.setup();
      render(<PlanImportSection {...defaultProps} defaultExpanded />);
      await user.click(screen.getByRole('radio', { name: /paste/i }));

      const dropZone = screen.getByTestId('plan-import-drop-zone');

      fireEvent.dragOver(dropZone);

      await waitFor(() => {
        expect(dropZone).toHaveClass('border-primary');
      });
    });
  });

  describe('error display', () => {
    it('displays error message when provided', () => {
      render(
        <PlanImportSection
          {...defaultProps}
          defaultExpanded
          error="Invalid plan format"
        />
      );

      expect(screen.getByText(/invalid plan format/i)).toBeInTheDocument();
    });

    it('clears error when error prop is removed', () => {
      const { rerender } = render(
        <PlanImportSection
          {...defaultProps}
          defaultExpanded
          error="Invalid plan format"
        />
      );

      expect(screen.getByText(/invalid plan format/i)).toBeInTheDocument();

      rerender(<PlanImportSection {...defaultProps} defaultExpanded />);

      expect(screen.queryByText(/invalid plan format/i)).not.toBeInTheDocument();
    });
  });

  describe('plan preview', () => {
    it('shows preview card when plan has content', async () => {
      const user = userEvent.setup();
      render(<PlanImportSection {...defaultProps} defaultExpanded />);
      await user.click(screen.getByRole('radio', { name: /paste/i }));

      const markdown = `## Goal

Add new feature.

## Key Files

- src/main.ts

## Tasks

### Task 1: First
### Task 2: Second
### Task 3: Third
`;
      const textarea = screen.getByPlaceholderText(/paste.*plan.*markdown/i);
      await user.type(textarea, markdown);

      await waitFor(() => {
        const preview = screen.getByTestId('plan-preview');
        expect(preview).toHaveTextContent(/add new feature/i);
        expect(preview).toHaveTextContent(/3 tasks/i);
        expect(preview).toHaveTextContent(/src\/main\.ts/i);
      });
    });

    it('does not show preview card when content is empty', () => {
      render(<PlanImportSection {...defaultProps} defaultExpanded />);

      // No preview should be visible
      expect(screen.queryByTestId('plan-preview')).not.toBeInTheDocument();
    });
  });

  describe('file preview', () => {
    const planContent = '## Goal\nBuild feature X\n\n## Tasks\n### Task 1\nDo thing\n### Task 2\nDo other thing\n\n## Key Files\n- src/foo.ts\n';

    beforeEach(() => {
      vi.mocked(api.readFile).mockResolvedValue({ content: planContent, filename: 'plan.md' });
    });

    it('shows Preview button when worktreePath provided and file path entered', async () => {
      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), 'docs/plan.md');
      expect(screen.getByRole('button', { name: /preview/i })).toBeInTheDocument();
    });

    it('does not show Preview button when worktreePath not provided', async () => {
      const user = userEvent.setup();
      render(<PlanImportSection onPlanChange={vi.fn()} defaultExpanded />);

      await user.type(screen.getByPlaceholderText(/relative path/i), 'docs/plan.md');
      expect(screen.queryByRole('button', { name: /preview/i })).not.toBeInTheDocument();
    });

    it('disables Preview button when file path is empty', () => {
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
        />
      );

      const previewBtn = screen.getByRole('button', { name: /preview/i });
      expect(previewBtn).toBeDisabled();
    });

    it('calls api.readFile with resolved absolute path on Preview click', async () => {
      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /preview/i }));

      expect(api.readFile).toHaveBeenCalledWith('/path/to/repo/docs/plan.md');
    });

    it('uses filePath directly when it starts with /', async () => {
      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), '/absolute/path/plan.md');
      await user.click(screen.getByRole('button', { name: /preview/i }));

      expect(api.readFile).toHaveBeenCalledWith('/absolute/path/plan.md');
    });

    it('shows plan preview card after successful file read', async () => {
      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /preview/i }));

      await waitFor(() => {
        expect(screen.getByTestId('plan-preview')).toBeInTheDocument();
      });
      expect(screen.getByText(/build feature x/i)).toBeInTheDocument();
      expect(screen.getByText('2 tasks')).toBeInTheDocument();
    });

    it('shows inline error when file not found', async () => {
      vi.mocked(api.readFile).mockRejectedValue(
        new ApiError('File not found', 'NOT_FOUND', 404)
      );

      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), 'missing.md');
      await user.click(screen.getByRole('button', { name: /preview/i }));

      await waitFor(() => {
        expect(screen.getByText('File not found')).toBeInTheDocument();
      });
    });

    it('shows error when file is empty', async () => {
      vi.mocked(api.readFile).mockResolvedValue({ content: '', filename: 'empty.md' });

      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), 'empty.md');
      await user.click(screen.getByRole('button', { name: /preview/i }));

      await waitFor(() => {
        expect(screen.getByText(/plan file is empty/i)).toBeInTheDocument();
      });
    });

    it('clears preview and error when file path changes', async () => {
      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
        />
      );

      // First, get a preview
      await user.type(screen.getByPlaceholderText(/relative path/i), 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /preview/i }));
      await waitFor(() => {
        expect(screen.getByTestId('plan-preview')).toBeInTheDocument();
      });

      // Change path — preview should clear
      await user.type(screen.getByPlaceholderText(/relative path/i), '-v2');
      expect(screen.queryByTestId('plan-preview')).not.toBeInTheDocument();
    });
  });
});
