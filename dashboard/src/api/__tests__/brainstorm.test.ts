import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { brainstormApi } from "../brainstorm";
import { ApiError } from '../utils';
import { mockFetchSuccess } from "@/test/mocks/fetch";

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
      mockFetchSuccess(mockSessions);

      const result = await brainstormApi.listSessions();

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/brainstorm/sessions"),
        expect.any(Object)
      );
      expect(result).toEqual(mockSessions);
    });

    it("applies filters to query string", async () => {
      mockFetchSuccess([]);

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
      mockFetchSuccess(mockSession);

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
      mockFetchSuccess(mockData);

      const result = await brainstormApi.getSession("s1");

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/brainstorm/sessions/s1"),
        expect.any(Object)
      );
      expect(result).toEqual(mockData);
    });
  });

  describe("sendMessage", () => {
    it("sends message and returns message_id", async () => {
      mockFetchSuccess({ message_id: "m1" });

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
        status: 204,
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
      mockFetchSuccess({ workflow_id: "w1", status: "created" });

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

  describe("error contract", () => {
    it("throws a typed ApiError on an error response", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: "missing", code: "NOT_FOUND" }),
      } as Response);
      const err = await brainstormApi.getSession("x").catch((e) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toMatchObject({ code: "NOT_FOUND", status: 404, message: "missing" });
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
