/**
 * Auto-Fix configuration section for the profile detail page.
 *
 * Thin wrapper around the existing `PRAutoFixSection`: `enabled` is derived from
 * whether a config is present (`config !== null`).
 */
import { PRAutoFixSection } from '@/components/settings/PRAutoFixSection';
import type { PRAutoFixConfig } from '@/api/settings';

interface AutoFixSectionProps {
  config: PRAutoFixConfig | null;
  onChange: (config: PRAutoFixConfig | null) => void;
}

export function AutoFixSection({ config, onChange }: AutoFixSectionProps) {
  return <PRAutoFixSection enabled={config !== null} config={config} onChange={onChange} />;
}
