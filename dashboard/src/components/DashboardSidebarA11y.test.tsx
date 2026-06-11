import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderSidebar } from '@/test/helpers';

vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn((selector) => {
    const state = { isConnected: true };
    return selector(state);
  }),
}));

vi.mock('@/hooks/useDemoMode', () => ({
  useDemoMode: vi.fn(() => ({ isDemo: false, demoType: null })),
}));

describe('DashboardSidebar Accessibility', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('connection status has proper ARIA attributes when expanded', () => {
    renderSidebar({ open: true });
    // getByRole throws if element not found, no need for toBeInTheDocument()
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Connected');
  });

  it('connection status has proper ARIA attributes when collapsed', () => {
    renderSidebar({ open: false });
    // getByRole throws if element not found, no need for toBeInTheDocument()
    const status = screen.getByRole('status');
    // In collapsed mode, it should have aria-label since text is hidden
    expect(status).toHaveAttribute('aria-label', 'Connection status: Connected');
  });
});
