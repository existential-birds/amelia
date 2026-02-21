import { Terminal, Cloud, Code2 } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface DriverStyle {
  bg: string;
  text: string;
  icon: LucideIcon;
}

const DRIVER_STYLES = {
  claude: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', icon: Terminal },
  codex: { bg: 'bg-purple-500/10', text: 'text-purple-500', icon: Code2 },
  api: { bg: 'bg-blue-500/10', text: 'text-blue-500', icon: Cloud },
} as const satisfies Record<string, DriverStyle>;

export function getDriverStyle(driver: string): DriverStyle {
  const normalized = driver.split(':')[0] as keyof typeof DRIVER_STYLES;
  return DRIVER_STYLES[normalized] ?? DRIVER_STYLES.api;
}

export function getDriverIcon(driver: string): LucideIcon {
  return getDriverStyle(driver).icon;
}
