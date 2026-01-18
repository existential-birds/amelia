# Brainstorming Pipeline UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a chat-based Spec Builder UI where users collaborate with an AI agent across multiple brainstorming sessions, then hand off design documents to the implementation pipeline.

**Architecture:** React page with Zustand store for session/message state, WebSocket integration for streaming responses, and ai-elements components for chat UI. Sessions are managed via a collapsible drawer. The first message auto-creates a session.

**Tech Stack:** React, TypeScript, Zustand, ai-elements (Conversation, Message, Reasoning, PromptInput), shadcn/ui (Sheet, Card, AlertDialog, DropdownMenu), existing WebSocket infrastructure.

---

## Task 1: Add TypeScript Types for Brainstorming

**Files:**
- Modify: `dashboard/src/types/api.ts`

**Step 1: Add type definitions**

Add these types at the end of `api.ts`:

```typescript
// Brainstorming types
export type SessionStatus = "active" | "ready_for_handoff" | "completed" | "failed";

export interface BrainstormingSession {
  id: string;
  profile_id: string;
  driver_session_id: string | null;
  status: SessionStatus;
  topic: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessagePart {
  type: "text" | "reasoning" | "tool_call" | "tool_result";
  text?: string;
  tool_name?: string;
  tool_call_id?: string;
  result?: unknown;
}

export interface BrainstormMessage {
  id: string;
  session_id: string;
  sequence: number;
  role: "user" | "assistant";
  content: string;
  parts: MessagePart[] | null;
  created_at: string;
}

export interface BrainstormArtifact {
  id: string;
  session_id: string;
  type: string;
  path: string;
  title: string | null;
  created_at: string;
}

export interface SessionWithHistory {
  session: BrainstormingSession;
  messages: BrainstormMessage[];
  artifacts: BrainstormArtifact[];
}
```

**Step 2: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add dashboard/src/types/api.ts
git commit -m "feat(dashboard): add brainstorming TypeScript types"
```

---

## Task 2: Add Brainstorming API Client

**Files:**
- Create: `dashboard/src/api/brainstorm.ts`
- Create: `dashboard/src/api/__tests__/brainstorm.test.ts`

**Step 1: Write failing tests for API client**

Create `dashboard/src/api/__tests__/brainstorm.test.ts`:

```typescript
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
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/api/__tests__/brainstorm.test.ts`
Expected: FAIL - module not found

**Step 3: Implement API client**

Create `dashboard/src/api/brainstorm.ts`:

```typescript
import type {
  BrainstormingSession,
  SessionWithHistory,
  SessionStatus,
} from "@/types/api";

const API_BASE_URL = "/api/brainstorm";
const DEFAULT_TIMEOUT_MS = 30000;

