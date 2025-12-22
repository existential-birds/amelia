/**
 * @fileoverview Mobile detection hook for responsive behavior.
 */
import * as React from "react"

/**
 * Breakpoint threshold for mobile detection (in pixels).
 * Viewport widths below this value are considered mobile.
 */
const MOBILE_BREAKPOINT = 768

/**
 * Detects if the viewport is mobile-sized.
 *
 * Uses matchMedia to listen for viewport changes and updates
 * reactively. Returns false during SSR/initial render.
 *
 * @returns True if viewport width is below mobile breakpoint
 *
 * @example
 * ```tsx
 * const isMobile = useIsMobile();
 * return isMobile ? <MobileNav /> : <DesktopNav />;
 * ```
 */
export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    }
    mql.addEventListener("change", onChange)
    setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return !!isMobile
}
