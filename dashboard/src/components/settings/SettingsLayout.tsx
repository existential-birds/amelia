/**
 * Layout with tab navigation for settings pages.
 */
import { Suspense } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { Users, Server, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SettingsPageSkeleton } from './SettingsPageSkeleton';

interface Tab {
  to: string;
  label: string;
  icon: LucideIcon;
}

const tabs: Tab[] = [
  { to: '/settings/profiles', label: 'Profiles', icon: Users },
  { to: '/settings/server', label: 'Server', icon: Server },
];

export function SettingsLayout() {
  return (
    <div>
      <div className="border-b">
        <nav className="container flex gap-4">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2 py-4 text-sm font-medium border-b-2 -mb-px transition-all duration-200',
                    isActive
                      ? 'border-primary text-foreground [text-shadow:0_0_8px_rgba(255,200,87,0.3)]'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </NavLink>
            );
          })}
        </nav>
      </div>
      <Suspense fallback={<SettingsPageSkeleton />}>
        <Outlet />
      </Suspense>
    </div>
  );
}

export default SettingsLayout;
