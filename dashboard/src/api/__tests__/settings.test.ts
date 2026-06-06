import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  getServerSettings,
  updateServerSettings,
  getProfiles,
  getProfile,
  createProfile,
  updateProfile,
  deleteProfile,
  activateProfile,
  type ServerSettings,
  type Profile,
} from "../settings";
import { ApiError } from "../utils";
import { mockFetchSuccess, mockFetchError } from "@/test/mocks/fetch";

function makeProfile(overrides: Partial<Profile> = {}): Profile {
  return {
    id: "work",
    tracker: "noop",
    repo_root: "/Users/me/projects",
    plan_output_dir: "plans",
    plan_path_pattern: "{issue_id}.md",
    agents: {
      architect: { driver: "api", model: "anthropic/claude-3.5-sonnet", options: {} },
      developer: { driver: "api", model: "anthropic/claude-3.5-sonnet", options: {} },
      reviewer: { driver: "api", model: "anthropic/claude-3.5-sonnet", options: {} },
    },
    is_active: true,
    ...overrides,
  };
}

describe("settings API", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("throws a typed ApiError on failure", async () => {
    mockFetchError(404, { detail: "Profile not found" });
    const err = await getProfile("nope").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, message: "Profile not found" });
  });

  // ===========================================================================
  // Server Settings
  // ===========================================================================

  describe("getServerSettings", () => {
    it("fetches server settings", async () => {
      const mockSettings: ServerSettings = {
        log_retention_days: 30,
        log_retention_max_events: 10000,
        checkpoint_retention_days: 0,
        checkpoint_path: "~/.amelia/checkpoints.db",
        websocket_idle_timeout_seconds: 300,
        workflow_start_timeout_seconds: 30,
        max_concurrent: 5,
      };

      mockFetchSuccess(mockSettings);

      const result = await getServerSettings();

      expect(fetch).toHaveBeenCalledWith(
        "/api/settings",
        expect.objectContaining({
          headers: { "Content-Type": "application/json" },
        })
      );
      expect(result).toEqual(mockSettings);
    });

    it("throws error on failure", async () => {
      mockFetchError(500, { detail: "Database error" }, "Internal Server Error");

      await expect(getServerSettings()).rejects.toThrow("Database error");
    });
  });

  describe("updateServerSettings", () => {
    it("updates server settings", async () => {
      const mockSettings: ServerSettings = {
        log_retention_days: 60,
        log_retention_max_events: 10000,
        checkpoint_retention_days: 0,
        checkpoint_path: "~/.amelia/checkpoints.db",
        websocket_idle_timeout_seconds: 300,
        workflow_start_timeout_seconds: 30,
        max_concurrent: 10,
      };

      mockFetchSuccess(mockSettings);

      const result = await updateServerSettings({
        log_retention_days: 60,
        max_concurrent: 10,
      });

      expect(fetch).toHaveBeenCalledWith(
        "/api/settings",
        expect.objectContaining({
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            log_retention_days: 60,
            max_concurrent: 10,
          }),
        })
      );
      expect(result).toEqual(mockSettings);
    });
  });

  // ===========================================================================
  // Profiles
  // ===========================================================================

  describe("getProfiles", () => {
    it("fetches all profiles", async () => {
      const mockProfiles: Profile[] = [
        makeProfile(),
        makeProfile({
          id: "personal",
          tracker: "github",
          repo_root: "/Users/me/personal",
          agents: {
            architect: { driver: "claude", model: "claude-sonnet-4-20250514", options: {} },
            developer: { driver: "claude", model: "claude-sonnet-4-20250514", options: {} },
            reviewer: { driver: "claude", model: "claude-sonnet-4-20250514", options: {} },
          },
          is_active: false,
        }),
      ];

      mockFetchSuccess(mockProfiles);

      const result = await getProfiles();

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles",
        expect.objectContaining({
          headers: { "Content-Type": "application/json" },
        })
      );
      expect(result).toEqual(mockProfiles);
      expect(result).toHaveLength(2);
    });

    it("throws error on failure", async () => {
      mockFetchError(500, {}, "Internal Server Error");

      await expect(getProfiles()).rejects.toThrow(
        "HTTP 500: Internal Server Error"
      );
    });
  });

  describe("getProfile", () => {
    it("fetches a single profile by ID", async () => {
      const mockProfile = makeProfile();

      mockFetchSuccess(mockProfile);

      const result = await getProfile("work");

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/work",
        expect.any(Object)
      );
      expect(result).toEqual(mockProfile);
    });

    it("encodes profile ID in URL", async () => {
      mockFetchSuccess({ id: "my profile" });

      await getProfile("my profile");

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/my%20profile",
        expect.any(Object)
      );
    });

    it("throws error when profile not found", async () => {
      mockFetchError(404, { detail: "Profile not found" }, "Not Found");

      await expect(getProfile("nonexistent")).rejects.toThrow(
        "Profile not found"
      );
    });
  });

  describe("createProfile", () => {
    it("creates a new profile", async () => {
      const mockProfile = makeProfile({ id: "new-profile", is_active: false });

      mockFetchSuccess(mockProfile);

      const createPayload = {
        id: "new-profile",
        repo_root: "/Users/me/projects",
        agents: {
          architect: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
          },
          developer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
          },
          reviewer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
          },
        },
      };

      const result = await createProfile(createPayload);

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(createPayload),
        })
      );
      expect(result).toEqual(mockProfile);
    });
  });

  describe("updateProfile", () => {
    it("updates an existing profile", async () => {
      const mockProfile = makeProfile();

      mockFetchSuccess(mockProfile);

      const result = await updateProfile("work", { tracker: "github" });

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/work",
        expect.objectContaining({
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tracker: "github" }),
        })
      );
      expect(result).toEqual(mockProfile);
    });
  });

  describe("deleteProfile", () => {
    it("deletes a profile", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      } as Response);

      await deleteProfile("old-profile");

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/old-profile",
        expect.objectContaining({ method: "DELETE" })
      );
    });

    it("throws error when profile not found", async () => {
      mockFetchError(404, { detail: "Profile not found" }, "Not Found");

      await expect(deleteProfile("nonexistent")).rejects.toThrow(
        "Profile not found"
      );
    });
  });

  describe("activateProfile", () => {
    it("activates a profile", async () => {
      const mockProfile = makeProfile();

      mockFetchSuccess(mockProfile);

      const result = await activateProfile("work");

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/work/activate",
        expect.objectContaining({ method: "POST" })
      );
      expect(result).toEqual(mockProfile);
      expect(result.is_active).toBe(true);
    });
  });
});
