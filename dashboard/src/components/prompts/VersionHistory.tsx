/**
 * @fileoverview Collapsible version history component for prompts.
 *
 * Shows a list of previous versions with timestamps and change notes,
 * with the active version highlighted.
 */
import { useState } from 'react';
import { ChevronDown, History, Check } from 'lucide-react';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { VersionSummary } from '@/types';

/** Cached date formatter for version timestamps. */
const dateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/**
 * Formats an ISO date string for display.
 *
 * @param dateString - ISO date string.
 * @returns Formatted date string (e.g., "Dec 7, 2024, 10:30 AM").
 */
function formatDate(dateString: string): string {
  return dateFormatter.format(new Date(dateString));
}

interface VersionHistoryProps {
  /** List of versions to display. */
  versions: VersionSummary[];
  /** The ID of the currently active version, or null for default. */
  activeVersionId: string | null;
  /** Callback when a version is selected for viewing. */
  onViewVersion?: (versionId: string) => void;
}

/**
 * Collapsible section showing prompt version history.
 *
 * Features:
 * - Expands/collapses to show version list
 * - Displays version number, date, and change note
 * - Highlights the active version
 * - Allows viewing previous versions (optional)
 *
 * @param props - Component props.
 * @returns The version history component.
 *
 * @example
 * ```tsx
 * <VersionHistory
 *   versions={prompt.versions}
 *   activeVersionId={prompt.current_version_id}
 *   onViewVersion={(id) => openVersionViewer(id)}
 * />
 * ```
 */
export function VersionHistory({
  versions,
  activeVersionId,
  onViewVersion,
}: VersionHistoryProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (versions.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-2">
        No version history. Using default prompt.
      </div>
    );
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-between text-muted-foreground hover:text-foreground"
        >
          <span className="flex items-center gap-2">
            <History className="size-4" />
            Version History ({versions.length})
          </span>
          <ChevronDown
            className={cn(
              'size-4 transition-transform',
              isOpen && 'rotate-180'
            )}
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 space-y-1">
          {versions.map((version) => {
            const isActive = version.id === activeVersionId;

            return (
              <div
                key={version.id}
                className={cn(
                  'flex items-start gap-3 p-2 rounded-md text-sm transition-colors',
                  isActive && 'bg-primary/10 border border-primary/20',
                  !isActive && 'hover:bg-muted/50'
                )}
              >
                {/* Version indicator */}
                <div
                  className={cn(
                    'flex items-center justify-center size-6 rounded-full text-xs font-medium shrink-0 mt-0.5',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground'
                  )}
                >
                  {isActive ? (
                    <Check className="size-3.5" />
                  ) : (
                    `v${version.version_number}`
                  )}
                </div>

                {/* Version details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      Version {version.version_number}
                    </span>
                    {isActive && (
                      <span className="text-xs text-primary font-medium">
                        Active
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {formatDate(version.created_at)}
                  </div>
                  {version.change_note && (
                    <div className="text-muted-foreground mt-1 line-clamp-2">
                      {version.change_note}
                    </div>
                  )}
                </div>

                {/* View button */}
                {onViewVersion && !isActive && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onViewVersion(version.id)}
                    className="shrink-0 text-xs"
                  >
                    View
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
