/**
 * Shared test helpers for the Amelia Dashboard.
 * Reduces duplication across test files.
 */

import { render, RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { SidebarProvider } from '@/components/ui/sidebar';
import { DashboardSidebar } from '@/components/DashboardSidebar';

/**
 * Suppress console output during tests.
 * Call in beforeEach, restore with vi.restoreAllMocks() in afterEach.
 */
export function suppressConsoleLogs(): void {
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
}

/**
 * Options for rendering the DashboardSidebar in tests.
 */
export interface RenderSidebarOptions {
  /** Initial route for the MemoryRouter. Defaults to '/'. */
  initialRoute?: string;
  /** Whether the sidebar should be open. Defaults to true. */
  open?: boolean;
}

/**
 * Renders the DashboardSidebar with common test providers.
 * Use this helper to reduce duplication in sidebar tests.
 */
export function renderSidebar(options: RenderSidebarOptions = {}): RenderResult {
  const { initialRoute = '/', open = true } = options;
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <SidebarProvider defaultOpen={open}>
        <DashboardSidebar />
      </SidebarProvider>
    </MemoryRouter>
  );
}
