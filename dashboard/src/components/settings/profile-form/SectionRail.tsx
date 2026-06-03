/**
 * Section navigation rail for the profile detail page.
 *
 * A single item set that lays out as a vertical rail at `md+` and collapses to
 * a horizontal, scrollable tab row below `md` — no nav hidden behind a menu and
 * fully reachable by mouse, touch, keyboard, and screen reader at every width.
 * Each item is a button that reflects whether its section currently has
 * validation errors via `data-has-error` and an aria-hidden error dot.
 */
import { cn } from '@/lib/utils';
import type { SectionId } from './types';

interface SectionRailProps {
  sections: { id: SectionId; label: string }[];
  active: SectionId;
  onSelect: (id: SectionId) => void;
  errorSections: Partial<Record<SectionId, boolean>>;
}

export function SectionRail({ sections, active, onSelect, errorSections }: SectionRailProps) {
  return (
    <nav
      aria-label="Profile sections"
      className="flex flex-row gap-4 overflow-x-auto border-b px-1 md:flex-col md:gap-1 md:overflow-x-visible md:border-b-0 md:px-0"
    >
      {sections.map(({ id, label }) => {
        const isActive = id === active;
        const hasError = Boolean(errorSections[id]);
        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelect(id)}
            data-has-error={hasError}
            aria-current={isActive ? 'page' : undefined}
            className={cn(
              // Mobile: bottom-border tab. md+: left-border vertical rail item.
              'flex items-center gap-2 whitespace-nowrap border-b-2 -mb-px py-3 text-sm font-medium transition-all duration-200 md:mb-0 md:rounded-md md:border-b-0 md:border-l-2 md:px-3 md:py-2 md:text-left',
              isActive
                ? 'border-primary text-foreground [text-shadow:0_0_8px_rgba(255,200,87,0.3)] md:bg-muted/50'
                : 'border-transparent text-muted-foreground hover:text-foreground md:hover:bg-muted/30'
            )}
          >
            {label}
            {hasError && (
              <>
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 rounded-full bg-destructive md:ml-auto"
                />
                <span className="sr-only">(has errors)</span>
              </>
            )}
          </button>
        );
      })}
    </nav>
  );
}
