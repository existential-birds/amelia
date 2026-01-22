/**
 * React Router loaders for settings pages.
 */
import { getServerSettings, getProfiles } from '@/api/settings';
import type { ServerSettings, Profile } from '@/api/settings';

export interface ProfilesLoaderData {
  profiles: Profile[];
}

export interface ServerSettingsLoaderData {
  serverSettings: ServerSettings;
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
