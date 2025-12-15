/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Application-wide constants and configuration values.
 *
 * Centralizes version info and other constants derived from package.json.
 */

import packageJson from '../../package.json';

/** Current application version from package.json. */
export const APP_VERSION = packageJson.version;
