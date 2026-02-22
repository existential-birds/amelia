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
    api: {
      readFile: vi.fn(),
      listFiles: vi.fn().mockResolvedValue({ files: [], directory: '' }),
    },
  };
});

describe('PlanImportSection', () => {
  const defaultProps = {
    onPlanChange: vi.fn(),
    // Disable combobox for most tests to preserve existing text-input behavior
    planOutputDir: undefined as string | undefined,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // Reset listFiles default
    vi.mocked(api.listFiles).mockResolvedValue({ files: [], directory: '' });
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
      render(<PlanImportSection onPlanChange={onPlanChange} defaultExpanded planOutputDir={undefined} />);

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
      render(<PlanImportSection onPlanChange={onPlanChange} defaultExpanded planOutputDir={undefined} />);

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
      render(<PlanImportSection onPlanChange={onPlanChange} defaultExpanded planOutputDir={undefined} />);

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
      render(<PlanImportSection onPlanChange={onPlanChange} defaultExpanded planOutputDir={undefined} />);

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

  describe('file preview (text input fallback)', () => {
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
          planOutputDir={undefined}
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), 'docs/plan.md');
      expect(screen.getByRole('button', { name: /preview/i })).toBeInTheDocument();
    });

    it('does not show Preview button when worktreePath not provided', async () => {
      const user = userEvent.setup();
      render(<PlanImportSection onPlanChange={vi.fn()} defaultExpanded planOutputDir={undefined} />);

      await user.type(screen.getByPlaceholderText(/relative path/i), 'docs/plan.md');
      expect(screen.queryByRole('button', { name: /preview/i })).not.toBeInTheDocument();
    });

    it('disables Preview button when file path is empty', () => {
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
          planOutputDir={undefined}
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
          planOutputDir={undefined}
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), 'docs/plan.md');
      await user.click(screen.getByRole('button', { name: /preview/i }));

      expect(api.readFile).toHaveBeenCalledWith('/path/to/repo/docs/plan.md', '/path/to/repo');
    });

    it('uses filePath directly when it starts with /', async () => {
      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
          planOutputDir={undefined}
        />
      );

      await user.type(screen.getByPlaceholderText(/relative path/i), '/absolute/path/plan.md');
      await user.click(screen.getByRole('button', { name: /preview/i }));

      expect(api.readFile).toHaveBeenCalledWith('/absolute/path/plan.md', '/path/to/repo');
    });

    it('shows plan preview card after successful file read', async () => {
      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/path/to/repo"
          planOutputDir={undefined}
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
          planOutputDir={undefined}
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
          planOutputDir={undefined}
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
          planOutputDir={undefined}
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

  describe('file combobox', () => {
    const mockFiles = [
      { name: 'plan-1.md', relative_path: 'plan-1.md', size_bytes: 100, modified_at: '2026-02-15T10:00:00Z' },
      { name: 'plan-2.md', relative_path: 'plan-2.md', size_bytes: 200, modified_at: '2026-02-14T08:00:00Z' },
    ];

    it('fetches file list on mount when worktreePath and planOutputDir are provided', async () => {
      vi.mocked(api.listFiles).mockResolvedValue({
        files: mockFiles,
        directory: '/tmp/project/docs/plans',
      });

      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/tmp/project"
          planOutputDir="docs/plans"
        />
      );

      await waitFor(() => {
        expect(api.listFiles).toHaveBeenCalledWith('docs/plans', '*.md', '/tmp/project');
      });
    });

    it('shows combobox trigger instead of text input when planOutputDir is set', async () => {
      vi.mocked(api.listFiles).mockResolvedValue({
        files: mockFiles,
        directory: '/tmp/project/docs/plans',
      });

      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/tmp/project"
          planOutputDir="docs/plans"
        />
      );

      // Should show combobox, not text input
      expect(screen.queryByPlaceholderText(/relative path/i)).not.toBeInTheDocument();
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('shows empty state when no files found', async () => {
      vi.mocked(api.listFiles).mockResolvedValue({
        files: [],
        directory: '/tmp/project/docs/plans',
      });

      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/tmp/project"
          planOutputDir="docs/plans"
        />
      );

      // Open combobox
      await user.click(screen.getByRole('combobox'));

      await waitFor(() => {
        expect(screen.getByText(/no .md files/i)).toBeInTheDocument();
      });
    });

    it('shows file list when combobox is opened', async () => {
      vi.mocked(api.listFiles).mockResolvedValue({
        files: mockFiles,
        directory: '/tmp/project/docs/plans',
      });

      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/tmp/project"
          planOutputDir="docs/plans"
        />
      );

      // Wait for files to load
      await waitFor(() => {
        expect(api.listFiles).toHaveBeenCalled();
      });

      // Open combobox
      await user.click(screen.getByRole('combobox'));

      await waitFor(() => {
        expect(screen.getByText('plan-1.md')).toBeInTheDocument();
        expect(screen.getByText('plan-2.md')).toBeInTheDocument();
      });
    });

    it('calls onPlanChange when a file is selected from combobox', async () => {
      vi.mocked(api.listFiles).mockResolvedValue({
        files: mockFiles,
        directory: '/tmp/project/docs/plans',
      });
      vi.mocked(api.readFile).mockResolvedValue({
        content: '## Goal\nTest\n\n## Tasks\n### Task 1\nDo it\n',
        filename: 'plan-1.md',
      });

      const onPlanChange = vi.fn();
      const user = userEvent.setup();
      render(
        <PlanImportSection
          onPlanChange={onPlanChange}
          defaultExpanded
          worktreePath="/tmp/project"
          planOutputDir="docs/plans"
        />
      );

      // Wait for files to load
      await waitFor(() => {
        expect(api.listFiles).toHaveBeenCalled();
      });

      // Open combobox and select a file
      await user.click(screen.getByRole('combobox'));
      await waitFor(() => {
        expect(screen.getByText('plan-1.md')).toBeInTheDocument();
      });
      await user.click(screen.getByText('plan-1.md'));

      await waitFor(() => {
        expect(onPlanChange).toHaveBeenLastCalledWith({
          plan_file: 'docs/plans/plan-1.md',
          plan_content: undefined,
        });
      });
    });

    it('falls back to text input when planOutputDir is not provided', () => {
      render(
        <PlanImportSection
          onPlanChange={vi.fn()}
          defaultExpanded
          worktreePath="/tmp/project"
          planOutputDir={undefined}
        />
      );

      expect(screen.getByPlaceholderText(/relative path/i)).toBeInTheDocument();
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });
  });
});
