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

/**
 * Formats ISO 8601 timestamp to HH:MM:SS format.
 *
 * Returns "-" for invalid or malformed timestamps to prevent render errors.
 *
 * @param isoString - ISO 8601 timestamp string
 * @returns Formatted time string (e.g., "10:30:45") or "-" if invalid
 *
 * @example
 * ```ts
 * formatTime('2025-12-13T10:30:45.123Z') // => '10:30:45'
 * formatTime('invalid') // => '-'
 * ```
 */
export function formatTime(isoString: string | null | undefined): string {
  if (!isoString) {
    return '-';
  }
  const date = new Date(isoString);
  if (!Number.isFinite(date.getTime())) {
    return '-';
  }
  return date.toISOString().slice(11, 19); // HH:MM:SS
}

/**
 * Formats driver string for display.
 *
 * Extracts the driver type (API or Claude) from the full driver string.
 *
 * @param driver - Driver string (e.g., "api:openrouter", "claude:opus")
 * @returns Formatted driver type (e.g., "API", "Claude")
 *
 * @example
 * ```ts
 * formatDriver('api:openrouter') // => 'API'
 * formatDriver('claude:opus') // => 'Claude'
 * ```
 */
export function formatDriver(driver: string): string {
  if (driver.startsWith('api:')) return 'API';
  if (driver.startsWith('claude:')) return 'Claude';
  return driver.toUpperCase();
}

/**
 * Formats model name for display.
 *
 * Capitalizes simple model names and formats longer model identifiers
 * with proper spacing and version numbers.
 *
 * @param model - Model identifier (e.g., "sonnet", "claude-3-5-sonnet")
 * @returns Formatted model name (e.g., "Sonnet", "Claude 3.5 Sonnet")
 *
 * @example
 * ```ts
 * formatModel('sonnet') // => 'Sonnet'
 * formatModel('claude-3-5-sonnet') // => 'Claude 3.5 Sonnet'
 * ```
 */
export function formatModel(model: string): string {
  // Handle simple names like "sonnet", "opus", "haiku"
  if (/^(sonnet|opus|haiku)$/i.test(model)) {
    return model.charAt(0).toUpperCase() + model.slice(1).toLowerCase();
  }
  // Handle longer model names - capitalize and clean up
  return model
    .split(/[-_]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
    .replace(/(\d)(\d)/g, '$1.$2'); // "35" -> "3.5"
}

/**
 * Copies text to clipboard with iOS Safari fallback.
 *
 * iOS Safari has quirks with navigator.clipboard.writeText() in some contexts.
 * This function tries the modern Clipboard API first, then falls back to
 * execCommand for iOS and older browsers.
 *
 * @param text - Text to copy to clipboard
 * @returns Promise resolving to true if copy succeeded, false otherwise
 *
 * @example
 * ```ts
 * const success = await copyToClipboard('Hello, world!');
 * if (success) {
 *   showToast('Copied!');
 * }
 * ```
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  // Try modern Clipboard API first
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to fallback
    }
  }

  // Fallback for iOS and older browsers
  const textArea = document.createElement('textarea');
  textArea.value = text;

  // Prevent scrolling on iOS
  textArea.style.position = 'fixed';
  textArea.style.left = '-9999px';
  textArea.style.top = '0';
  textArea.style.opacity = '0';

  document.body.appendChild(textArea);

  // iOS specific: need to select with setSelectionRange
  textArea.focus();
  textArea.setSelectionRange(0, text.length);

  let success = false;
  try {
    success = document.execCommand('copy');
  } catch {
    success = false;
  }

  document.body.removeChild(textArea);
  return success;
}
