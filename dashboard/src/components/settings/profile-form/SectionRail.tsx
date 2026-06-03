/**
 * Section navigation rail for the profile detail page.
 *
 * Renders a vertical rail at `md+` and a horizontal, scrollable tab row below
 * `md` (the same item set — no nav hidden behind a menu). Each item is a button
 * that reflects whether its section currently has validation errors via
 * `data-has-error` and an aria-hidden error dot.
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
    <>
      {/* Vertical rail at md+ */}
      <nav className="hidden md:flex flex-col gap-1" aria-label="Profile sections">
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
                'flex items-center gap-2 whitespace-nowrap rounded-md border-l-2 px-3 py-2 text-left text-sm font-medium transition-all duration-200',
                isActive
                  ? 'border-primary bg-muted/50 text-foreground [text-shadow:0_0_8px_rgba(255,200,87,0.3)]'
                  : 'border-transparent text-muted-foreground hover:bg-muted/30 hover:text-foreground'
              )}
            >
              {label}
              {hasError && (
                <span
                  aria-hidden="true"
                  className="ml-auto h-1.5 w-1.5 rounded-full bg-destructive"
                />
              )}
            </button>
          );
        })}
      </nav>

      {/* Horizontal scrollable tab row below md (mirror of the same items, hidden
          from the accessibility tree so it does not duplicate the rail buttons). */}
      <nav
        className="flex md:hidden gap-4 overflow-x-auto border-b px-1"
        aria-hidden="true"
      >
        {sections.map(({ id, label }) => {
          const isActive = id === active;
          const hasError = Boolean(errorSections[id]);
          return (
            <button
              key={id}
              type="button"
              tabIndex={-1}
              onClick={() => onSelect(id)}
              data-has-error={hasError}
              className={cn(
                'flex items-center gap-2 whitespace-nowrap border-b-2 -mb-px py-3 text-sm font-medium transition-all duration-200',
                isActive
                  ? 'border-primary text-foreground [text-shadow:0_0_8px_rgba(255,200,87,0.3)]'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              {label}
              {hasError && (
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 rounded-full bg-destructive"
                />
              )}
            </button>
          );
        })}
      </nav>
    </>
  );
}
