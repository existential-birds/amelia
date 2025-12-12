/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Toast notification utilities.
 *
 * Toast notification utilities using the sonner library for displaying
 * user feedback with a clean, accessible UI.
 */

import { toast } from 'sonner';

/**
 * Displays a success toast notification.
 * @param message - Success message to display
 */
export function success(message: string): void {
  toast.success(message);
}

/**
 * Displays an error toast notification.
 * @param message - Error message to display
 */
export function error(message: string): void {
  toast.error(message);
}

/**
 * Displays an informational toast notification.
 * @param message - Info message to display
 */
export function info(message: string): void {
  toast.info(message);
}

/**
 * Displays a warning toast notification.
 * @param message - Warning message to display
 */
export function warning(message: string): void {
  toast.warning(message);
}

/**
 * Displays a loading toast notification.
 * @param message - Loading message to display
 * @returns Toast ID that can be used to dismiss or update the toast
 */
export function loading(message: string): string | number {
  return toast.loading(message);
}

/**
 * Displays a promise toast notification that updates based on promise state.
 * @param promise - Promise to track
 * @param messages - Messages for loading, success, and error states
 * @returns The original promise, allowing callers to await the resolved value
 */
export function promise<T>(
  promise: Promise<T>,
  messages: {
    loading: string;
    success: string | ((data: T) => string);
    error: string | ((error: Error) => string);
  }
): Promise<T> {
  // Call toast.promise for side effect (displays toast)
  // toast.promise returns toast ID (string | number), not the promise
  toast.promise(promise, messages);
  // Return the original promise so callers get the resolved value
  return promise;
}
