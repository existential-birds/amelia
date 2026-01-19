import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useBrainstormSession } from "../useBrainstormSession";
import { useBrainstormStore } from "@/store/brainstormStore";
import { brainstormApi } from "@/api/brainstorm";

vi.mock("@/api/brainstorm");

describe("useBrainstormSession", () => {
  beforeEach(() => {
    useBrainstormStore.setState({
      sessions: [],
      activeSessionId: null,
      activeProfile: null,
      messages: [],
      artifacts: [],
      isStreaming: false,
      drawerOpen: false,
      streamingMessageId: null,
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe("loadSessions", () => {
    it("fetches and stores sessions", async () => {
      const mockSessions = [
        {
          id: "s1",
          profile_id: "p1",
          status: "active" as const,
          topic: "Test",
          driver_session_id: null,
          created_at: "2026-01-18T00:00:00Z",
          updated_at: "2026-01-18T00:00:00Z",
        },
      ];
      vi.mocked(brainstormApi.listSessions).mockResolvedValueOnce(mockSessions);

      const { result } = renderHook(() => useBrainstormSession());

      await act(async () => {
        await result.current.loadSessions();
      });

      expect(brainstormApi.listSessions).toHaveBeenCalled();
      expect(useBrainstormStore.getState().sessions).toEqual(mockSessions);
    });
  });

  describe("loadSession", () => {
    it("fetches session with history", async () => {
      const mockData = {
        session: {
          id: "s1",
          profile_id: "p1",
          status: "active" as const,
          topic: "Test",
          driver_session_id: null,
          created_at: "2026-01-18T00:00:00Z",
          updated_at: "2026-01-18T00:00:00Z",
        },
        messages: [
          {
            id: "m1",
            session_id: "s1",
            sequence: 1,
            role: "user" as const,
            content: "Hello",
            parts: null,
            created_at: "2026-01-18T00:00:00Z",
          },
        ],
        artifacts: [],
        profile: {
          name: "p1",
          driver: "cli:claude",
          model: "sonnet",
        },
      };
      vi.mocked(brainstormApi.getSession).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useBrainstormSession());

      await act(async () => {
        await result.current.loadSession("s1");
      });

      expect(brainstormApi.getSession).toHaveBeenCalledWith("s1");
      expect(useBrainstormStore.getState().activeSessionId).toBe("s1");
      expect(useBrainstormStore.getState().messages).toEqual(mockData.messages);
      expect(useBrainstormStore.getState().activeProfile).toEqual(mockData.profile);
    });
  });

  describe("createSession", () => {
    it("creates session and sends first message", async () => {
      const mockSession = {
        id: "s1",
        profile_id: "p1",
        status: "active" as const,
        topic: "Hello",
        driver_session_id: null,
        created_at: "2026-01-18T00:00:00Z",
        updated_at: "2026-01-18T00:00:00Z",
      };
      vi.mocked(brainstormApi.createSession).mockResolvedValueOnce(mockSession);
      vi.mocked(brainstormApi.sendMessage).mockResolvedValueOnce({
        message_id: "m1",
      });

      const { result } = renderHook(() => useBrainstormSession());

      await act(async () => {
        await result.current.createSession("p1", "Hello");
      });

      expect(brainstormApi.createSession).toHaveBeenCalledWith("p1", "Hello");
      expect(brainstormApi.sendMessage).toHaveBeenCalledWith("s1", "Hello");
      expect(useBrainstormStore.getState().activeSessionId).toBe("s1");
    });
  });

  describe("sendMessage", () => {
    it("sends message to active session", async () => {
      useBrainstormStore.setState({ activeSessionId: "s1" });
      vi.mocked(brainstormApi.sendMessage).mockResolvedValueOnce({
        message_id: "m1",
      });

      const { result } = renderHook(() => useBrainstormSession());

      await act(async () => {
        await result.current.sendMessage("Hello");
      });

      expect(brainstormApi.sendMessage).toHaveBeenCalledWith("s1", "Hello");
      // User message should be optimistically added, plus assistant placeholder
      expect(useBrainstormStore.getState().messages).toHaveLength(2);
      expect(useBrainstormStore.getState().messages[0]!.role).toBe("user");
      expect(useBrainstormStore.getState().messages[1]!.role).toBe("assistant");
    });

    it("throws if no active session", async () => {
      const { result } = renderHook(() => useBrainstormSession());

      await expect(
        act(async () => {
          await result.current.sendMessage("Hello");
        })
      ).rejects.toThrow("No active session");
    });

    it("creates assistant placeholder with streaming status after sending", async () => {
      useBrainstormStore.setState({ activeSessionId: "s1" });
      vi.mocked(brainstormApi.sendMessage).mockResolvedValueOnce({
        message_id: "assistant-1",
      });

      const { result } = renderHook(() => useBrainstormSession());

      await act(async () => {
        await result.current.sendMessage("Hello");
      });

      const messages = useBrainstormStore.getState().messages;
      const assistantMsg = messages.find((m) => m.id === "assistant-1");

      expect(assistantMsg).toBeDefined();
      expect(assistantMsg?.role).toBe("assistant");
      expect(assistantMsg?.content).toBe("");
      expect(assistantMsg?.status).toBe("streaming");
      expect(useBrainstormStore.getState().streamingMessageId).toBe(
        "assistant-1"
      );
    });
  });

  describe("deleteSession", () => {
    it("deletes session and clears if active", async () => {
      useBrainstormStore.setState({
        sessions: [
          {
            id: "s1",
            profile_id: "p1",
            status: "active",
            topic: null,
            driver_session_id: null,
            created_at: "2026-01-18T00:00:00Z",
            updated_at: "2026-01-18T00:00:00Z",
          },
        ],
        activeSessionId: "s1",
        messages: [
          {
            id: "m1",
            session_id: "s1",
            sequence: 1,
            role: "user",
            content: "Hello",
            parts: null,
            created_at: "2026-01-18T00:00:00Z",
          },
        ],
      });
      vi.mocked(brainstormApi.deleteSession).mockResolvedValueOnce();

      const { result } = renderHook(() => useBrainstormSession());

      await act(async () => {
        await result.current.deleteSession("s1");
      });

      expect(brainstormApi.deleteSession).toHaveBeenCalledWith("s1");
      expect(useBrainstormStore.getState().sessions).toHaveLength(0);
      expect(useBrainstormStore.getState().activeSessionId).toBeNull();
      expect(useBrainstormStore.getState().messages).toHaveLength(0);
    });
  });
});
