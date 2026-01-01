/**
 * @fileoverview Dashboard navigation sidebar component.
 *
 * Provides the main navigation for the Amelia dashboard using shadcn/ui
 * Sidebar primitives with React Router for active state management.
 */

import { NavLink } from 'react-router-dom';
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar';
import {
  GitBranch,
  History,
  Radio,
  BookOpen,
  Zap,
  Library,
  Target,
  FlaskConical,
  Gauge,
  Coins,
} from 'lucide-react';
import { APP_VERSION } from '@/lib/constants';
import { cn } from '@/lib/utils';
import { useWorkflowStore } from '@/store/workflowStore';
import { useDemoMode } from '@/hooks/useDemoMode';

/**
 * Navigation link component using React Router's NavLink for active state.
 * Uses SidebarMenuButton for proper collapsed state handling with tooltips.
 */
interface SidebarNavLinkProps {
  to: string;
  icon: React.ElementType;
  label: string;
  onClick?: () => void;
  comingSoon?: boolean;
}

/**
 * Navigation link component using React Router's NavLink for active state.
 * Renders as a SidebarMenuItem with proper collapsed state handling and tooltips.
 * Supports a "coming soon" mode that renders as a non-clickable placeholder.
 *
 * @param props - Component props
 * @param props.to - The route path to navigate to
 * @param props.icon - Lucide icon component to display
 * @param props.label - Text label for the navigation item
 * @param props.onClick - Optional click handler
 * @param props.comingSoon - If true, renders as disabled placeholder with "Soon" badge
 * @returns React element for the sidebar navigation link
 */
