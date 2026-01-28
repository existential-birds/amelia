import { create } from "zustand";
import type {
  BrainstormingSession,
  BrainstormMessage,
  BrainstormArtifact,
  ProfileInfo,
  SessionUsageSummary,
} from "@/types/api";

interface BrainstormState {
  // Session management
  sessions: BrainstormingSession[];
  activeSessionId: string | null;
  activeProfile: ProfileInfo | null;
  sessionUsage: SessionUsageSummary | null;

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
  setActiveProfile: (profile: ProfileInfo | null) => void;
  setSessionUsage: (usage: SessionUsageSummary | null) => void;

  // Message actions
  setMessages: (messages: BrainstormMessage[]) => void;
  addMessage: (message: BrainstormMessage) => void;
  removeMessage: (messageId: string) => void;
  updateMessage: (
    messageId: string,
    updater: (message: BrainstormMessage) => BrainstormMessage
  ) => void;
  updateMessageContent: (messageId: string, content: string) => void;
  appendMessageContent: (messageId: string, content: string) => void;
  clearMessages: () => void;

  // Artifact actions
  setArtifacts: (artifacts: BrainstormArtifact[]) => void;
  addArtifact: (artifact: BrainstormArtifact) => void;

  // UI actions
  setStreaming: (streaming: boolean, messageId: string | null) => void;
  setDrawerOpen: (open: boolean) => void;

  // WebSocket actions
  handleWebSocketDisconnect: () => void;
}

export const useBrainstormStore = create<BrainstormState>()((set) => ({
  // Initial state
  sessions: [],
  activeSessionId: null,
  activeProfile: null,
  sessionUsage: null,
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

  setActiveProfile: (profile) => set({ activeProfile: profile }),

  setSessionUsage: (usage) => set({ sessionUsage: usage }),

  // Message actions
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

  clearMessages: () => set({ messages: [], artifacts: [] }),

  // Artifact actions
  setArtifacts: (artifacts) => set({ artifacts }),

  addArtifact: (artifact) =>
    set((state) => ({
      artifacts: state.artifacts.some((a) => a.id === artifact.id)
        ? state.artifacts
        : [...state.artifacts, artifact],
    })),

  // UI actions
  setStreaming: (streaming, messageId) =>
    set({ isStreaming: streaming, streamingMessageId: messageId }),

  setDrawerOpen: (open) => set({ drawerOpen: open }),

  // WebSocket actions
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
