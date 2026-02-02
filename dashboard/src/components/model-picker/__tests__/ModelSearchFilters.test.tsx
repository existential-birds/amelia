import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelSearchFilters } from '../ModelSearchFilters';

describe('ModelSearchFilters', () => {
  const defaultProps = {
    searchQuery: '',
    onSearchChange: vi.fn(),
    selectedCapabilities: [] as string[],
    onCapabilitiesChange: vi.fn(),
    selectedPriceTier: null as string | null,
    onPriceTierChange: vi.fn(),
    minContextSize: null as number | null,
    onMinContextChange: vi.fn(),
    onClearFilters: vi.fn(),
  };

  it('should render search input', () => {
    render(<ModelSearchFilters {...defaultProps} />);

    expect(screen.getByPlaceholderText(/search models/i)).toBeInTheDocument();
  });

  it('should call onSearchChange when typing', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(<ModelSearchFilters {...defaultProps} onSearchChange={onSearchChange} />);

    const input = screen.getByPlaceholderText(/search models/i);
    await user.type(input, 'c');

    // Component is controlled, so it calls onChange with the current value
    expect(onSearchChange).toHaveBeenCalledWith('c');
  });

  it('should render filter dropdowns', () => {
    render(<ModelSearchFilters {...defaultProps} />);

    // Verify all three filter dropdowns are rendered
    expect(screen.getByText('Capabilities')).toBeInTheDocument();
    expect(screen.getByText('All prices')).toBeInTheDocument();
    expect(screen.getByText('Context')).toBeInTheDocument();
  });

  it('should show active filter chips', () => {
    render(
      <ModelSearchFilters
        {...defaultProps}
        selectedCapabilities={['reasoning']}
        selectedPriceTier="budget"
      />
    );

    expect(screen.getByText('reasoning')).toBeInTheDocument();
    expect(screen.getByText('budget')).toBeInTheDocument();
  });

  it('should show clear filters button when filters active', () => {
    render(
      <ModelSearchFilters
        {...defaultProps}
        selectedCapabilities={['reasoning']}
      />
    );

    expect(screen.getByRole('button', { name: /clear filters/i })).toBeInTheDocument();
  });

  it('should not show clear filters button when no filters active', () => {
    render(<ModelSearchFilters {...defaultProps} />);

    expect(screen.queryByRole('button', { name: /clear filters/i })).not.toBeInTheDocument();
  });

  it('should call onClearFilters when clear button clicked', () => {
    const onClearFilters = vi.fn();
    render(
      <ModelSearchFilters
        {...defaultProps}
        selectedCapabilities={['reasoning']}
        onClearFilters={onClearFilters}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /clear filters/i }));

    expect(onClearFilters).toHaveBeenCalled();
  });
});
