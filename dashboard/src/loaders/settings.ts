/**
 * React Router loaders for settings pages.
 */
import type { LoaderFunctionArgs } from 'react-router-dom';
import { getServerSettings, getProfiles, getProfile } from '@/api/settings';
import type { ServerSettings, Profile } from '@/api/settings';

export interface ProfilesLoaderData {
  profiles: Profile[];
}

export interface ProfileDetailLoaderData {
  profile: Profile | null;
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
 * Loader for the profile detail page (`/settings/profiles/:id` and
 * `/settings/profiles/~new`).
 *
 * Fetches a single profile by id. When no id is present (create mode), or when
 * the API request fails, returns `{ profile: null }` so the page can render a
 * graceful empty/error state rather than tearing down the route entirely.
 *
 * @param args - React Router loader arguments containing route params.
 * @returns Object containing the profile, or `null` in create mode or on error.
 * @example
 * ```typescript
 * const { profile } = await profileDetailLoader({ params: { id: 'work' }, request });
 * ```
 */
export async function profileDetailLoader({
  params,
}: LoaderFunctionArgs): Promise<ProfileDetailLoaderData> {
  if (!params.id) {
    return { profile: null };
  }
  try {
    return { profile: await getProfile(params.id) };
  } catch (err) {
    console.warn('profileDetailLoader: failed to fetch profile', params.id, err);
    return { profile: null };
  }
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
