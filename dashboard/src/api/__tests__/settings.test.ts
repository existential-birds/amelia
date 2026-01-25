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

describe("settings API", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // ===========================================================================
  // Server Settings
  // ===========================================================================

  describe("getServerSettings", () => {
    it("fetches server settings", async () => {
      const mockSettings: ServerSettings = {
        log_retention_days: 30,
        log_retention_max_events: 10000,
        trace_retention_days: 7,
        checkpoint_retention_days: 0,
        checkpoint_path: "~/.amelia/checkpoints.db",
        websocket_idle_timeout_seconds: 300,
        workflow_start_timeout_seconds: 30,
        max_concurrent: 5,
        stream_tool_results: false,
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSettings,
      } as Response);

      const result = await getServerSettings();

      expect(fetch).toHaveBeenCalledWith(
        "/api/settings",
        expect.objectContaining({
          method: "GET",
          headers: { "Content-Type": "application/json" },
        })
      );
      expect(result).toEqual(mockSettings);
    });

    it("throws error on failure", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => ({ detail: "Database error" }),
      } as Response);

      await expect(getServerSettings()).rejects.toThrow("Database error");
    });
  });

  describe("updateServerSettings", () => {
    it("updates server settings", async () => {
      const mockSettings: ServerSettings = {
        log_retention_days: 60,
        log_retention_max_events: 10000,
        trace_retention_days: 7,
        checkpoint_retention_days: 0,
        checkpoint_path: "~/.amelia/checkpoints.db",
        websocket_idle_timeout_seconds: 300,
        workflow_start_timeout_seconds: 30,
        max_concurrent: 10,
        stream_tool_results: false,
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSettings,
      } as Response);

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
        {
          id: "work",
          tracker: "none",
          working_dir: "/Users/me/projects",
          plan_output_dir: "plans",
          plan_path_pattern: "{issue_id}.md",
          auto_approve_reviews: false,
          agents: {
            architect: {
              driver: "api",
              model: "anthropic/claude-3.5-sonnet",
              options: {},
            },
            developer: {
              driver: "api",
              model: "anthropic/claude-3.5-sonnet",
              options: {},
            },
            reviewer: {
              driver: "api",
              model: "anthropic/claude-3.5-sonnet",
              options: {},
            },
          },
          is_active: true,
        },
        {
          id: "personal",
          tracker: "github",
          working_dir: "/Users/me/personal",
          plan_output_dir: "plans",
          plan_path_pattern: "{issue_id}.md",
          auto_approve_reviews: false,
          agents: {
            architect: {
              driver: "cli",
              model: "claude-sonnet-4-20250514",
              options: {},
            },
            developer: {
              driver: "cli",
              model: "claude-sonnet-4-20250514",
              options: {},
            },
            reviewer: {
              driver: "cli",
              model: "claude-sonnet-4-20250514",
              options: {},
            },
          },
          is_active: false,
        },
      ];

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfiles,
      } as Response);

      const result = await getProfiles();

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles",
        expect.objectContaining({
          method: "GET",
          headers: { "Content-Type": "application/json" },
        })
      );
      expect(result).toEqual(mockProfiles);
      expect(result).toHaveLength(2);
    });

    it("throws error on failure", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => ({}),
      } as Response);

      await expect(getProfiles()).rejects.toThrow(
        "HTTP 500: Internal Server Error"
      );
    });
  });

  describe("getProfile", () => {
    it("fetches a single profile by ID", async () => {
      const mockProfile: Profile = {
        id: "work",
        tracker: "none",
        working_dir: "/Users/me/projects",
        plan_output_dir: "plans",
        plan_path_pattern: "{issue_id}.md",
        auto_approve_reviews: false,
        agents: {
          architect: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
          developer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
          reviewer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
        },
        is_active: true,
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfile,
      } as Response);

      const result = await getProfile("work");

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/work",
        expect.objectContaining({ method: "GET" })
      );
      expect(result).toEqual(mockProfile);
    });

    it("encodes profile ID in URL", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: "my profile" }),
      } as Response);

      await getProfile("my profile");

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/my%20profile",
        expect.any(Object)
      );
    });

    it("throws error when profile not found", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: async () => ({ detail: "Profile not found" }),
      } as Response);

      await expect(getProfile("nonexistent")).rejects.toThrow(
        "Profile not found"
      );
    });
  });

  describe("createProfile", () => {
    it("creates a new profile", async () => {
      const mockProfile: Profile = {
        id: "new-profile",
        tracker: "none",
        working_dir: "/Users/me/projects",
        plan_output_dir: "plans",
        plan_path_pattern: "{issue_id}.md",
        auto_approve_reviews: false,
        agents: {
          architect: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
          developer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
          reviewer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
        },
        is_active: false,
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfile,
      } as Response);

      const createPayload = {
        id: "new-profile",
        working_dir: "/Users/me/projects",
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
      const mockProfile: Profile = {
        id: "work",
        tracker: "none",
        working_dir: "/Users/me/projects",
        plan_output_dir: "plans",
        plan_path_pattern: "{issue_id}.md",
        auto_approve_reviews: true,
        agents: {
          architect: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
          developer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
          reviewer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
        },
        is_active: true,
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfile,
      } as Response);

      const result = await updateProfile("work", { auto_approve_reviews: true });

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/work",
        expect.objectContaining({
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ auto_approve_reviews: true }),
        })
      );
      expect(result).toEqual(mockProfile);
    });
  });

  describe("deleteProfile", () => {
    it("deletes a profile", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
      } as Response);

      await deleteProfile("old-profile");

      expect(fetch).toHaveBeenCalledWith(
        "/api/profiles/old-profile",
        expect.objectContaining({ method: "DELETE" })
      );
    });

    it("throws error when profile not found", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: async () => ({ detail: "Profile not found" }),
      } as Response);

      await expect(deleteProfile("nonexistent")).rejects.toThrow(
        "Profile not found"
      );
    });
  });

  describe("activateProfile", () => {
    it("activates a profile", async () => {
      const mockProfile: Profile = {
        id: "work",
        tracker: "none",
        working_dir: "/Users/me/projects",
        plan_output_dir: "plans",
        plan_path_pattern: "{issue_id}.md",
        auto_approve_reviews: false,
        agents: {
          architect: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
          developer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
          reviewer: {
            driver: "api",
            model: "anthropic/claude-3.5-sonnet",
            options: {},
          },
        },
        is_active: true,
      };

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockProfile,
      } as Response);

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
