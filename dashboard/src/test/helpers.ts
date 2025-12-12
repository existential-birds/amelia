/**
 * Shared test helpers for the Amelia Dashboard.
 * Reduces duplication across test files.
 */

import { vi } from 'vitest';

/**
 * Suppress console output during tests.
 * Call in beforeEach, restore with vi.restoreAllMocks() in afterEach.
 */
export function suppressConsoleLogs(): void {
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
}
