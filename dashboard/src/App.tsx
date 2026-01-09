/**
 * @fileoverview Root application component for the Amelia dashboard.
 * Provides global context providers and routing setup.
 */
import { Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import { Toaster } from 'sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { LoadingTimeout } from '@/components/LoadingTimeout';
import { router } from '@/router';

/**
 * Global loading spinner displayed during lazy-loaded route transitions.
 * Uses LoadingTimeout for progressive feedback during slow loads.
 *
 * @returns A full-screen loading spinner component with timeout feedback.
 */
function GlobalLoadingSpinner() {
  return (
    <LoadingTimeout className="min-h-screen bg-background" />
  );
}

/**
 * Root application component that sets up global providers and routing.
 *
 * Wraps the application with:
 * - TooltipProvider for global tooltip support
 * - Suspense with GlobalLoadingSpinner for lazy-loaded routes
 * - RouterProvider for client-side routing
 * - Toaster for toast notifications
 *
 * @returns The configured root application component.
 */
export function App() {
  return (
    <TooltipProvider>
      <Suspense fallback={<GlobalLoadingSpinner />}>
        <RouterProvider router={router} />
      </Suspense>
      <Toaster richColors position="bottom-right" />
    </TooltipProvider>
  );
}
