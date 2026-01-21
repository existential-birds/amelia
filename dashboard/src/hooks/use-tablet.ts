/**
 * @fileoverview Tablet detection hook for responsive behavior.
 */
import * as React from 'react';

/**
 * Breakpoint threshold for tablet detection (in pixels).
 * Viewport widths below this value are considered tablet or smaller.
 * Matches Tailwind's `lg` breakpoint (1024px).
 */
const TABLET_BREAKPOINT = 1024;

/**
 * Detects if the viewport is tablet-sized or smaller.
 *
 * Uses matchMedia to listen for viewport changes and updates
 * reactively. Returns false during SSR/initial render.
 *
 * @returns True if viewport width is below tablet breakpoint (1024px)
 *
 * @example
 * ```tsx
 * const isTablet = useIsTablet();
 * return isTablet ? <VerticalLayout /> : <HorizontalLayout />;
 * ```
 */
export function useIsTablet() {
  const [isTablet, setIsTablet] = React.useState<boolean | undefined>(
    undefined
  );

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${TABLET_BREAKPOINT - 1}px)`);
    const onChange = () => {
      setIsTablet(window.innerWidth < TABLET_BREAKPOINT);
    };
    mql.addEventListener('change', onChange);
    setIsTablet(window.innerWidth < TABLET_BREAKPOINT);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return !!isTablet;
}
