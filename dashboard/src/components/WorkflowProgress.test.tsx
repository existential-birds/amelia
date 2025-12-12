import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowProgress } from './WorkflowProgress';

describe('WorkflowProgress', () => {
  describe('percentage calculation', () => {
    it.each([
      { completed: 0, total: 5, expectedPct: '0%', expectedStages: '0 of 5 stages' },
      { completed: 1, total: 5, expectedPct: '20%', expectedStages: '1 of 5 stages' },
      { completed: 2, total: 5, expectedPct: '40%', expectedStages: '2 of 5 stages' },
      { completed: 3, total: 4, expectedPct: '75%', expectedStages: '3 of 4 stages' },
      { completed: 5, total: 5, expectedPct: '100%', expectedStages: '5 of 5 stages' },
      { completed: 1, total: 3, expectedPct: '33%', expectedStages: '1 of 3 stages' },
      { completed: 2, total: 3, expectedPct: '67%', expectedStages: '2 of 3 stages' },
    ])(
      '$completed/$total = $expectedPct',
      ({ completed, total, expectedPct, expectedStages }) => {
        render(<WorkflowProgress completed={completed} total={total} />);

        expect(screen.getByText(expectedPct)).toBeInTheDocument();
        expect(screen.getByText(expectedStages)).toBeInTheDocument();
      }
    );

    it('handles division by zero gracefully', () => {
      render(<WorkflowProgress completed={0} total={0} />);

      expect(screen.getByText('0%')).toBeInTheDocument();
      expect(screen.getByText('0 of 0 stages')).toBeInTheDocument();
    });
  });

  describe('completion state', () => {
    it('marks as incomplete when stages remain', () => {
      render(<WorkflowProgress completed={4} total={5} />);
      // Find the progress bar element by its ARIA role
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar.parentElement).not.toHaveAttribute('data-complete', 'true');
    });

    it('marks as complete when all stages done', () => {
      render(<WorkflowProgress completed={5} total={5} />);
      // Find the progress bar element by its ARIA role
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar.parentElement).toHaveAttribute('data-complete', 'true');
    });

    it('does not mark 0/0 as complete', () => {
      render(<WorkflowProgress completed={0} total={0} />);
      // Find the progress bar element by its ARIA role
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar.parentElement).not.toHaveAttribute('data-complete', 'true');
    });
  });
});
