import { useSearchParams } from "react-router-dom";

/**
 * Demo mode state returned by useDemoMode hook and getDemoMode helper.
 */
export interface DemoModeState {
  /** Whether any demo mode is active */
  isDemo: boolean;
  /** The specific demo type (e.g., 'infinite') or null */
  demoType: string | null;
}

/**
 * Check demo mode from a URLSearchParams or Request object.
 * Used in loaders which don't have access to hooks.
 *
 * @param searchParams - URLSearchParams from loader
 * @returns Demo mode state
 *
 * @example
 * ```typescript
 * // In a loader
 * export async function loader({ request }: LoaderFunctionArgs) {
 *   const url = new URL(request.url);
 *   const { isDemo, demoType } = getDemoMode(url.searchParams);
 *   // ...
 * }
 * ```
 */
export function getDemoMode(searchParams: URLSearchParams): DemoModeState {
  const demo = searchParams.get("demo");

  if (demo) {
    return {
      isDemo: true,
      demoType: demo,
    };
  }

  return {
    isDemo: false,
    demoType: null,
  };
}

/**
 * Hook to detect if the dashboard is in demo mode.
 * Reads from URL search params: ?demo=infinite
 *
 * @returns Object with demo mode state
 *
 * @example
 * ```typescript
 * function MyComponent() {
 *   const { isDemo, demoType } = useDemoMode();
 *
 *   if (isDemo && demoType === 'infinite') {
 *     // Render infinite scroll demo
 *   }
 * }
 * ```
 */
export function useDemoMode(): DemoModeState {
  const [searchParams] = useSearchParams();
  return getDemoMode(searchParams);
}
