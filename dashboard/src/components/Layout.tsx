/**
 * @fileoverview Main layout component for the Amelia dashboard.
 * Provides the sidebar, content area, and global visual effects.
 */
import { Outlet, useNavigation } from 'react-router-dom';
import { SidebarProvider } from '@/components/ui/sidebar';
import { DashboardSidebar } from '@/components/DashboardSidebar';
import { NavigationProgress } from '@/components/NavigationProgress';
import { useWebSocket } from '@/hooks/useWebSocket';

/**
 * Root layout component that provides the dashboard structure.
 *
 * Features:
 * - Responsive sidebar with navigation
 * - WebSocket connection for real-time updates
 * - Navigation progress indicator during route transitions
 * - Decorative visual effects (starfield, scanlines, vignette)
 *
 * @returns The layout wrapper with sidebar and content outlet.
 */
export function Layout() {
  const navigation = useNavigation();

  // Initialize WebSocket connection
  useWebSocket();

  const isNavigating = navigation.state !== 'idle';

  return (
    <SidebarProvider>
      <div className="flex h-screen w-full bg-background text-foreground">
        {/* Sidebar */}
        <DashboardSidebar />

        {/* Main content area with navigation progress */}
        <main className="flex-1 overflow-auto relative">
          {/* Starfield background - z-0 */}
          <div
            className="fixed inset-0 pointer-events-none z-0 opacity-40"
            style={{
              background: `
                radial-gradient(1px 1px at 20px 30px, rgb(239 248 226), transparent),
                radial-gradient(1px 1px at 40px 70px, rgb(239 248 226 / 0.8), transparent),
                radial-gradient(1px 1px at 50px 160px, rgb(239 248 226 / 0.6), transparent),
                radial-gradient(1px 1px at 90px 40px, rgb(239 248 226), transparent),
                radial-gradient(1px 1px at 130px 80px, rgb(239 248 226 / 0.7), transparent),
                radial-gradient(1.5px 1.5px at 160px 120px, rgb(255 200 87), transparent),
                radial-gradient(1px 1px at 200px 50px, rgb(239 248 226 / 0.5), transparent),
                radial-gradient(1px 1px at 280px 20px, rgb(239 248 226 / 0.6), transparent),
                radial-gradient(1.5px 1.5px at 320px 100px, rgb(91 155 213 / 0.8), transparent),
                radial-gradient(1px 1px at 400px 60px, rgb(239 248 226), transparent),
                radial-gradient(1.5px 1.5px at 550px 90px, rgb(255 200 87), transparent),
                radial-gradient(1px 1px at 650px 50px, rgb(239 248 226 / 0.9), transparent)
              `,
              backgroundRepeat: 'repeat',
              backgroundSize: '700px 180px',
            }}
            aria-hidden="true"
          />

          {/* Glass scanlines - z-[5] (behind content at z-10) */}
          <div
            className="fixed inset-0 pointer-events-none z-[5]"
            style={{
              background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgb(239 248 226 / 0.01) 2px, rgb(239 248 226 / 0.01) 4px)',
            }}
            aria-hidden="true"
          />

          {/* Vignette - z-[6] (behind content at z-10) */}
          <div
            className="fixed inset-0 pointer-events-none z-[6]"
            style={{
              background: 'radial-gradient(ellipse at center, transparent 30%, rgb(13 26 18 / 0.6) 100%)',
            }}
            aria-hidden="true"
          />

          {isNavigating && <NavigationProgress />}

          {/* Content wrapper with z-10 for proper layering */}
          <div className="relative z-10 h-full">
            <Outlet />
          </div>
        </main>
      </div>
    </SidebarProvider>
  );
}
