/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { Outlet, useNavigation } from 'react-router-dom';
import { SidebarProvider } from '@/components/ui/sidebar';
import { DashboardSidebar } from '@/components/DashboardSidebar';
import { NavigationProgress } from '@/components/NavigationProgress';
import { useWebSocket } from '@/hooks/useWebSocket';

export function Layout() {
  const navigation = useNavigation();

  // Initialize WebSocket connection
  useWebSocket();

  const isNavigating = navigation.state !== 'idle';

  return (
    <SidebarProvider>
      <div className="flex h-screen bg-background text-foreground">
        {/* Sidebar */}
        <DashboardSidebar />

        {/* Main content area with navigation progress */}
        <main className="flex-1 overflow-hidden relative">
          {isNavigating && <NavigationProgress />}
          <Outlet />
        </main>
      </div>
    </SidebarProvider>
  );
}
