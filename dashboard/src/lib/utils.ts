/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Utility functions for the dashboard application.
 */
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merges Tailwind CSS classes safely, handling conflicts.
 *
 * Combines multiple class values using clsx and resolves Tailwind
 * class conflicts using tailwind-merge.
 *
 * @param inputs - Class values to merge (strings, arrays, objects)
 * @returns Merged class string with conflicts resolved
 *
 * @example
 * ```ts
 * cn('px-4 py-2', 'px-6') // => 'py-2 px-6'
 * cn('text-red-500', { 'text-blue-500': isBlue })
 * ```
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
