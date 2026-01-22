import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// Mock the sidebar hook
const mockToggleSidebar = vi.fn();
vi.mock('@/components/ui/sidebar', () => ({
  useSidebar: () => ({ toggleSidebar: mockToggleSidebar }),
}));

// Mutable state for tests - must be declared before vi.mock
let mockIsConnected = true;

// Mock the workflow store with selector support
vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn((selector) => {
    const state = { isConnected: mockIsConnected };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

import { MobileCommandBar } from './MobileCommandBar';

describe('MobileCommandBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsConnected = true; // Reset to connected state
  });

  it('renders on mobile viewport with AMELIA branding', () => {
    render(<MobileCommandBar />);

    expect(screen.getByText(/A M E L I A/)).toBeInTheDocument();
  });

  it('calls toggleSidebar when sidebar trigger button is clicked', () => {
    render(<MobileCommandBar />);

    const sidebarButton = screen.getByRole('button', { name: 'Toggle sidebar' });
    fireEvent.click(sidebarButton);

    expect(mockToggleSidebar).toHaveBeenCalledTimes(1);
  });

  it('shows connected status when isConnected is true', () => {
    mockIsConnected = true;
    render(<MobileCommandBar />);

    const statusIndicator = screen.getByRole('status');
    expect(statusIndicator).toHaveClass('bg-[--status-running]');
    expect(statusIndicator).not.toHaveClass('bg-[--status-failed]');
  });

  it('shows disconnected status when isConnected is false', () => {
    mockIsConnected = false;
    render(<MobileCommandBar />);

    const statusIndicator = screen.getByRole('status');
    expect(statusIndicator).toHaveClass('bg-[--status-failed]');
    expect(statusIndicator).not.toHaveClass('bg-[--status-running]');
  });

  it('has correct accessibility attributes', () => {
    mockIsConnected = true;
    render(<MobileCommandBar />);

    // Verify sidebar button has correct aria-label
    const sidebarButton = screen.getByRole('button', { name: 'Toggle sidebar' });
    expect(sidebarButton).toHaveAttribute('aria-label', 'Toggle sidebar');

    // Verify status indicator has role="status" and appropriate aria-label
    const statusIndicator = screen.getByRole('status');
    expect(statusIndicator).toHaveAttribute('aria-label', 'Connected');
  });

  it('has correct accessibility attributes when disconnected', () => {
    mockIsConnected = false;
    render(<MobileCommandBar />);

    const statusIndicator = screen.getByRole('status');
    expect(statusIndicator).toHaveAttribute('aria-label', 'Disconnected');
  });
});
