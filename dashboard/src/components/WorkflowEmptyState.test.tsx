import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkflowEmptyState } from './WorkflowEmptyState';

describe('WorkflowEmptyState', () => {
  describe('variant configurations', () => {
    it.each([
      {
        variant: 'no-workflows' as const,
        expectedTitle: 'No Active Workflows',
        expectedDescription: /Start a new workflow/,
      },
      {
        variant: 'no-activity' as const,
        expectedTitle: 'No Activity Yet',
        expectedDescription: /Activity will appear here/,
      },
      {
        variant: 'no-results' as const,
        expectedTitle: 'No Results Found',
        expectedDescription: /Try adjusting your search/,
      },
      {
        variant: 'error' as const,
        expectedTitle: 'Something Went Wrong',
        expectedDescription: /An error occurred/,
      },
    ])(
      '$variant renders correct title and description',
      ({ variant, expectedTitle, expectedDescription }) => {
        render(<WorkflowEmptyState variant={variant} />);

        expect(screen.getByText(expectedTitle)).toBeInTheDocument();
        expect(screen.getByText(expectedDescription)).toBeInTheDocument();
      }
    );
  });

  describe('custom overrides', () => {
    it('allows custom title and description to override variant defaults', () => {
      render(
        <WorkflowEmptyState
          variant="no-workflows"
          title="Custom Title"
          description="Custom description text"
        />
      );

      expect(screen.getByText('Custom Title')).toBeInTheDocument();
      expect(screen.getByText('Custom description text')).toBeInTheDocument();
      expect(screen.queryByText('No Active Workflows')).not.toBeInTheDocument();
    });
  });

  describe('action button', () => {
    it('renders and triggers action when provided', async () => {
      const user = userEvent.setup();
      const onAction = vi.fn();

      render(
        <WorkflowEmptyState
          variant="no-workflows"
          action={{ label: 'New Workflow', onClick: onAction }}
        />
      );

      const button = screen.getByRole('button', { name: 'New Workflow' });
      await user.click(button);
      expect(onAction).toHaveBeenCalledTimes(1);
    });

    it('does not render button when action is not provided', () => {
      render(<WorkflowEmptyState variant="no-workflows" />);

      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });
  });
});
