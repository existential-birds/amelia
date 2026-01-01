import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { UsageCard } from './UsageCard';
import { createMockTokenSummary } from '@/__tests__/fixtures';

describe('UsageCard', () => {
  describe('rendering with token usage data', () => {
    it('renders the USAGE header', () => {
      const tokenUsage = createMockTokenSummary();
      render(<UsageCard tokenUsage={tokenUsage} />);

      expect(screen.getByText('USAGE')).toBeInTheDocument();
    });

    it('renders the summary line with totals', () => {
      const tokenUsage = createMockTokenSummary({
        total_cost_usd: 0.42,
        total_input_tokens: 13700,
        total_output_tokens: 3000,
        total_duration_ms: 154000,
        total_turns: 12,
      });
      render(<UsageCard tokenUsage={tokenUsage} />);

      // Check summary line content
      expect(screen.getByText('$0.42')).toBeInTheDocument();
      expect(screen.getByText('16.7K tokens')).toBeInTheDocument();
      expect(screen.getByText('2m 34s')).toBeInTheDocument();
      expect(screen.getByText('12 turns')).toBeInTheDocument();
    });

    it('renders agent breakdown table with headers', () => {
      const tokenUsage = createMockTokenSummary();
      render(<UsageCard tokenUsage={tokenUsage} />);

      expect(screen.getByRole('table')).toBeInTheDocument();
      expect(screen.getByText('Agent')).toBeInTheDocument();
      expect(screen.getByText('Model')).toBeInTheDocument();
      expect(screen.getByText('Input')).toBeInTheDocument();
      expect(screen.getByText('Output')).toBeInTheDocument();
      expect(screen.getByText('Cache')).toBeInTheDocument();
      expect(screen.getByText('Cost')).toBeInTheDocument();
      expect(screen.getByText('Time')).toBeInTheDocument();
    });

    it('renders a row for each agent in the breakdown', () => {
      const tokenUsage = createMockTokenSummary();
      render(<UsageCard tokenUsage={tokenUsage} />);

      const rows = screen.getAllByRole('row');
      // Header row + 3 agent rows
      expect(rows).toHaveLength(4);

      // Check agent names are present
      expect(screen.getByText('architect')).toBeInTheDocument();
      expect(screen.getByText('developer')).toBeInTheDocument();
      expect(screen.getByText('reviewer')).toBeInTheDocument();
    });

    it('formats agent token values correctly', () => {
      const tokenUsage = createMockTokenSummary();
      render(<UsageCard tokenUsage={tokenUsage} />);

      // Architect row: claude-sonnet-4-20250514, 2.1K input, 500 output, 1.8K cache, $0.08, 15s
      const architectRow = screen.getByText('architect').closest('tr');
      expect(architectRow).toBeInTheDocument();
      expect(
        within(architectRow!).getByText('claude-sonnet-4-20250514')
      ).toBeInTheDocument();
      expect(within(architectRow!).getByText('2.1K')).toBeInTheDocument();
      expect(within(architectRow!).getByText('500')).toBeInTheDocument();
      expect(within(architectRow!).getByText('1.8K')).toBeInTheDocument();
      expect(within(architectRow!).getByText('$0.08')).toBeInTheDocument();
      expect(within(architectRow!).getByText('15s')).toBeInTheDocument();
    });

    it('formats developer row values correctly', () => {
      const tokenUsage = createMockTokenSummary();
      render(<UsageCard tokenUsage={tokenUsage} />);

      // Developer row: 8.4K input, 2.1K output, 6.2K cache, $0.28, 1m 37s
      const developerRow = screen.getByText('developer').closest('tr');
      expect(developerRow).toBeInTheDocument();
      expect(within(developerRow!).getByText('8.4K')).toBeInTheDocument();
      expect(within(developerRow!).getByText('2.1K')).toBeInTheDocument();
      expect(within(developerRow!).getByText('6.2K')).toBeInTheDocument();
      expect(within(developerRow!).getByText('$0.28')).toBeInTheDocument();
      expect(within(developerRow!).getByText('1m 37s')).toBeInTheDocument();
    });
  });

  describe('null token usage', () => {
    it('returns null when tokenUsage is null', () => {
      const { container } = render(<UsageCard tokenUsage={null} />);
      expect(container.firstChild).toBeNull();
    });

    it('returns null when tokenUsage is undefined', () => {
      const { container } = render(<UsageCard tokenUsage={undefined} />);
      expect(container.firstChild).toBeNull();
    });
  });

  describe('empty breakdown', () => {
    it('renders summary but no table rows when breakdown is empty', () => {
      const tokenUsage = createMockTokenSummary({
        breakdown: [],
        total_cost_usd: 0,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_duration_ms: 0,
        total_turns: 0,
      });
      render(<UsageCard tokenUsage={tokenUsage} />);

      expect(screen.getByText('USAGE')).toBeInTheDocument();
      expect(screen.getByText('$0.00')).toBeInTheDocument();
      expect(screen.getByText('0 tokens')).toBeInTheDocument();

      // Table should still have header row
      const rows = screen.getAllByRole('row');
      expect(rows).toHaveLength(1); // Just header row
    });
  });

  describe('custom className', () => {
    it('applies custom className to the card', () => {
      const tokenUsage = createMockTokenSummary();
      const { container } = render(
        <UsageCard tokenUsage={tokenUsage} className="custom-class" />
      );

      const card = container.querySelector('[data-slot="usage-card"]');
      expect(card).toHaveClass('custom-class');
    });
  });

  describe('accessibility', () => {
    it('has accessible table structure', () => {
      const tokenUsage = createMockTokenSummary();
      render(<UsageCard tokenUsage={tokenUsage} />);

      const table = screen.getByRole('table');
      expect(table).toBeInTheDocument();

      // Check for columnheaders
      const columnHeaders = screen.getAllByRole('columnheader');
      expect(columnHeaders).toHaveLength(7);
    });

    it('has proper heading hierarchy', () => {
      const tokenUsage = createMockTokenSummary();
      render(<UsageCard tokenUsage={tokenUsage} />);

      // USAGE should be in an h3
      const heading = screen.getByRole('heading', { level: 3 });
      expect(heading).toHaveTextContent('USAGE');
    });
  });
});
