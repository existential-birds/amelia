/**
 * React Router loaders for settings pages.
 */
import { getServerSettings, getProfiles } from '@/api/settings';
import type { ServerSettings, Profile } from '@/api/settings';

export interface SettingsLoaderData {
  serverSettings: ServerSettings;
  profiles: Profile[];
}

export interface ProfilesLoaderData {
  profiles: Profile[];
}

export interface ServerSettingsLoaderData {
  serverSettings: ServerSettings;
}

/**
 * Loader for the main settings page.
 * Fetches both server settings and all profiles in parallel.
 *
 * @returns Object containing server settings and profiles.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { serverSettings, profiles } = await settingsLoader();
 * ```
 */
export async function settingsLoader(): Promise<SettingsLoaderData> {
  const [serverSettings, profiles] = await Promise.all([
    getServerSettings(),
    getProfiles(),
  ]);
  return { serverSettings, profiles };
}

/**
 * Loader for the profiles page.
 * Fetches all profile configurations.
 *
 * @returns Object containing the list of profiles.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { profiles } = await profilesLoader();
 * ```
 */
export async function profilesLoader(): Promise<ProfilesLoaderData> {
  const profiles = await getProfiles();
  return { profiles };
}

/**
 * Loader for the server settings page.
 * Fetches server-wide settings configuration.
 *
 * @returns Object containing the server settings.
 * @throws {Error} When the API request fails.
 * @example
 * ```typescript
 * const { serverSettings } = await serverSettingsLoader();
 * ```
 */
export async function serverSettingsLoader(): Promise<ServerSettingsLoaderData> {
  const serverSettings = await getServerSettings();
  return { serverSettings };
}
