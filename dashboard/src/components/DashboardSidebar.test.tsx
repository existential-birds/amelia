import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DashboardSidebar } from './DashboardSidebar';
import { SidebarProvider } from '@/components/ui/sidebar';

// Mock the workflow store
vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: vi.fn((selector) => {
    const state = { isConnected: true, selectWorkflow: vi.fn() };
    return selector(state);
  }),
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
    expect(screen.getByText('Agentic Orchestrator')).toBeInTheDocument();
  });

  it.each([
    ['Active Jobs', '/workflows'],
    ['Past Runs', '/history'],
    ['Logs', '/logs'],
  ])('renders %s navigation link to %s', (label, href) => {
    renderSidebar();
    const link = screen.getByRole('link', { name: new RegExp(label) });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', href);
  });

  it('renders section labels', () => {
    renderSidebar();
    expect(screen.getByText('WORKFLOWS')).toBeInTheDocument();
    expect(screen.getByText('HISTORY')).toBeInTheDocument();
    expect(screen.getByText('MONITORING')).toBeInTheDocument();
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
});
