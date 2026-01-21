/**
 * Layout with tab navigation for settings pages.
 */
import { NavLink, Outlet } from 'react-router-dom';
import { cn } from '@/lib/utils';

const tabs = [
  { to: '/settings/profiles', label: 'Profiles' },
  { to: '/settings/server', label: 'Server' },
];

export function SettingsLayout() {
  return (
    <div>
      <div className="border-b">
        <nav className="container flex gap-4">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                cn(
                  'py-4 text-sm font-medium border-b-2 -mb-px',
                  isActive
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <Outlet />
    </div>
  );
}

export default SettingsLayout;
