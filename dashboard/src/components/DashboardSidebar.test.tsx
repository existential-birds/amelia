import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DashboardSidebar } from './DashboardSidebar';
import { SidebarProvider } from '@/components/ui/sidebar';
import { useDemoMode } from '@/hooks/useDemoMode';

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

const renderSidebar = (initialRoute = '/') => {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <SidebarProvider>
        <DashboardSidebar />
      </SidebarProvider>
    </MemoryRouter>
  );
};

describe('DashboardSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders branding', () => {
    renderSidebar();
    expect(screen.getByText('AMELIA')).toBeInTheDocument();
  });

  it.each([
    ['Active Jobs', '/workflows'],
    ['Past Runs', '/history'],
    ['Logs', '/logs'],
    ['Agent Prompts', '/prompts'],
  ])('renders %s navigation link to %s', (label, href) => {
    renderSidebar();
    const link = screen.getByRole('link', { name: new RegExp(label) });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', href);
  });

  it('renders section labels', () => {
    renderSidebar();
    expect(screen.getByText('WORKFLOWS')).toBeInTheDocument();
    expect(screen.getByText('TOOLS')).toBeInTheDocument();
    expect(screen.getByText('AGENT OPS')).toBeInTheDocument();
    expect(screen.getByText('USAGE')).toBeInTheDocument();
    expect(screen.getByText('CONFIGURE')).toBeInTheDocument();
  });

  it('shows connected status when WebSocket is connected', () => {
    renderSidebar();
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('applies active styling to current route', () => {
    renderSidebar('/workflows');
    const link = screen.getByRole('link', { name: /Active Jobs/ });
    // NavLink sets aria-current="page" when active
    expect(link).toHaveAttribute('aria-current', 'page');
  });

  it.each([
    { isDemo: true, demoType: 'infinite' as const, expectedSymbol: '∞' },
    { isDemo: false, demoType: null, expectedSymbol: null },
  ])('shows $expectedSymbol when isDemo=$isDemo', ({ isDemo, demoType, expectedSymbol }) => {
    vi.mocked(useDemoMode).mockReturnValue({ isDemo, demoType });

    renderSidebar();

    expect(screen.getByText('AMELIA')).toBeInTheDocument();
    if (expectedSymbol) {
      expect(screen.getByText(expectedSymbol)).toBeInTheDocument();
    } else {
      expect(screen.queryByText('∞')).not.toBeInTheDocument();
    }
  });
});
