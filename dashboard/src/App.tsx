import { Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { router } from '@/router';

function GlobalLoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

export function App() {
  return (
    <TooltipProvider>
      <Suspense fallback={<GlobalLoadingSpinner />}>
        <RouterProvider router={router} />
      </Suspense>
    </TooltipProvider>
  );
}
