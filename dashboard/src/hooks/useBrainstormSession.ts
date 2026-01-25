import { useCallback } from "react";
import { nanoid } from "nanoid";
import { brainstormApi } from "@/api/brainstorm";
import { useBrainstormStore } from "@/store/brainstormStore";
import type { SessionStatus } from "@/types/api";

export function useBrainstormSession() {
  const {
    activeSessionId,
    setSessions,
    addSession,
    removeSession,
    setActiveSessionId,
    setActiveProfile,
    setMessages,
    addMessage,
    removeMessage,
    setArtifacts,
    clearMessages,
    setStreaming,
    setDrawerOpen,
    setSessionUsage,
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
      setActiveProfile(data.profile ?? null);
      setSessionUsage(data.session.usage_summary ?? null);
      setDrawerOpen(false);
    },
    [setActiveSessionId, setMessages, setArtifacts, setActiveProfile, setSessionUsage, setDrawerOpen]
  );

  const createSession = useCallback(
    async (profileId: string, firstMessage: string) => {
      // Create session with first message as topic
      const { session, profile } = await brainstormApi.createSession(profileId, firstMessage);
      addSession(session);
      setActiveSessionId(session.id);
      setActiveProfile(profile ?? null);
      clearMessages();
      setArtifacts([]);
      // Initialize usage to zeros for new sessions
      setSessionUsage({
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_cost_usd: 0,
        message_count: 0,
      });

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

      // Send the user's message directly (no priming needed)
      try {
        setStreaming(true, null);
        const response = await brainstormApi.sendMessage(session.id, firstMessage);

        // Create assistant placeholder with streaming status
        const assistantMessage = {
          id: response.message_id,
          session_id: session.id,
          sequence: 2,
          role: "assistant" as const,
          content: "",
          parts: null,
          created_at: new Date().toISOString(),
          status: "streaming" as const,
        };
        addMessage(assistantMessage);
        setStreaming(true, response.message_id);
      } catch (error) {
        // Rollback optimistic user message
        removeMessage(userMessage.id);
        setStreaming(false, null);
        throw error;
      }
    },
    [addSession, setActiveSessionId, setActiveProfile, clearMessages, setArtifacts, setSessionUsage, addMessage, removeMessage, setStreaming]
  );

  const sendMessage = useCallback(
    async (content: string) => {
      if (!activeSessionId) {
        throw new Error("No active session");
      }

      // Get current message count from store to avoid stale closure
      const currentLength = useBrainstormStore.getState().messages.length;
      const optimisticId = nanoid();
      const userMessage = {
        id: optimisticId,
        session_id: activeSessionId,
        sequence: currentLength + 1,
        role: "user" as const,
        content,
        parts: null,
        created_at: new Date().toISOString(),
      };

      try {
        addMessage(userMessage);
        setStreaming(true, null);
        const response = await brainstormApi.sendMessage(activeSessionId, content);

        // Get updated count after user message was added
        const newLength = useBrainstormStore.getState().messages.length;
        // Create assistant placeholder with streaming status
        const assistantMessage = {
          id: response.message_id,
          session_id: activeSessionId,
          sequence: newLength + 1,
          role: "assistant" as const,
          content: "",
          parts: null,
          created_at: new Date().toISOString(),
          status: "streaming" as const,
        };
        addMessage(assistantMessage);
        setStreaming(true, response.message_id);
      } catch (error) {
        // Rollback optimistic update
        removeMessage(optimisticId);
        setStreaming(false, null);
        throw error;
      }
    },
    [activeSessionId, addMessage, removeMessage, setStreaming]
  );

  const deleteSession = useCallback(
    async (sessionId: string) => {
      await brainstormApi.deleteSession(sessionId);
      removeSession(sessionId);
      if (activeSessionId === sessionId) {
        clearMessages();
        setArtifacts([]);
        setActiveSessionId(null);
        setActiveProfile(null);
        setSessionUsage(null);
        setStreaming(false, null);
      }
    },
    [activeSessionId, removeSession, clearMessages, setArtifacts, setActiveSessionId, setActiveProfile, setSessionUsage, setStreaming]
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
    setActiveProfile(null);
    clearMessages();
    setArtifacts([]);
    setSessionUsage(null);
    setStreaming(false, null);
    setDrawerOpen(false);
  }, [setActiveSessionId, setActiveProfile, clearMessages, setArtifacts, setSessionUsage, setStreaming, setDrawerOpen]);

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
