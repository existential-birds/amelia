/**
 * @fileoverview Root application component for the Amelia dashboard.
 * Provides global context providers and routing setup.
 */
import { Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import { Toaster } from 'sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { router } from '@/router';

/**
 * Global loading spinner displayed during lazy-loaded route transitions.
 * Renders a centered spinning indicator with primary color styling.
 *
 * @returns A full-screen loading spinner component.
 */
function GlobalLoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
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
