/**
 * @fileoverview Tests for ProfileSelect component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { ProfileSelect } from '../ProfileSelect';
import { getProfiles, type Profile } from '@/api/settings';

// Mock the settings API
vi.mock('@/api/settings', () => ({
  getProfiles: vi.fn(),
}));

const mockProfiles: Profile[] = [
  {
    id: 'work',
    tracker: 'github',
    working_dir: '/work',
    plan_output_dir: '',
    plan_path_pattern: '',
    agents: {},
    is_active: true,
  },
  {
    id: 'personal',
    tracker: 'jira',
    working_dir: '/personal',
    plan_output_dir: '',
    plan_path_pattern: '',
    agents: {},
    is_active: false,
  },
];

describe('ProfileSelect', () => {
  const defaultProps = {
    value: '',
    onChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getProfiles).mockResolvedValue(mockProfiles);
  });

  describe('loading state', () => {
    it('disables select while loading', () => {
      // Don't resolve immediately to capture loading state
      vi.mocked(getProfiles).mockReturnValue(new Promise(() => {}));

      render(<ProfileSelect {...defaultProps} />);

      const combobox = screen.getByRole('combobox');
      expect(combobox).toBeDisabled();
    });
  });

  describe('rendering', () => {
    it('renders profiles after loading', async () => {
      render(<ProfileSelect {...defaultProps} />);

      // Wait for loading to complete
      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      // Open the select dropdown
      fireEvent.click(screen.getByRole('combobox'));

      // Check that profiles are rendered
      await waitFor(() => {
        expect(screen.getByText('work')).toBeInTheDocument();
        expect(screen.getByText('personal')).toBeInTheDocument();
      });
    });

    it('shows tracker type as secondary info', async () => {
      render(<ProfileSelect {...defaultProps} />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      fireEvent.click(screen.getByRole('combobox'));

      await waitFor(() => {
        expect(screen.getByText('github')).toBeInTheDocument();
        expect(screen.getByText('jira')).toBeInTheDocument();
      });
    });

    it('shows active indicator for active profile', async () => {
      render(<ProfileSelect {...defaultProps} />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      fireEvent.click(screen.getByRole('combobox'));

      await waitFor(() => {
        expect(screen.getByText('(active)')).toBeInTheDocument();
      });
    });

    it('renders "None" option for clearing selection', async () => {
      render(<ProfileSelect {...defaultProps} />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      fireEvent.click(screen.getByRole('combobox'));

      // Use getAllByText since "None" appears in both trigger and dropdown
      await waitFor(() => {
        const noneElements = screen.getAllByText('None (use server default)');
        expect(noneElements.length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  describe('selection', () => {
    it('calls onChange when profile selected', async () => {
      const onChange = vi.fn();

      render(<ProfileSelect {...defaultProps} onChange={onChange} />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      fireEvent.click(screen.getByRole('combobox'));

      await waitFor(() => {
        expect(screen.getByText('work')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('work'));

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith('work');
      });
    });

    it('calls onChange with empty string when "None" selected', async () => {
      const onChange = vi.fn();

      render(<ProfileSelect {...defaultProps} value="work" onChange={onChange} />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      fireEvent.click(screen.getByRole('combobox'));

      // Find the "None" option in the dropdown (not the trigger)
      await waitFor(() => {
        // The dropdown content has role="listbox"
        const listbox = screen.getByRole('listbox');
        const noneOption = within(listbox).getByText('None (use server default)');
        expect(noneOption).toBeInTheDocument();
      });

      const listbox = screen.getByRole('listbox');
      const noneOption = within(listbox).getByText('None (use server default)');
      fireEvent.click(noneOption);

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith('');
      });
    });

    it('displays selected profile value', async () => {
      render(<ProfileSelect {...defaultProps} value="work" />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      // The combobox should display the selected profile
      await waitFor(() => {
        expect(screen.getByRole('combobox')).toHaveTextContent('work');
      });
    });
  });

  describe('error handling', () => {
    it('shows error message when provided', async () => {
      render(<ProfileSelect {...defaultProps} error="Profile is required" />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      expect(screen.getByText('Profile is required')).toBeInTheDocument();
    });

    it('handles API error gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      vi.mocked(getProfiles).mockRejectedValue(new Error('Network error'));

      try {
        render(<ProfileSelect {...defaultProps} />);

        await waitFor(() => {
          expect(getProfiles).toHaveBeenCalled();
        });

        // Wait for the error to be processed - the component should still be functional
        await waitFor(() => {
          // The select should be enabled after loading fails
          expect(screen.getByRole('combobox')).not.toBeDisabled();
        });

        expect(consoleSpy).toHaveBeenCalledWith(
          'Failed to fetch profiles:',
          expect.any(Error)
        );
      } finally {
        consoleSpy.mockRestore();
      }
    });
  });

  describe('accessibility', () => {
    it('has proper label association', async () => {
      render(<ProfileSelect {...defaultProps} id="test-profile" />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      const combobox = screen.getByRole('combobox');
      expect(combobox).toHaveAttribute('id', 'test-profile');

      // Label should be associated
      expect(screen.getByText('Profile')).toBeInTheDocument();
    });

    it('shows aria-invalid when error present', async () => {
      render(<ProfileSelect {...defaultProps} error="Invalid selection" />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      const combobox = screen.getByRole('combobox');
      expect(combobox).toHaveAttribute('aria-invalid', 'true');
    });

    it('disables select when disabled prop is true', async () => {
      render(<ProfileSelect {...defaultProps} disabled />);

      await waitFor(() => {
        expect(getProfiles).toHaveBeenCalled();
      });

      const combobox = screen.getByRole('combobox');
      expect(combobox).toBeDisabled();
    });
  });
});
