import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DashboardSidebar } from './DashboardSidebar';
import { SidebarProvider } from '@/components/ui/sidebar';

// Mock the workflow store
vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn((selector) => {
    const state = { isConnected: true };
    return selector(state);
  }),
}));

// Mock the demo mode hook
vi.mock('@/hooks/useDemoMode', () => ({
  useDemoMode: vi.fn(() => ({ isDemo: false, demoType: null })),
}));

const renderSidebar = (open = true) => {
  return render(
    <MemoryRouter>
      <SidebarProvider defaultOpen={open}>
        <DashboardSidebar />
      </SidebarProvider>
    </MemoryRouter>
  );
};

describe('DashboardSidebar Accessibility', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('connection status has proper ARIA attributes when expanded', () => {
    renderSidebar(true);
    // Should have role="status"
    const status = screen.getByRole('status');
    expect(status).toBeInTheDocument();
    // In expanded mode, it should contain text "Connected"
    expect(status).toHaveTextContent('Connected');
  });

  it('connection status has proper ARIA attributes when collapsed', () => {
    renderSidebar(false);
    // Should have role="status"
    const status = screen.getByRole('status');
    expect(status).toBeInTheDocument();
    // In collapsed mode, it should have aria-label since text is hidden
    expect(status).toHaveAttribute('aria-label', 'Connection status: Connected');
  });
});
