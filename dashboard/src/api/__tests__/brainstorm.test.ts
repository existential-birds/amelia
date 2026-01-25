import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { brainstormApi } from "../brainstorm";

describe("brainstormApi", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("listSessions", () => {
    it("fetches sessions list", async () => {
      const mockSessions = [
        { id: "s1", profile_id: "p1", status: "active", topic: "Test" },
      ];
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSessions,
      } as Response);

      const result = await brainstormApi.listSessions();

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/brainstorm/sessions"),
        expect.objectContaining({ method: "GET" })
      );
      expect(result).toEqual(mockSessions);
    });

    it("applies filters to query string", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response);

      await brainstormApi.listSessions({ profileId: "p1", status: "active" });

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("profile_id=p1"),
        expect.any(Object)
      );
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("status=active"),
        expect.any(Object)
      );
    });
  });

  describe("createSession", () => {
    it("creates a new session", async () => {
      const mockSession = { id: "s1", profile_id: "p1", status: "active" };
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSession,
      } as Response);

      const result = await brainstormApi.createSession("p1", "Test topic");

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/brainstorm/sessions"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ profile_id: "p1", topic: "Test topic" }),
        })
      );
      expect(result).toEqual(mockSession);
    });
  });

  describe("getSession", () => {
    it("fetches session with history", async () => {
      const mockData = {
        session: { id: "s1" },
        messages: [],
        artifacts: [],
      };
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      } as Response);

      const result = await brainstormApi.getSession("s1");

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/brainstorm/sessions/s1"),
        expect.objectContaining({ method: "GET" })
      );
      expect(result).toEqual(mockData);
    });
  });

  describe("sendMessage", () => {
    it("sends message and returns message_id", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message_id: "m1" }),
      } as Response);

      const result = await brainstormApi.sendMessage("s1", "Hello");

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/brainstorm/sessions/s1/message"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ content: "Hello" }),
        })
      );
      expect(result).toEqual({ message_id: "m1" });
    });
  });

  describe("deleteSession", () => {
    it("deletes a session", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
      } as Response);

      await brainstormApi.deleteSession("s1");

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/brainstorm/sessions/s1"),
        expect.objectContaining({ method: "DELETE" })
      );
    });
  });

  describe("handoff", () => {
    it("hands off session to implementation", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ workflow_id: "w1", status: "created" }),
      } as Response);

      const result = await brainstormApi.handoff("s1", "/path/doc.md", "Title");

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/brainstorm/sessions/s1/handoff"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            artifact_path: "/path/doc.md",
            issue_title: "Title",
          }),
        })
      );
      expect(result).toEqual({ workflow_id: "w1", status: "created" });
    });
  });

  describe("brainstormApi - no primeSession", () => {
    it("should not have primeSession method", () => {
      expect(
        (brainstormApi as Record<string, unknown>).primeSession
      ).toBeUndefined();
    });
  });
});
