import { Terminal, Cloud } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface DriverStyle {
  bg: string;
  text: string;
  icon: LucideIcon;
}

const DRIVER_STYLES = {
  cli: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', icon: Terminal },
  api: { bg: 'bg-blue-500/10', text: 'text-blue-500', icon: Cloud },
} as const satisfies Record<string, DriverStyle>;

export function getDriverStyle(driver: string): DriverStyle {
  const prefix = driver.startsWith('cli:') ? 'cli' : 'api';
  return DRIVER_STYLES[prefix];
}

export function getDriverIcon(driver: string): LucideIcon {
  return getDriverStyle(driver).icon;
}
