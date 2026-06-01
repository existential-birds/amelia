/**
 * Toast notification helpers wrapping the sonner library, so the rest of the
 * app depends on this seam rather than sonner directly.
 */

import { toast } from 'sonner';

export function success(message: string): void {
  toast.success(message);
}

export function error(message: string): void {
  toast.error(message);
}

export function info(message: string): void {
  toast.info(message);
}

export function warning(message: string): void {
  toast.warning(message);
}

/** Returns a toast ID that can be used to dismiss or update the toast. */
export function loading(message: string): string | number {
  return toast.loading(message);
}

/**
 * Shows a toast that tracks promise state, and returns the original promise so
 * callers can still await the resolved value (toast.promise returns a toast ID).
 */
export function promise<T>(
  promise: Promise<T>,
  messages: {
    loading: string;
    success: string | ((data: T) => string);
    error: string | ((error: Error) => string);
  }
): Promise<T> {
  toast.promise(promise, messages);
  return promise;
}
