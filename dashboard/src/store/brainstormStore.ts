import { create } from "zustand";
import type {
  BrainstormingSession,
  BrainstormMessage,
  BrainstormArtifact,
  ProfileInfo,
  SessionUsageSummary,
} from "@/types/api";

interface BrainstormState {
  sessions: BrainstormingSession[];
  activeSessionId: string | null;
  activeProfile: ProfileInfo | null;
  sessionUsage: SessionUsageSummary | null;

  messages: BrainstormMessage[];
  artifacts: BrainstormArtifact[];

  isStreaming: boolean;
  streamingMessageId: string | null;
  drawerOpen: boolean;

  setSessions: (sessions: BrainstormingSession[]) => void;
  addSession: (session: BrainstormingSession) => void;
  updateSession: (
    sessionId: string,
    updates: Partial<BrainstormingSession>
  ) => void;
  removeSession: (sessionId: string) => void;
  setActiveSessionId: (sessionId: string | null) => void;
  setActiveProfile: (profile: ProfileInfo | null) => void;
  setSessionUsage: (usage: SessionUsageSummary | null) => void;

  setMessages: (messages: BrainstormMessage[]) => void;
  addMessage: (message: BrainstormMessage) => void;
  removeMessage: (messageId: string) => void;
  updateMessage: (
    messageId: string,
    updater: (message: BrainstormMessage) => BrainstormMessage
  ) => void;
  updateMessageContent: (messageId: string, content: string) => void;
  appendMessageContent: (messageId: string, content: string) => void;
  replaceMessageId: (oldId: string, newId: string) => void;
  clearStaleStreaming: () => void;
  clearMessages: () => void;

  setArtifacts: (artifacts: BrainstormArtifact[]) => void;
  addArtifact: (artifact: BrainstormArtifact) => void;

  setStreaming: (streaming: boolean, messageId: string | null) => void;
  setDrawerOpen: (open: boolean) => void;

  handleWebSocketDisconnect: () => void;
}

export const useBrainstormStore = create<BrainstormState>()((set) => ({
  sessions: [],
  activeSessionId: null,
  activeProfile: null,
  sessionUsage: null,
  messages: [],
  artifacts: [],
  isStreaming: false,
  streamingMessageId: null,
  drawerOpen: false,

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

  setActiveProfile: (profile) => set({ activeProfile: profile }),

  setSessionUsage: (usage) => set({ sessionUsage: usage }),

  setMessages: (messages) => set({ messages }),

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  removeMessage: (messageId) =>
    set((state) => ({
      messages: state.messages.filter((m) => m.id !== messageId),
    })),

  updateMessage: (messageId, updater) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId ? updater(m) : m
      ),
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

  replaceMessageId: (oldId, newId) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === oldId ? { ...m, id: newId } : m
      ),
      streamingMessageId:
        state.streamingMessageId === oldId ? newId : state.streamingMessageId,
    })),

  clearStaleStreaming: () =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.status === "streaming" ? { ...m, status: undefined } : m
      ),
    })),

  clearMessages: () => set({ messages: [], artifacts: [] }),

  setArtifacts: (artifacts) => set({ artifacts }),

  addArtifact: (artifact) =>
    set((state) => ({
      artifacts: state.artifacts.some((a) => a.id === artifact.id)
        ? state.artifacts
        : [...state.artifacts, artifact],
    })),

  setStreaming: (streaming, messageId) =>
    set({ isStreaming: streaming, streamingMessageId: messageId }),

  setDrawerOpen: (open) => set({ drawerOpen: open }),

  handleWebSocketDisconnect: () =>
    set((state) => {
      if (!state.streamingMessageId) {
        return state;
      }
      return {
        messages: state.messages.map((m) =>
          m.id === state.streamingMessageId
            ? {
                ...m,
                status: "error" as const,
                errorMessage: "Connection lost. Please retry.",
              }
            : m
        ),
        isStreaming: false,
        streamingMessageId: null,
      };
    }),
}));
