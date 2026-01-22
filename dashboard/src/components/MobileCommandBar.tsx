/**
 * @fileoverview Mobile navigation command bar component.
 *
 * Provides a compact navigation strip for mobile viewports that appears
 * above page content. Includes sidebar trigger, branding, and connection
 * status indicator. Only visible on mobile where the sidebar becomes a
 * hidden Sheet drawer.
 */

import { PanelLeft } from 'lucide-react';
import { useSidebar } from '@/components/ui/sidebar';
import { useWorkflowStore } from '@/store/workflowStore';
import { cn } from '@/lib/utils';

/**
 * Mobile-only command bar that provides quick access to the sidebar
 * and displays connection status.
 *
 * Features:
 * - Sidebar trigger button using the sidebar context
 * - Centered "AMELIA" branding with letter-spaced typography
 * - Connection status indicator (glowing green when connected, red when disconnected)
 * - Sticky positioning at top of viewport
 * - Hidden on tablet/desktop viewports (md:hidden)
 *
 * Layout:
 * ```
 * +-----------------------------------------------------+
 * | [=]           A M E L I A                   [*]    |
 * +-----------------------------------------------------+
 * ```
 *
 * @returns The mobile command bar element, or null on non-mobile viewports.
 *
 * @example
 * ```tsx
 * // Place at the top of your page content
 * function WorkflowsPage() {
 *   return (
 *     <div>
 *       <MobileCommandBar />
 *       <main>Page content...</main>
 *     </div>
 *   );
 * }
 * ```
 */
export function MobileCommandBar() {
  const { toggleSidebar } = useSidebar();
  const isConnected = useWorkflowStore((state) => state.isConnected);

  return (
    <header
      className={cn(
        'md:hidden',
        'sticky top-0 z-20',
        'h-11 min-h-[44px]',
        'flex items-center justify-between px-4',
        'bg-background/95 backdrop-blur-sm',
        'border-b border-primary/30'
      )}
    >
      {/* Left section: Sidebar trigger */}
      <button
        type="button"
        onClick={toggleSidebar}
        className={cn(
          'flex items-center justify-center',
          'h-9 w-9 rounded-md',
          'text-muted-foreground hover:text-foreground',
          'hover:bg-accent/50 active:bg-accent/70',
          'transition-colors'
        )}
        aria-label="Toggle sidebar"
      >
        <PanelLeft className="h-5 w-5" />
      </button>

      {/* Center section: Branding */}
      <div className="flex items-center justify-center">
        <span className="text-primary font-display tracking-[0.3em] text-sm">
          A M E L I A
        </span>
      </div>

      {/* Right section: Connection status */}
      <div className="flex items-center justify-center h-9 w-9">
        <span
          className={cn(
            'h-2.5 w-2.5 rounded-full',
            isConnected
              ? 'bg-[--status-running] animate-pulse-glow'
              : 'bg-[--status-failed]'
          )}
          aria-label={isConnected ? 'Connected' : 'Disconnected'}
          role="status"
        />
      </div>
    </header>
  );
}
