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
import { GitBranch, History, Radio, Compass } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWorkflowStore } from '@/store/workflowStore';

/**
 * Navigation link component using React Router's NavLink for active state.
 * Uses SidebarMenuButton for proper collapsed state handling with tooltips.
 */
interface SidebarNavLinkProps {
  to: string;
  icon: React.ElementType;
  label: string;
}

function SidebarNavLink({ to, icon: Icon, label }: SidebarNavLinkProps) {
  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild tooltip={label}>
        <NavLink
          to={to}
          className={({ isActive, isPending }) =>
            cn(
              'flex items-center gap-3',
              'focus-visible:ring-ring/50 focus-visible:ring-[3px] transition-colors',
              // Center icon when collapsed
              'group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0',
              isActive && 'bg-sidebar-primary text-sidebar-primary-foreground',
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
 */
export function DashboardSidebar() {
  // Get connection status from store
  const isConnected = useWorkflowStore((state) => state.isConnected);
  const { state } = useSidebar();
  const isCollapsed = state === 'collapsed';

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      {/* Logo - shows glowing "A" when collapsed, full "AMELIA" when expanded */}
      <SidebarHeader
        className={cn(
          'border-b border-sidebar-border transition-all',
          isCollapsed ? 'px-2 py-4' : 'px-6 py-6'
        )}
      >
        {isCollapsed ? (
          <div className="flex items-center justify-center">
            <span className="text-3xl font-display text-sidebar-primary animate-pulse-glow">
              A
            </span>
          </div>
        ) : (
          <>
            <h1 className="text-4xl font-display text-sidebar-primary tracking-wider">
              AMELIA
            </h1>
            <p className="text-xs font-mono text-muted-foreground mt-1">
              Agentic Orchestrator
            </p>
          </>
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
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* History Section */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs font-heading text-muted-foreground/60 font-semibold tracking-wider">
            HISTORY
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarNavLink
                to="/history"
                icon={History}
                label="Past Runs"
              />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Monitoring Section */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs font-heading text-muted-foreground/60 font-semibold tracking-wider">
            MONITORING
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarNavLink
                to="/logs"
                icon={Radio}
                label="Logs"
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
              <span
                className={cn(
                  'inline-block w-3 h-3 rounded-full',
                  isConnected
                    ? 'bg-[--status-running] animate-pulse-glow'
                    : 'bg-[--status-failed]'
                )}
                title={isConnected ? 'Connected' : 'Disconnected'}
              />
            ) : (
              <>
                <Compass className="w-6 h-6 text-muted-foreground/50" />
                <div className="text-xs font-mono text-muted-foreground">
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
