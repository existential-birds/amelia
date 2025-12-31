/**
 * @fileoverview Root error boundary for router-level errors.
 *
 * Catches and displays both HTTP errors (404, 500) and JavaScript runtime
 * errors that occur during rendering or navigation.
 */

import { useRouteError, isRouteErrorResponse, useNavigate, Link } from 'react-router-dom';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Root error boundary component for handling router-level errors.
 *
 * Displays user-friendly error pages for:
 * - HTTP error responses (404, 500, etc.) with status and message
 * - JavaScript runtime errors with stack trace in development mode
 *
 * Provides navigation options to recover from errors.
 *
 * @returns Error UI with recovery options (reload, go home, go back)
 */
export function RootErrorBoundary() {
  const error = useRouteError();
  const navigate = useNavigate();

  // Handle HTTP error responses (404, 500, etc.)
  if (isRouteErrorResponse(error)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-8">
        <AlertTriangle className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-4xl font-display text-destructive mb-4">
          {error.status} {error.statusText}
        </h1>
        <p className="text-muted-foreground mb-8 max-w-md text-center">
          {error.data?.message || 'The page you are looking for does not exist.'}
        </p>
        <div className="flex gap-4">
          <Button asChild>
            <Link to="/">
              <Home className="w-4 h-4" />
              Go Home
            </Link>
          </Button>
          <Button variant="outline" onClick={() => navigate(-1)}>
            Go Back
          </Button>
        </div>
      </div>
    );
  }

  // Handle JavaScript errors
  const errorMessage = error instanceof Error ? error.message : 'Unknown error';
  const errorStack = error instanceof Error ? error.stack : undefined;

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-8">
      <AlertTriangle className="w-16 h-16 text-destructive mb-4" />
      <h1 className="text-4xl font-display text-destructive mb-4">
        Something went wrong
      </h1>
      <p className="text-muted-foreground mb-8 max-w-md text-center">
        {errorMessage}
      </p>
      {import.meta.env.DEV && errorStack && (
        <details className="mb-8 max-w-2xl w-full">
          <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
            Show error details
          </summary>
          <pre className="mt-4 p-4 bg-card border border-border rounded text-xs overflow-auto">
            {errorStack}
          </pre>
        </details>
      )}
      <div className="flex gap-4">
        <Button onClick={() => window.location.reload()}>
          <RefreshCw className="w-4 h-4" />
          Reload Dashboard
        </Button>
        <Button variant="outline" asChild>
          <Link to="/">
            <Home className="w-4 h-4" />
            Go Home
          </Link>
        </Button>
      </div>
    </div>
  );
}