function SidebarNavLink({ to, icon: Icon, label, onClick, comingSoon }: SidebarNavLinkProps) {
  // Coming soon items render as non-clickable placeholders
  if (comingSoon) {
    return (
      <SidebarMenuItem>
        <SidebarMenuButton tooltip={`${label} - Coming Soon`}>
          <div
            className={cn(
              'flex items-center gap-3 w-full cursor-not-allowed opacity-50',
              'group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0'
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="font-heading font-semibold tracking-wide truncate group-data-[collapsible=icon]:hidden flex items-center gap-2">
              {label}
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                Soon
              </span>
            </span>
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>
    );
  }

  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild tooltip={label}>
        <NavLink
          to={to}
          onClick={onClick}
          className={({ isActive, isPending }) =>
            cn(
              'flex items-center gap-3',
              'focus-visible:ring-ring/50 focus-visible:ring-[3px] transition-colors',
              // Center icon when collapsed
              'group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0',
              isActive && 'bg-sidebar-accent text-sidebar-accent-foreground font-medium',
              isPending && 'opacity-50',
              !isActive &&
              'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
            )
          }
        >
          <Icon className="h-4 w-4 shrink-0" />
          <span className="font-heading font-semibold tracking-wide truncate group-data-[collapsible=icon]:hidden">
            {label}
          </span>
        </NavLink>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

/**
 * DashboardSidebar provides navigation for the Amelia dashboard.
 * Uses shadcn/ui Sidebar with React Router NavLink for active state styling.
 *
 * Features:
 * - SidebarProvider for state management (in parent layout)
 * - Cookie-based state persistence
 * - Mobile responsive with sheet drawer
 * - Keyboard navigation with focus-visible states
 * - Server connection status indicator
 *
 * @returns React element for the dashboard sidebar navigation
 */
export function DashboardSidebar() {
  // Get connection status from store
  const isConnected = useWorkflowStore((state) => state.isConnected);
  const { state } = useSidebar();
  const isCollapsed = state === 'collapsed';
  const { isDemo } = useDemoMode();

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      {/* Logo - collapsed shows "A" (glowing primary in demo), expanded shows "AMELIA" with "∞" in demo */}
      <SidebarHeader
        className={cn(
          'border-b border-sidebar-border transition-all',
          isCollapsed ? 'px-2 py-4' : 'px-6 py-6'
        )}
      >
        {isCollapsed ? (
          <div className="flex items-center justify-center">
            <span
              className={cn(
                'text-3xl font-display animate-pulse-glow',
                isDemo ? 'text-primary' : 'text-sidebar-primary'
              )}
            >
              A
            </span>
          </div>
        ) : (
          <h1 className="text-4xl font-display text-sidebar-primary tracking-wider flex items-center gap-2">
            AMELIA
            {isDemo && (
              <span className="text-4xl font-display text-primary animate-pulse-glow">
                ∞
              </span>
            )}
          </h1>
        )}
      </SidebarHeader>

      <SidebarContent className={cn(isCollapsed ? 'px-0' : 'px-2')}>
        {/* Workflows Section */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs font-heading text-muted-foreground/60 font-semibold tracking-wider">
            WORKFLOWS
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarNavLink
                to="/workflows"
                icon={GitBranch}
                label="Active Jobs"
              />
              <SidebarNavLink
                to="/history"
                icon={History}
                label="Past Runs"
              />
              <SidebarNavLink
                to="/logs"
                icon={Radio}
                label="Logs"
              />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Tools Section - Coming Soon features */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs font-heading text-muted-foreground/60 font-semibold tracking-wider">
            TOOLS
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarNavLink
                to="/specs"
                icon={BookOpen}
                label="Spec Builder"
                comingSoon
              />
              <SidebarNavLink
                to="/roundtable"
                icon={Zap}
                label="Roundtable"
                comingSoon
              />
              <SidebarNavLink
                to="/knowledge"
                icon={Library}
                label="Knowledge"
                comingSoon
              />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Improve Section - Agent benchmarking and optimization */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs font-heading text-muted-foreground/60 font-semibold tracking-wider">
            IMPROVE
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarNavLink
                to="/benchmarks"
                icon={Target}
                label="Benchmarks"
                comingSoon
              />
              <SidebarNavLink
                to="/experiments"
                icon={FlaskConical}
                label="Experiments"
                comingSoon
              />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Usage Section - Costs and resource tracking */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs font-heading text-muted-foreground/60 font-semibold tracking-wider">
            USAGE
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarNavLink
                to="/capacity"
                icon={Gauge}
                label="Capacity"
                comingSoon
              />
              <SidebarNavLink
                to="/costs"
                icon={Coins}
                label="Costs"
                comingSoon
              />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* Footer with server status and collapse toggle */}
      <SidebarFooter
        className={cn(
          'border-t border-sidebar-border',
          isCollapsed ? 'px-2 py-3' : 'px-4 py-3'
        )}
      >
        <div
          className={cn(
            'flex items-center',
            isCollapsed ? 'flex-col' : 'justify-between'
          )}
        >
          {/* Connection status */}
          <div
            className={cn(
              'flex items-center',
              isCollapsed ? 'justify-center' : 'gap-3'
            )}
          >
            {isCollapsed ? (
              <div
                role="status"
                aria-label={`Connection status: ${isConnected ? 'Connected' : 'Disconnected'}`}
              >
                <span
                  className={cn(
                    'inline-block w-3 h-3 rounded-full',
                    isConnected
                      ? 'bg-[--status-running] animate-pulse-glow'
                      : 'bg-[--status-failed]'
                  )}
                  title={isConnected ? 'Connected' : 'Disconnected'}
                />
              </div>
            ) : (
              <>
                <span className="text-xs font-mono text-muted-foreground/50">
                  v{APP_VERSION}
                </span>
                <div
                  className="text-xs font-mono text-muted-foreground"
                  role="status"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        'inline-block w-2 h-2 rounded-full',
                        isConnected
                          ? 'bg-[--status-running] animate-pulse-glow'
                          : 'bg-[--status-failed]'
                      )}
                    />
                    {isConnected ? 'Connected' : 'Disconnected'}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Collapse toggle button */}
          <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