function createTimeoutSignal(timeoutMs: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

interface ListSessionsFilters {
  profileId?: string;
  status?: SessionStatus;
  limit?: number;
}

export const brainstormApi = {
  async listSessions(
    filters?: ListSessionsFilters
  ): Promise<BrainstormingSession[]> {
    const params = new URLSearchParams();
    if (filters?.profileId) params.set("profile_id", filters.profileId);
    if (filters?.status) params.set("status", filters.status);
    if (filters?.limit) params.set("limit", String(filters.limit));

    const url = `${API_BASE_URL}/sessions${params.toString() ? `?${params}` : ""}`;
    const response = await fetch(url, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });
    return handleResponse<BrainstormingSession[]>(response);
  },

  async createSession(
    profileId: string,
    topic?: string
  ): Promise<BrainstormingSession> {
    const response = await fetch(`${API_BASE_URL}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId, topic }),
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });
    return handleResponse<BrainstormingSession>(response);
  },

  async getSession(sessionId: string): Promise<SessionWithHistory> {
    const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });
    return handleResponse<SessionWithHistory>(response);
  },

  async sendMessage(
    sessionId: string,
    content: string
  ): Promise<{ message_id: string }> {
    const response = await fetch(
      `${API_BASE_URL}/sessions/${sessionId}/message`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
        signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
      }
    );
    return handleResponse<{ message_id: string }>(response);
  },

  async deleteSession(sessionId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  },

  async handoff(
    sessionId: string,
    artifactPath: string,
    issueTitle?: string
  ): Promise<{ workflow_id: string; status: string }> {
    const response = await fetch(
      `${API_BASE_URL}/sessions/${sessionId}/handoff`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artifact_path: artifactPath,
          issue_title: issueTitle,
        }),
        signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
      }
    );
    return handleResponse<{ workflow_id: string; status: string }>(response);
  },
};
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/api/__tests__/brainstorm.test.ts`
Expected: All tests pass

**Step 5: Commit**

```bash
git add dashboard/src/api/brainstorm.ts dashboard/src/api/__tests__/brainstorm.test.ts
git commit -m "feat(dashboard): add brainstorming API client with tests"
```

---

## Task 3: Create Brainstorm Zustand Store

**Files:**
- Create: `dashboard/src/store/brainstormStore.ts`
- Create: `dashboard/src/store/__tests__/brainstormStore.test.ts`

**Step 1: Write failing store tests**

Create `dashboard/src/store/__tests__/brainstormStore.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { useBrainstormStore } from "../brainstormStore";
import type { BrainstormingSession, BrainstormMessage } from "@/types/api";

describe("useBrainstormStore", () => {
  beforeEach(() => {
    useBrainstormStore.setState({
      sessions: [],
      activeSessionId: null,
      messages: [],
      artifacts: [],
      isStreaming: false,
      drawerOpen: false,
      streamingMessageId: null,
    });
  });

  describe("session management", () => {
    it("sets sessions list", () => {
      const sessions: BrainstormingSession[] = [
        {
          id: "s1",
          profile_id: "p1",
          driver_session_id: null,
          status: "active",
          topic: "Test",
          created_at: "2026-01-18T00:00:00Z",
          updated_at: "2026-01-18T00:00:00Z",
        },
      ];

      useBrainstormStore.getState().setSessions(sessions);

      expect(useBrainstormStore.getState().sessions).toEqual(sessions);
    });

    it("sets active session", () => {
      useBrainstormStore.getState().setActiveSessionId("s1");

      expect(useBrainstormStore.getState().activeSessionId).toBe("s1");
    });

    it("clears active session", () => {
      useBrainstormStore.getState().setActiveSessionId("s1");
      useBrainstormStore.getState().setActiveSessionId(null);

      expect(useBrainstormStore.getState().activeSessionId).toBeNull();
    });
  });

  describe("message management", () => {
    it("adds a user message", () => {
      const message: BrainstormMessage = {
        id: "m1",
        session_id: "s1",
        sequence: 1,
        role: "user",
        content: "Hello",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
      };

      useBrainstormStore.getState().addMessage(message);

      expect(useBrainstormStore.getState().messages).toHaveLength(1);
      expect(useBrainstormStore.getState().messages[0]).toEqual(message);
    });

    it("updates existing message content", () => {
      const message: BrainstormMessage = {
        id: "m1",
        session_id: "s1",
        sequence: 1,
        role: "assistant",
        content: "Hello",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
      };
      useBrainstormStore.getState().addMessage(message);

      useBrainstormStore.getState().updateMessageContent("m1", "Hello world");

      expect(useBrainstormStore.getState().messages[0].content).toBe(
        "Hello world"
      );
    });

    it("appends to existing message content", () => {
      const message: BrainstormMessage = {
        id: "m1",
        session_id: "s1",
        sequence: 1,
        role: "assistant",
        content: "Hello",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
      };
      useBrainstormStore.getState().addMessage(message);

      useBrainstormStore.getState().appendMessageContent("m1", " world");

      expect(useBrainstormStore.getState().messages[0].content).toBe(
        "Hello world"
      );
    });

    it("clears messages", () => {
      useBrainstormStore.getState().addMessage({
        id: "m1",
        session_id: "s1",
        sequence: 1,
        role: "user",
        content: "Hello",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
      });

      useBrainstormStore.getState().clearMessages();

      expect(useBrainstormStore.getState().messages).toHaveLength(0);
    });
  });

  describe("streaming state", () => {
    it("sets streaming state", () => {
      useBrainstormStore.getState().setStreaming(true, "m1");

      expect(useBrainstormStore.getState().isStreaming).toBe(true);
      expect(useBrainstormStore.getState().streamingMessageId).toBe("m1");
    });

    it("clears streaming state", () => {
      useBrainstormStore.getState().setStreaming(true, "m1");
      useBrainstormStore.getState().setStreaming(false, null);

      expect(useBrainstormStore.getState().isStreaming).toBe(false);
      expect(useBrainstormStore.getState().streamingMessageId).toBeNull();
    });
  });

  describe("drawer state", () => {
    it("toggles drawer", () => {
      expect(useBrainstormStore.getState().drawerOpen).toBe(false);

      useBrainstormStore.getState().setDrawerOpen(true);
      expect(useBrainstormStore.getState().drawerOpen).toBe(true);

      useBrainstormStore.getState().setDrawerOpen(false);
      expect(useBrainstormStore.getState().drawerOpen).toBe(false);
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/store/__tests__/brainstormStore.test.ts`
Expected: FAIL - module not found

**Step 3: Implement the store**

Create `dashboard/src/store/brainstormStore.ts`:

```typescript
import { create } from "zustand";
import type {
  BrainstormingSession,
  BrainstormMessage,
  BrainstormArtifact,
} from "@/types/api";

interface BrainstormState {
  // Session management
  sessions: BrainstormingSession[];
  activeSessionId: string | null;

  // Current conversation
  messages: BrainstormMessage[];
  artifacts: BrainstormArtifact[];

  // UI state
  isStreaming: boolean;
  streamingMessageId: string | null;
  drawerOpen: boolean;

  // Session actions
  setSessions: (sessions: BrainstormingSession[]) => void;
  addSession: (session: BrainstormingSession) => void;
  updateSession: (
    sessionId: string,
    updates: Partial<BrainstormingSession>
  ) => void;
  removeSession: (sessionId: string) => void;
  setActiveSessionId: (sessionId: string | null) => void;

  // Message actions
  setMessages: (messages: BrainstormMessage[]) => void;
  addMessage: (message: BrainstormMessage) => void;
  removeMessage: (messageId: string) => void;
  updateMessageContent: (messageId: string, content: string) => void;
  appendMessageContent: (messageId: string, content: string) => void;
  clearMessages: () => void;

  // Artifact actions
  setArtifacts: (artifacts: BrainstormArtifact[]) => void;
  addArtifact: (artifact: BrainstormArtifact) => void;

  // UI actions
  setStreaming: (streaming: boolean, messageId: string | null) => void;
  setDrawerOpen: (open: boolean) => void;
}

export const useBrainstormStore = create<BrainstormState>()((set) => ({
  // Initial state
  sessions: [],
  activeSessionId: null,
  messages: [],
  artifacts: [],
  isStreaming: false,
  streamingMessageId: null,
  drawerOpen: false,

  // Session actions
  setSessions: (sessions) => set({ sessions }),

  addSession: (session) =>
    set((state) => ({ sessions: [session, ...state.sessions] })),

  updateSession: (sessionId, updates) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, ...updates } : s
      ),
    })),

  removeSession: (sessionId) =>
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== sessionId),
      activeSessionId:
        state.activeSessionId === sessionId ? null : state.activeSessionId,
    })),

  setActiveSessionId: (sessionId) => set({ activeSessionId: sessionId }),

  // Message actions
  setMessages: (messages) => set({ messages }),

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  removeMessage: (messageId) =>
    set((state) => ({
      messages: state.messages.filter((m) => m.id !== messageId),
    })),

  updateMessageContent: (messageId, content) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId ? { ...m, content } : m
      ),
    })),

  appendMessageContent: (messageId, content) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId ? { ...m, content: m.content + content } : m
      ),
    })),

  clearMessages: () => set({ messages: [], artifacts: [] }),

  // Artifact actions
  setArtifacts: (artifacts) => set({ artifacts }),

  addArtifact: (artifact) =>
    set((state) => ({ artifacts: [...state.artifacts, artifact] })),

  // UI actions
  setStreaming: (streaming, messageId) =>
    set({ isStreaming: streaming, streamingMessageId: messageId }),

  setDrawerOpen: (open) => set({ drawerOpen: open }),
}));
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/store/__tests__/brainstormStore.test.ts`
Expected: All tests pass

**Step 5: Commit**

```bash
git add dashboard/src/store/brainstormStore.ts dashboard/src/store/__tests__/brainstormStore.test.ts
git commit -m "feat(dashboard): add brainstorming Zustand store with tests"
```

---

## Task 4: Create useBrainstormSession Hook

**Files:**
- Create: `dashboard/src/hooks/useBrainstormSession.ts`
- Create: `dashboard/src/hooks/__tests__/useBrainstormSession.test.ts`

**Step 1: Write failing hook tests**

Create `dashboard/src/hooks/__tests__/useBrainstormSession.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useBrainstormSession } from "../useBrainstormSession";
import { useBrainstormStore } from "@/store/brainstormStore";
import { brainstormApi } from "@/api/brainstorm";

vi.mock("@/api/brainstorm");

describe("useBrainstormSession", () => {
  beforeEach(() => {
    useBrainstormStore.setState({
      sessions: [],
      activeSessionId: null,
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
      };
      vi.mocked(brainstormApi.getSession).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useBrainstormSession());

      await act(async () => {
        await result.current.loadSession("s1");
      });

      expect(brainstormApi.getSession).toHaveBeenCalledWith("s1");
      expect(useBrainstormStore.getState().activeSessionId).toBe("s1");
      expect(useBrainstormStore.getState().messages).toEqual(mockData.messages);
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
      // User message should be optimistically added
      expect(useBrainstormStore.getState().messages).toHaveLength(1);
      expect(useBrainstormStore.getState().messages[0].role).toBe("user");
    });

    it("throws if no active session", async () => {
      const { result } = renderHook(() => useBrainstormSession());

      await expect(
        act(async () => {
          await result.current.sendMessage("Hello");
        })
      ).rejects.toThrow("No active session");
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
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/hooks/__tests__/useBrainstormSession.test.ts`
Expected: FAIL - module not found

**Step 3: Implement the hook**

Create `dashboard/src/hooks/useBrainstormSession.ts`:

```typescript
import { useCallback } from "react";
import { nanoid } from "nanoid";
import { brainstormApi } from "@/api/brainstorm";
import { useBrainstormStore } from "@/store/brainstormStore";
import type { SessionStatus } from "@/types/api";

export function useBrainstormSession() {
  const {
    activeSessionId,
    messages,
    setSessions,
    addSession,
    removeSession,
    setActiveSessionId,
    setMessages,
    addMessage,
    removeMessage,
    setArtifacts,
    clearMessages,
    setStreaming,
    setDrawerOpen,
  } = useBrainstormStore();

  const loadSessions = useCallback(
    async (filters?: { profileId?: string; status?: SessionStatus }) => {
      const sessions = await brainstormApi.listSessions(filters);
      setSessions(sessions);
    },
    [setSessions]
  );

  const loadSession = useCallback(
    async (sessionId: string) => {
      const data = await brainstormApi.getSession(sessionId);
      setActiveSessionId(sessionId);
      setMessages(data.messages);
      setArtifacts(data.artifacts);
      setDrawerOpen(false);
    },
    [setActiveSessionId, setMessages, setArtifacts, setDrawerOpen]
  );

  const createSession = useCallback(
    async (profileId: string, firstMessage: string) => {
      // Create session with first message as topic
      const session = await brainstormApi.createSession(profileId, firstMessage);
      addSession(session);
      setActiveSessionId(session.id);
      clearMessages();

      // Add optimistic user message
      const userMessage = {
        id: nanoid(),
        session_id: session.id,
        sequence: 1,
        role: "user" as const,
        content: firstMessage,
        parts: null,
        created_at: new Date().toISOString(),
      };
      addMessage(userMessage);

      // Send the message
      setStreaming(true, null);
      await brainstormApi.sendMessage(session.id, firstMessage);
      // Response comes via WebSocket - streaming will be set to false when complete
    },
    [addSession, setActiveSessionId, clearMessages, addMessage, setStreaming]
  );

  const sendMessage = useCallback(
    async (content: string) => {
      if (!activeSessionId) {
        throw new Error("No active session");
      }

      const optimisticId = nanoid();
      const userMessage = {
        id: optimisticId,
        session_id: activeSessionId,
        sequence: messages.length + 1,
        role: "user" as const,
        content,
        parts: null,
        created_at: new Date().toISOString(),
      };

      try {
        addMessage(userMessage);
        setStreaming(true, null);
        await brainstormApi.sendMessage(activeSessionId, content);
        // Response comes via WebSocket
      } catch (error) {
        // Rollback optimistic update
        removeMessage(optimisticId);
        setStreaming(false, null);
        throw error;
      }
    },
    [activeSessionId, messages.length, addMessage, removeMessage, setStreaming]
  );

  const deleteSession = useCallback(
    async (sessionId: string) => {
      await brainstormApi.deleteSession(sessionId);
      removeSession(sessionId);
      if (activeSessionId === sessionId) {
        clearMessages();
      }
    },
    [activeSessionId, removeSession, clearMessages]
  );

  const handoff = useCallback(
    async (artifactPath: string, issueTitle?: string) => {
      if (!activeSessionId) {
        throw new Error("No active session");
      }
      return brainstormApi.handoff(activeSessionId, artifactPath, issueTitle);
    },
    [activeSessionId]
  );

  const startNewSession = useCallback(() => {
    setActiveSessionId(null);
    clearMessages();
    setDrawerOpen(false);
  }, [setActiveSessionId, clearMessages, setDrawerOpen]);

  return {
    activeSessionId,
    loadSessions,
    loadSession,
    createSession,
    sendMessage,
    deleteSession,
    handoff,
    startNewSession,
  };
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/hooks/__tests__/useBrainstormSession.test.ts`
Expected: All tests pass

**Step 5: Commit**

```bash
git add dashboard/src/hooks/useBrainstormSession.ts dashboard/src/hooks/__tests__/useBrainstormSession.test.ts
git commit -m "feat(dashboard): add useBrainstormSession hook with tests"
```

---

## Task 5: Create SessionListItem Component

**Files:**
- Create: `dashboard/src/components/brainstorm/SessionListItem.tsx`
- Create: `dashboard/src/components/brainstorm/__tests__/SessionListItem.test.tsx`

**Step 1: Write failing component tests**

Create `dashboard/src/components/brainstorm/__tests__/SessionListItem.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SessionListItem } from "../SessionListItem";
import type { BrainstormingSession } from "@/types/api";

const mockSession: BrainstormingSession = {
  id: "s1",
  profile_id: "p1",
  driver_session_id: null,
  status: "active",
  topic: "Test Session",
  created_at: "2026-01-18T10:00:00Z",
  updated_at: "2026-01-18T10:05:00Z",
};

describe("SessionListItem", () => {
  it("renders session topic", () => {
    render(
      <SessionListItem
        session={mockSession}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("Test Session")).toBeInTheDocument();
  });

  it("renders 'Untitled' for sessions without topic", () => {
    render(
      <SessionListItem
        session={{ ...mockSession, topic: null }}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("Untitled")).toBeInTheDocument();
  });

  it("shows status indicator based on session status", () => {
    const { rerender } = render(
      <SessionListItem
        session={{ ...mockSession, status: "active" }}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByTestId("status-indicator")).toHaveClass(
      "bg-status-running"
    );

    rerender(
      <SessionListItem
        session={{ ...mockSession, status: "completed" }}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByTestId("status-indicator")).toHaveClass(
      "bg-status-completed"
    );
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = vi.fn();
    render(
      <SessionListItem
        session={mockSession}
        isSelected={false}
        onSelect={onSelect}
        onDelete={vi.fn()}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /test session/i }));

    expect(onSelect).toHaveBeenCalledWith("s1");
  });

  it("shows selected state", () => {
    render(
      <SessionListItem
        session={mockSession}
        isSelected={true}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /test session/i })).toHaveClass(
      "bg-accent"
    );
  });

  it("calls onDelete from overflow menu", async () => {
    const onDelete = vi.fn();
    render(
      <SessionListItem
        session={mockSession}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={onDelete}
      />
    );

    // Open overflow menu
    await userEvent.click(screen.getByRole("button", { name: /options/i }));

    // Click delete
    await userEvent.click(screen.getByRole("menuitem", { name: /delete/i }));

    expect(onDelete).toHaveBeenCalledWith("s1");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/components/brainstorm/__tests__/SessionListItem.test.tsx`
Expected: FAIL - module not found

**Step 3: Create the component**

Create `dashboard/src/components/brainstorm/SessionListItem.tsx`:

```typescript
import { formatDistanceToNow } from "date-fns";
import { MoreHorizontal, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { BrainstormingSession, SessionStatus } from "@/types/api";

interface SessionListItemProps {
  session: BrainstormingSession;
  isSelected: boolean;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

const statusStyles: Record<SessionStatus, string> = {
  active: "bg-status-running",
  ready_for_handoff: "bg-status-pending",
  completed: "bg-status-completed",
  failed: "bg-status-failed",
};

export function SessionListItem({
  session,
  isSelected,
  onSelect,
  onDelete,
}: SessionListItemProps) {
  const timeAgo = formatDistanceToNow(new Date(session.updated_at), {
    addSuffix: true,
  });

  return (
    <div
      className={cn(
        "group flex items-center gap-2 rounded-lg p-2 transition-colors",
        isSelected ? "bg-accent" : "hover:bg-accent/50"
      )}
    >
      <Button
        variant="ghost"
        className="flex-1 justify-start gap-3 h-auto py-2 px-2"
        onClick={() => onSelect(session.id)}
        aria-label={session.topic || "Untitled"}
      >
        <span
          data-testid="status-indicator"
          className={cn("h-2 w-2 rounded-full shrink-0", statusStyles[session.status])}
        />
        <div className="flex flex-col items-start text-left min-w-0">
          <span className="text-sm font-medium truncate w-full">
            {session.topic || "Untitled"}
          </span>
          <span className="text-xs text-muted-foreground">{timeAgo}</span>
        </div>
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 opacity-0 group-hover:opacity-100 focus:opacity-100"
            aria-label="Options"
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onClick={() => onDelete(session.id)}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
```

**Step 4: Add date-fns if not installed**

Check if date-fns exists in package.json. If not:

Run: `cd dashboard && pnpm add date-fns`

**Step 5: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/components/brainstorm/__tests__/SessionListItem.test.tsx`
Expected: All tests pass

**Step 6: Commit**

```bash
git add dashboard/src/components/brainstorm/SessionListItem.tsx dashboard/src/components/brainstorm/__tests__/SessionListItem.test.tsx
git commit -m "feat(dashboard): add SessionListItem component with tests"
```

---

## Task 6: Create SessionDrawer Component

**Files:**
- Create: `dashboard/src/components/brainstorm/SessionDrawer.tsx`
- Create: `dashboard/src/components/brainstorm/__tests__/SessionDrawer.test.tsx`

**Step 1: Write failing component tests**

Create `dashboard/src/components/brainstorm/__tests__/SessionDrawer.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SessionDrawer } from "../SessionDrawer";
import { useBrainstormStore } from "@/store/brainstormStore";
import type { BrainstormingSession } from "@/types/api";

const mockSessions: BrainstormingSession[] = [
  {
    id: "s1",
    profile_id: "p1",
    driver_session_id: null,
    status: "active",
    topic: "Active Session",
    created_at: "2026-01-18T10:00:00Z",
    updated_at: "2026-01-18T10:05:00Z",
  },
  {
    id: "s2",
    profile_id: "p1",
    driver_session_id: null,
    status: "completed",
    topic: "Completed Session",
    created_at: "2026-01-17T10:00:00Z",
    updated_at: "2026-01-17T10:05:00Z",
  },
];

describe("SessionDrawer", () => {
  beforeEach(() => {
    useBrainstormStore.setState({
      sessions: mockSessions,
      activeSessionId: "s1",
      drawerOpen: true,
    });
  });

  it("renders session list grouped by status", () => {
    render(
      <SessionDrawer onSelectSession={vi.fn()} onDeleteSession={vi.fn()} onNewSession={vi.fn()} />
    );

    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Active Session")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Completed Session")).toBeInTheDocument();
  });

  it("calls onSelectSession when session is clicked", async () => {
    const onSelectSession = vi.fn();
    render(
      <SessionDrawer
        onSelectSession={onSelectSession}
        onDeleteSession={vi.fn()}
        onNewSession={vi.fn()}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /completed session/i }));

    expect(onSelectSession).toHaveBeenCalledWith("s2");
  });

  it("calls onNewSession when new session button is clicked", async () => {
    const onNewSession = vi.fn();
    render(
      <SessionDrawer
        onSelectSession={vi.fn()}
        onDeleteSession={vi.fn()}
        onNewSession={onNewSession}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /new session/i }));

    expect(onNewSession).toHaveBeenCalled();
  });

  it("shows empty state when no sessions", () => {
    useBrainstormStore.setState({ sessions: [] });

    render(
      <SessionDrawer onSelectSession={vi.fn()} onDeleteSession={vi.fn()} onNewSession={vi.fn()} />
    );

    expect(screen.getByText(/no sessions yet/i)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/components/brainstorm/__tests__/SessionDrawer.test.tsx`
Expected: FAIL - module not found

**Step 3: Create the component**

Create `dashboard/src/components/brainstorm/SessionDrawer.tsx`:

```typescript
import { Plus } from "lucide-react";
import { useBrainstormStore } from "@/store/brainstormStore";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SessionListItem } from "./SessionListItem";
import type { BrainstormingSession, SessionStatus } from "@/types/api";

interface SessionDrawerProps {
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onNewSession: () => void;
}

const statusOrder: SessionStatus[] = [
  "active",
  "ready_for_handoff",
  "completed",
  "failed",
];

const statusLabels: Record<SessionStatus, string> = {
  active: "Active",
  ready_for_handoff: "Ready for Handoff",
  completed: "Completed",
  failed: "Failed",
};

function groupByStatus(
  sessions: BrainstormingSession[]
): Record<SessionStatus, BrainstormingSession[]> {
  const groups: Record<SessionStatus, BrainstormingSession[]> = {
    active: [],
    ready_for_handoff: [],
    completed: [],
    failed: [],
  };

  for (const session of sessions) {
    groups[session.status].push(session);
  }

  return groups;
}

export function SessionDrawer({
  onSelectSession,
  onDeleteSession,
  onNewSession,
}: SessionDrawerProps) {
  const { sessions, activeSessionId, drawerOpen, setDrawerOpen } =
    useBrainstormStore();

  const groupedSessions = groupByStatus(sessions);
  const hasAnySessions = sessions.length > 0;

  return (
    <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
      <SheetContent side="left" className="w-80 p-0">
        <SheetHeader className="px-4 py-4 border-b">
          <SheetTitle>Sessions</SheetTitle>
        </SheetHeader>

        <ScrollArea className="flex-1 h-[calc(100vh-8rem)]">
          <div className="p-2">
            {!hasAnySessions ? (
              <p className="text-center text-muted-foreground py-8">
                No sessions yet. Start a new conversation below.
              </p>
            ) : (
              statusOrder.map((status) => {
                const sessionsInGroup = groupedSessions[status];
                if (sessionsInGroup.length === 0) return null;

                return (
                  <div key={status} className="mb-4">
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-2 mb-2">
                      {statusLabels[status]}
                    </h3>
                    <div className="space-y-1">
                      {sessionsInGroup.map((session) => (
                        <SessionListItem
                          key={session.id}
                          session={session}
                          isSelected={session.id === activeSessionId}
                          onSelect={onSelectSession}
                          onDelete={onDeleteSession}
                        />
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>

        <div className="border-t p-4">
          <Button
            variant="outline"
            className="w-full"
            onClick={onNewSession}
            aria-label="New Session"
          >
            <Plus className="h-4 w-4 mr-2" />
            New Session
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/components/brainstorm/__tests__/SessionDrawer.test.tsx`
Expected: All tests pass

**Step 5: Commit**

```bash
git add dashboard/src/components/brainstorm/SessionDrawer.tsx dashboard/src/components/brainstorm/__tests__/SessionDrawer.test.tsx
git commit -m "feat(dashboard): add SessionDrawer component with tests"
```

---

## Task 7: Create ArtifactCard Component

**Files:**
- Create: `dashboard/src/components/brainstorm/ArtifactCard.tsx`
- Create: `dashboard/src/components/brainstorm/__tests__/ArtifactCard.test.tsx`

**Step 1: Write failing component tests**

Create `dashboard/src/components/brainstorm/__tests__/ArtifactCard.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArtifactCard } from "../ArtifactCard";
import type { BrainstormArtifact } from "@/types/api";

const mockArtifact: BrainstormArtifact = {
  id: "a1",
  session_id: "s1",
  type: "design",
  path: "docs/plans/2026-01-18-caching-design.md",
  title: "Caching Layer Design",
  created_at: "2026-01-18T10:00:00Z",
};

describe("ArtifactCard", () => {
  it("renders artifact path", () => {
    render(<ArtifactCard artifact={mockArtifact} onHandoff={vi.fn()} />);

    expect(
      screen.getByText("docs/plans/2026-01-18-caching-design.md")
    ).toBeInTheDocument();
  });

  it("renders title if present", () => {
    render(<ArtifactCard artifact={mockArtifact} onHandoff={vi.fn()} />);

    expect(screen.getByText("Caching Layer Design")).toBeInTheDocument();
  });

  it("shows success indicator", () => {
    render(<ArtifactCard artifact={mockArtifact} onHandoff={vi.fn()} />);

    expect(screen.getByText(/design document created/i)).toBeInTheDocument();
  });

  it("calls onHandoff when handoff button is clicked", async () => {
    const onHandoff = vi.fn();
    render(<ArtifactCard artifact={mockArtifact} onHandoff={onHandoff} />);

    await userEvent.click(
      screen.getByRole("button", { name: /hand off to implementation/i })
    );

    expect(onHandoff).toHaveBeenCalledWith(mockArtifact);
  });

  it("disables handoff when isHandingOff is true", () => {
    render(
      <ArtifactCard
        artifact={mockArtifact}
        onHandoff={vi.fn()}
        isHandingOff={true}
      />
    );

    expect(
      screen.getByRole("button", { name: /hand off to implementation/i })
    ).toBeDisabled();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/components/brainstorm/__tests__/ArtifactCard.test.tsx`
Expected: FAIL - module not found

**Step 3: Create the component**

Create `dashboard/src/components/brainstorm/ArtifactCard.tsx`:

```typescript
import { CheckCircle2, FileText, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import type { BrainstormArtifact } from "@/types/api";

interface ArtifactCardProps {
  artifact: BrainstormArtifact;
  onHandoff: (artifact: BrainstormArtifact) => void;
  isHandingOff?: boolean;
}

export function ArtifactCard({
  artifact,
  onHandoff,
  isHandingOff = false,
}: ArtifactCardProps) {
  return (
    <Card className="border-l-4 border-l-status-completed">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2 text-status-completed">
          <CheckCircle2 className="h-4 w-4" />
          <span className="text-sm font-medium">Design document created</span>
        </div>
      </CardHeader>
      <CardContent className="pb-3">
        {artifact.title && (
          <p className="font-medium mb-1">{artifact.title}</p>
        )}
        <div className="flex items-center gap-2 text-muted-foreground">
          <FileText className="h-4 w-4 shrink-0" />
          <code className="text-xs bg-muted px-1.5 py-0.5 rounded truncate">
            {artifact.path}
          </code>
        </div>
      </CardContent>
      <CardFooter className="gap-2">
        <Button variant="secondary" size="sm" asChild>
          <a
            href={`/api/files/${encodeURIComponent(artifact.path)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            View Document
          </a>
        </Button>
        <Button
          size="sm"
          onClick={() => onHandoff(artifact)}
          disabled={isHandingOff}
          aria-label="Hand off to Implementation"
        >
          {isHandingOff ? (
            "Handing off..."
          ) : (
            <>
              Hand off to Implementation
              <ArrowRight className="h-4 w-4 ml-1" />
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/components/brainstorm/__tests__/ArtifactCard.test.tsx`
Expected: All tests pass

**Step 5: Commit**

```bash
git add dashboard/src/components/brainstorm/ArtifactCard.tsx dashboard/src/components/brainstorm/__tests__/ArtifactCard.test.tsx
git commit -m "feat(dashboard): add ArtifactCard component with tests"
```

---

## Task 8: Create HandoffDialog Component

**Files:**
- Create: `dashboard/src/components/brainstorm/HandoffDialog.tsx`
- Create: `dashboard/src/components/brainstorm/__tests__/HandoffDialog.test.tsx`

**Step 1: Write failing component tests**

Create `dashboard/src/components/brainstorm/__tests__/HandoffDialog.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HandoffDialog } from "../HandoffDialog";
import type { BrainstormArtifact } from "@/types/api";

const mockArtifact: BrainstormArtifact = {
  id: "a1",
  session_id: "s1",
  type: "design",
  path: "docs/plans/2026-01-18-caching-design.md",
  title: "Caching Layer Design",
  created_at: "2026-01-18T10:00:00Z",
};

describe("HandoffDialog", () => {
  it("renders dialog when open", () => {
    render(
      <HandoffDialog
        open={true}
        artifact={mockArtifact}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByText("Hand off to Implementation")).toBeInTheDocument();
  });

  it("pre-fills issue title from artifact title", () => {
    render(
      <HandoffDialog
        open={true}
        artifact={mockArtifact}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByLabelText(/issue title/i)).toHaveValue(
      "Implement Caching Layer Design"
    );
  });

  it("calls onConfirm with title when confirmed", async () => {
    const onConfirm = vi.fn();
    render(
      <HandoffDialog
        open={true}
        artifact={mockArtifact}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );

    await userEvent.click(
      screen.getByRole("button", { name: /create workflow/i })
    );

    expect(onConfirm).toHaveBeenCalledWith("Implement Caching Layer Design");
  });

  it("calls onConfirm with custom title", async () => {
    const onConfirm = vi.fn();
    render(
      <HandoffDialog
        open={true}
        artifact={mockArtifact}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );

    const input = screen.getByLabelText(/issue title/i);
    await userEvent.clear(input);
    await userEvent.type(input, "Custom Title");
    await userEvent.click(
      screen.getByRole("button", { name: /create workflow/i })
    );

    expect(onConfirm).toHaveBeenCalledWith("Custom Title");
  });

  it("calls onCancel when cancel button is clicked", async () => {
    const onCancel = vi.fn();
    render(
      <HandoffDialog
        open={true}
        artifact={mockArtifact}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onCancel).toHaveBeenCalled();
  });

  it("disables confirm when isLoading", () => {
    render(
      <HandoffDialog
        open={true}
        artifact={mockArtifact}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isLoading={true}
      />
    );

    expect(
      screen.getByRole("button", { name: /create workflow/i })
    ).toBeDisabled();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/components/brainstorm/__tests__/HandoffDialog.test.tsx`
Expected: FAIL - module not found

**Step 3: Create the component**

Create `dashboard/src/components/brainstorm/HandoffDialog.tsx`:

```typescript
import { useState, useEffect } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { BrainstormArtifact } from "@/types/api";

interface HandoffDialogProps {
  open: boolean;
  artifact: BrainstormArtifact | null;
  onConfirm: (issueTitle: string) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

export function HandoffDialog({
  open,
  artifact,
  onConfirm,
  onCancel,
  isLoading = false,
}: HandoffDialogProps) {
  const [issueTitle, setIssueTitle] = useState("");

  // Pre-fill title from artifact
  useEffect(() => {
    if (artifact?.title) {
      setIssueTitle(`Implement ${artifact.title}`);
    } else {
      setIssueTitle("");
    }
  }, [artifact]);

  const handleConfirm = () => {
    onConfirm(issueTitle);
  };

  return (
    <AlertDialog open={open}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Hand off to Implementation</AlertDialogTitle>
          <AlertDialogDescription>
            This will create a new implementation workflow from your design
            document.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="py-4">
          <Label htmlFor="issue-title">Issue title (optional)</Label>
          <Input
            id="issue-title"
            value={issueTitle}
            onChange={(e) => setIssueTitle(e.target.value)}
            placeholder="Implement feature..."
            className="mt-2"
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} disabled={isLoading}>
            {isLoading ? "Creating..." : "Create Workflow →"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/components/brainstorm/__tests__/HandoffDialog.test.tsx`
Expected: All tests pass

**Step 5: Commit**

```bash
git add dashboard/src/components/brainstorm/HandoffDialog.tsx dashboard/src/components/brainstorm/__tests__/HandoffDialog.test.tsx
git commit -m "feat(dashboard): add HandoffDialog component with tests"
```

---

## Task 9: Create Component Index

**Files:**
- Create: `dashboard/src/components/brainstorm/index.ts`

**Step 1: Create barrel export**

Create `dashboard/src/components/brainstorm/index.ts`:

```typescript
export { SessionListItem } from "./SessionListItem";
export { SessionDrawer } from "./SessionDrawer";
export { ArtifactCard } from "./ArtifactCard";
export { HandoffDialog } from "./HandoffDialog";
```

**Step 2: Commit**

```bash
git add dashboard/src/components/brainstorm/index.ts
git commit -m "feat(dashboard): add brainstorm components barrel export"
```

---

## Task 10: Create SpecBuilderPage Component

**Files:**
- Create: `dashboard/src/pages/SpecBuilderPage.tsx`
- Create: `dashboard/src/pages/__tests__/SpecBuilderPage.test.tsx`

**Step 0: Install ai-elements components**

Run: `cd dashboard && pnpm dlx ai-elements add conversation message prompt-input reasoning`

Then update imports in SpecBuilderPage.tsx to use local paths:
```typescript
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from "@/components/ai-elements/reasoning";
```

**Step 1: Write failing page tests**

Create `dashboard/src/pages/__tests__/SpecBuilderPage.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import SpecBuilderPage from "../SpecBuilderPage";
import { useBrainstormStore } from "@/store/brainstormStore";
import { brainstormApi } from "@/api/brainstorm";

vi.mock("@/api/brainstorm");

function renderPage() {
  return render(
    <MemoryRouter>
      <SpecBuilderPage />
    </MemoryRouter>
  );
}

describe("SpecBuilderPage", () => {
  beforeEach(() => {
    useBrainstormStore.setState({
      sessions: [],
      activeSessionId: null,
      messages: [],
      artifacts: [],
      isStreaming: false,
      drawerOpen: false,
      streamingMessageId: null,
    });
    vi.clearAllMocks();
    vi.mocked(brainstormApi.listSessions).mockResolvedValue([]);
  });

  it("renders page header", async () => {
    renderPage();

    expect(screen.getByText("Spec Builder")).toBeInTheDocument();
  });

  it("shows empty state when no active session", async () => {
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(/start a brainstorming session/i)
      ).toBeInTheDocument();
    });
  });

  it("loads sessions on mount", async () => {
    renderPage();

    await waitFor(() => {
      expect(brainstormApi.listSessions).toHaveBeenCalled();
    });
  });

  it("shows input area", () => {
    renderPage();

    expect(
      screen.getByPlaceholderText(/what would you like to design/i)
    ).toBeInTheDocument();
  });

  it("creates session on first message", async () => {
    const mockSession = {
      id: "s1",
      profile_id: "default",
      driver_session_id: null,
      status: "active" as const,
      topic: "Test",
      created_at: "2026-01-18T00:00:00Z",
      updated_at: "2026-01-18T00:00:00Z",
    };
    vi.mocked(brainstormApi.createSession).mockResolvedValue(mockSession);
    vi.mocked(brainstormApi.sendMessage).mockResolvedValue({ message_id: "m1" });

    renderPage();

    const input = screen.getByPlaceholderText(/what would you like to design/i);
    await userEvent.type(input, "Design a caching layer{enter}");

    await waitFor(() => {
      expect(brainstormApi.createSession).toHaveBeenCalledWith(
        "default",
        "Design a caching layer"
      );
    });
  });

  it("opens drawer when hamburger is clicked", async () => {
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: /open sessions/i }));

    expect(useBrainstormStore.getState().drawerOpen).toBe(true);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run src/pages/__tests__/SpecBuilderPage.test.tsx`
Expected: FAIL - module not found

**Step 3: Create the page component**

Create `dashboard/src/pages/SpecBuilderPage.tsx`:

```typescript
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Menu, Plus, Lightbulb } from "lucide-react";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from "@/components/ai-elements/reasoning";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { useBrainstormStore } from "@/store/brainstormStore";
import { useBrainstormSession } from "@/hooks/useBrainstormSession";
import {
  SessionDrawer,
  ArtifactCard,
  HandoffDialog,
} from "@/components/brainstorm";
import type { BrainstormArtifact } from "@/types/api";

export default function SpecBuilderPage() {
  const navigate = useNavigate();
  const {
    activeSessionId,
    messages,
    artifacts,
    isStreaming,
    setDrawerOpen,
  } = useBrainstormStore();

  const {
    loadSessions,
    loadSession,
    createSession,
    sendMessage,
    deleteSession,
    handoff,
    startNewSession,
  } = useBrainstormSession();

  const [inputValue, setInputValue] = useState("");
  const [handoffArtifact, setHandoffArtifact] = useState<BrainstormArtifact | null>(null);
  const [isHandingOff, setIsHandingOff] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleSubmit = useCallback(async () => {
    const content = inputValue.trim();
    if (!content || isSubmitting) return;

    setIsSubmitting(true);
    setInputValue("");

    try {
      if (activeSessionId) {
        await sendMessage(content);
      } else {
        // Create new session with first message
        // TODO: Get actual profile ID from settings
        await createSession("default", content);
      }
    } catch (error) {
      setInputValue(content); // Restore on error
      // TODO: Show error toast
    } finally {
      setIsSubmitting(false);
    }
  }, [inputValue, isSubmitting, activeSessionId, sendMessage, createSession]);

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      await loadSession(sessionId);
    },
    [loadSession]
  );

  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      await deleteSession(sessionId);
    },
    [deleteSession]
  );

  const handleHandoffClick = useCallback((artifact: BrainstormArtifact) => {
    setHandoffArtifact(artifact);
  }, []);

  const handleHandoffConfirm = useCallback(
    async (issueTitle: string) => {
      if (!handoffArtifact) return;

      setIsHandingOff(true);
      try {
        const result = await handoff(handoffArtifact.path, issueTitle);
        setHandoffArtifact(null);
        // Navigate to the new workflow
        navigate(`/workflows/${result.workflow_id}`);
      } finally {
        setIsHandingOff(false);
      }
    },
    [handoffArtifact, handoff, navigate]
  );

  const handleHandoffCancel = useCallback(() => {
    setHandoffArtifact(null);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <PageHeader>
        <PageHeader.Left>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open sessions"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <PageHeader.Title>Spec Builder</PageHeader.Title>
        </PageHeader.Left>
        <PageHeader.Right>
          <Button variant="outline" size="sm" onClick={startNewSession}>
            <Plus className="h-4 w-4 mr-2" />
            New Session
          </Button>
        </PageHeader.Right>
      </PageHeader>

      {/* Session Drawer */}
      <SessionDrawer
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onNewSession={startNewSession}
      />

      {/* Conversation Area */}
      <Conversation className="flex-1 overflow-hidden">
        <ConversationContent className="px-4 py-6">
          {messages.length === 0 ? (
            <ConversationEmptyState
              icon={<Lightbulb className="h-12 w-12 text-muted-foreground" />}
              title="Start a brainstorming session"
              description="Type a message below to begin exploring ideas and producing design documents."
            />
          ) : (
            <div className="space-y-4 max-w-3xl mx-auto">
              {messages.map((message) => (
                <Message
                  key={message.id}
                  className={cn(
                    message.role === "user" && "ml-auto max-w-[80%]"
                  )}
                >
                  <MessageContent
                    className={cn(
                      message.role === "user" && "bg-secondary"
                    )}
                  >
                    {message.parts?.some((p) => p.type === "reasoning") && (
                      <Reasoning>
                        <ReasoningTrigger>
                          🧠 Thinking...
                        </ReasoningTrigger>
                        <ReasoningContent>
                          {message.parts
                            ?.filter((p) => p.type === "reasoning")
                            .map((p) => p.text)
                            .join("\n")}
                        </ReasoningContent>
                      </Reasoning>
                    )}
                    <MessageResponse>{message.content}</MessageResponse>
                  </MessageContent>
                </Message>
              ))}

              {/* Inline artifacts */}
              {artifacts.map((artifact) => (
                <ArtifactCard
                  key={artifact.id}
                  artifact={artifact}
                  onHandoff={handleHandoffClick}
                  isHandingOff={isHandingOff && handoffArtifact?.id === artifact.id}
                />
              ))}
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* Input Area */}
      <div className="border-t bg-background p-4">
        <PromptInput className="max-w-3xl mx-auto">
          <PromptInputTextarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="What would you like to design?"
            disabled={isStreaming}
          />
          <PromptInputFooter>
            <PromptInputSubmit
              onClick={handleSubmit}
              disabled={!inputValue.trim()}
              status={isStreaming ? "streaming" : "ready"}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>

      {/* Handoff Dialog */}
      <HandoffDialog
        open={handoffArtifact !== null}
        artifact={handoffArtifact}
        onConfirm={handleHandoffConfirm}
        onCancel={handleHandoffCancel}
        isLoading={isHandingOff}
      />
    </div>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/pages/__tests__/SpecBuilderPage.test.tsx`
Expected: All tests pass (some may need adjustment based on ai-elements mocking)

**Step 5: Commit**

```bash
git add dashboard/src/pages/SpecBuilderPage.tsx dashboard/src/pages/__tests__/SpecBuilderPage.test.tsx
git commit -m "feat(dashboard): add SpecBuilderPage with chat UI"
```

---

## Task 11: Add WebSocket Event Handling

**Files:**
- Modify: `dashboard/src/hooks/useWebSocket.ts`
- Modify: `dashboard/src/hooks/__tests__/useWebSocket.test.ts`

**Step 1: Write failing tests for brainstorm events**

Add to `dashboard/src/hooks/__tests__/useWebSocket.test.ts`:

```typescript
describe("brainstorm events", () => {
  it("appends text to message on brainstorm_text event", () => {
    // ... test code
  });

  it("sets streaming false on brainstorm_message_complete", () => {
    // ... test code
  });

  it("adds artifact on brainstorm_artifact_created", () => {
    // ... test code
  });

  it("ignores events for non-active sessions", () => {
    // Verify session_id validation
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm test:run src/hooks/__tests__/useWebSocket.test.ts`
Expected: FAIL - event types not handled

**Step 3: Add brainstorm event handling**

Add handling for brainstorm events with session ID validation:

```typescript
// In the event handler switch statement, add:
case 'brainstorm_text': {
  const { message_id, text, session_id } = event.data ?? {};
  const state = useBrainstormStore.getState();
  if (session_id === state.activeSessionId && message_id && typeof text === 'string') {
    state.appendMessageContent(message_id, text);
  }
  break;
}

case 'brainstorm_reasoning': {
  // Handle reasoning updates (append to message parts)
  const { session_id } = event.data ?? {};
  const state = useBrainstormStore.getState();
  if (session_id !== state.activeSessionId) break;
  // ... reasoning handling
  break;
}

case 'brainstorm_message_complete': {
  const { session_id } = event.data ?? {};
  const state = useBrainstormStore.getState();
  if (session_id === state.activeSessionId) {
    state.setStreaming(false, null);
  }
  break;
}

case 'brainstorm_artifact_created': {
  const { session_id, artifact } = event.data ?? {};
  const state = useBrainstormStore.getState();
  if (session_id === state.activeSessionId && artifact) {
    state.addArtifact(artifact);
    state.updateSession(session_id, { status: 'ready_for_handoff' });
  }
  break;
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/hooks/__tests__/useWebSocket.test.ts`
Expected: All tests pass

**Step 5: Commit**

```bash
git add dashboard/src/hooks/useWebSocket.ts
git commit -m "feat(dashboard): add brainstorm WebSocket event handling"
```

---

## Task 12: Add Route to Router

**Files:**
- Modify: `dashboard/src/router.tsx`

**Step 1: Add the specs route**

Add a new route for `/specs` (matches existing sidebar link):

```typescript
{
  path: 'specs',
  lazy: async () => {
    const { default: Component } = await import('@/pages/SpecBuilderPage');
    return { Component };
  },
},
```

**Step 2: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add dashboard/src/router.tsx
git commit -m "feat(dashboard): add specs route for SpecBuilderPage"
```

---

## Task 13: Enable Navigation Link

**Files:**
- Modify: `dashboard/src/components/DashboardSidebar.tsx`

**Step 1: Read sidebar component**

Understand the existing navigation structure. Note that there's already a "Spec Builder" link pointing to `/specs` with `comingSoon` prop.

**Step 2: Enable Spec Builder link**

Remove the `comingSoon` prop from the existing Spec Builder navigation item to enable it.

**Step 3: Run existing sidebar tests**

Run: `cd dashboard && pnpm test:run src/components/DashboardSidebar.test.tsx`
Expected: Existing tests pass

**Step 4: Add test for enabled link**

Add test to verify the Spec Builder link is now clickable and navigates to `/specs`.

**Step 5: Commit**

```bash
git add dashboard/src/components/DashboardSidebar.tsx
git commit -m "feat(dashboard): enable Spec Builder sidebar navigation"
```

---

## Task 14: Add ai-elements Theme Customization

**Files:**
- Create: `dashboard/src/styles/ai-elements.css`
- Modify: `dashboard/src/styles/index.css` (or main CSS file)

**Step 1: Create ai-elements theme overrides**

Create CSS that maps ai-elements variables to existing dashboard theme:

```css
/* ai-elements theme overrides */
:root {
  --ai-elements-bg: var(--background);
  --ai-elements-fg: var(--foreground);
  --ai-elements-muted: var(--muted);
  --ai-elements-muted-fg: var(--muted-foreground);
  --ai-elements-accent: var(--accent);
  --ai-elements-accent-fg: var(--accent-foreground);
  --ai-elements-border: var(--border);
  --ai-elements-ring: var(--ring);
}
```

**Step 2: Import in main CSS**

**Step 3: Commit**

```bash
git add dashboard/src/styles/ai-elements.css
git commit -m "style(dashboard): add ai-elements theme customization"
```

---

## Task 15: Run Full Test Suite and Lint

**Files:** None (verification only)

**Step 1: Run all tests**

Run: `cd dashboard && pnpm test:run`
Expected: All tests pass

**Step 2: Run linter**

Run: `cd dashboard && pnpm lint`
Expected: No errors

**Step 3: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 4: Build**

Run: `cd dashboard && pnpm build`
Expected: Build succeeds

---

## Task 16: Manual Testing

**Files:** None

**Step 1: Start the development server**

Run: `uv run amelia dev`

**Step 2: Navigate to Spec Builder**

Go to `http://localhost:8420/spec-builder`

**Step 3: Test empty state**

Verify the empty state displays correctly.

**Step 4: Test session creation**

Type a message and verify:
- Session is created
- Message appears in conversation
- Streaming indicator shows

**Step 5: Test session drawer**

Click hamburger menu and verify:
- Drawer opens
- Sessions are listed
- Can switch between sessions

**Step 6: Test artifact and handoff**

(Requires backend to produce an artifact)
- Verify artifact card appears
- Click "Hand off" and verify dialog
- Confirm handoff navigates to workflow

---

## Summary

This plan implements the Spec Builder UI in 16 tasks:

1. **Types** - TypeScript definitions for brainstorming
2. **API Client** - HTTP client for brainstorm endpoints
3. **Store** - Zustand state management
4. **Hook** - useBrainstormSession for session logic
5-8. **Components** - SessionListItem, SessionDrawer, ArtifactCard, HandoffDialog
9. **Index** - Barrel export
10. **Page** - SpecBuilderPage with full chat UI
11. **WebSocket** - Event handling for streaming
12. **Router** - Route configuration
13. **Sidebar** - Navigation link
14. **Theme** - ai-elements styling
15. **Verification** - Tests, lint, build
16. **Manual Testing** - End-to-end verification

Each task follows TDD with explicit test-first steps and frequent commits.
