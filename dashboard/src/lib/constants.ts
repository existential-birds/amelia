/**
 * @fileoverview Application-wide constants and configuration values.
 *
 * Centralizes version info and other constants derived from package.json.
 */

import packageJson from '../../package.json';

/** Current application version from package.json. */
export const APP_VERSION = packageJson.version;
