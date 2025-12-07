import { NavLink } from 'react-router-dom';
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuItem,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
} from '@/components/ui/sidebar';
import { GitBranch, History, Radio, Compass } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWorkflowStore } from '@/store/workflowStore';

/**
 * Navigation link component using React Router's NavLink for active state.
 * Applies shadcn/ui SidebarMenuButton styling with active highlighting.
 */
interface SidebarNavLinkProps {
  to: string;
  icon: React.ElementType;
  label: string;
}

function SidebarNavLink({ to, icon: Icon, label }: SidebarNavLinkProps) {
  return (
    <SidebarMenuItem>
      <NavLink
        to={to}
        className={({ isActive, isPending }) =>
          cn(
            'flex items-center gap-3 w-full px-3 py-2 rounded-md text-sm',
            'focus-visible:ring-ring/50 focus-visible:ring-[3px] transition-colors',
            isActive && 'bg-sidebar-primary text-sidebar-primary-foreground',
            isPending && 'opacity-50',
            !isActive && 'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
          )
        }
      >
        <Icon className="h-4 w-4" />
        <span className="font-heading font-semibold tracking-wide">{label}</span>
      </NavLink>
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

  return (
    <Sidebar className="border-r border-sidebar-border">
      {/* Logo */}
      <SidebarHeader className="px-6 py-6 border-b border-sidebar-border">
        <h1 className="text-4xl font-display text-sidebar-primary tracking-wider">
          AMELIA
        </h1>
        <p className="text-xs font-mono text-muted-foreground mt-1">
          Agentic Orchestrator
        </p>
      </SidebarHeader>

      <SidebarContent className="px-2">
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

      {/* Footer with server status */}
      <SidebarFooter className="px-4 py-4 border-t border-sidebar-border">
        <div className="flex items-center gap-3">
          <Compass className="w-8 h-8 text-muted-foreground/50" />
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
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
