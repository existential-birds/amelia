import { describe, it, expect, beforeEach } from "vitest";
import { useBrainstormStore } from "../brainstormStore";
import type {
  BrainstormArtifact,
  BrainstormingSession,
  BrainstormMessage,
} from "@/types/api";

describe("useBrainstormStore", () => {
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

    it("sets active profile", () => {
      const profile = {
        name: "test-profile",
        driver: "claude",
        model: "sonnet",
      };
      useBrainstormStore.getState().setActiveProfile(profile);

      expect(useBrainstormStore.getState().activeProfile).toEqual(profile);
    });

    it("clears active profile", () => {
      useBrainstormStore.getState().setActiveProfile({
        name: "p1",
        driver: "api",
        model: "gpt-4",
      });
      useBrainstormStore.getState().setActiveProfile(null);

      expect(useBrainstormStore.getState().activeProfile).toBeNull();
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

      expect(useBrainstormStore.getState().messages[0]!.content).toBe(
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

      expect(useBrainstormStore.getState().messages[0]!.content).toBe(
        "Hello world"
      );
    });

    it("replaces a message ID", () => {
      const message: BrainstormMessage = {
        id: "temp-1",
        session_id: "s1",
        sequence: 1,
        role: "assistant",
        content: "",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
        status: "streaming",
      };
      useBrainstormStore.getState().addMessage(message);

      useBrainstormStore.getState().replaceMessageId("temp-1", "real-uuid");

      const messages = useBrainstormStore.getState().messages;
      expect(messages).toHaveLength(1);
      expect(messages[0]!.id).toBe("real-uuid");
      expect(messages[0]!.content).toBe("");
      expect(messages[0]!.status).toBe("streaming");
    });

    it("also updates streamingMessageId when replacing message ID", () => {
      const message: BrainstormMessage = {
        id: "temp-1",
        session_id: "s1",
        sequence: 1,
        role: "assistant",
        content: "",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
        status: "streaming",
      };
      useBrainstormStore.getState().addMessage(message);
      useBrainstormStore.getState().setStreaming(true, "temp-1");

      useBrainstormStore.getState().replaceMessageId("temp-1", "real-uuid");

      expect(useBrainstormStore.getState().streamingMessageId).toBe("real-uuid");
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

  describe("updateMessage", () => {
    it("updates a message using updater function", () => {
      const message: BrainstormMessage = {
        id: "msg-1",
        session_id: "session-1",
        sequence: 1,
        role: "assistant",
        content: "Hello",
        parts: null,
        created_at: new Date().toISOString(),
        status: "streaming",
      };

      useBrainstormStore.getState().addMessage(message);

      useBrainstormStore.getState().updateMessage("msg-1", (m) => ({
        ...m,
        content: m.content + " world",
        status: undefined,
      }));

      const updated = useBrainstormStore.getState().messages[0];
      expect(updated!.content).toBe("Hello world");
      expect(updated!.status).toBeUndefined();
    });

    it("does nothing if message not found", () => {
      useBrainstormStore.getState().updateMessage("nonexistent", (m) => ({
        ...m,
        content: "changed",
      }));

      expect(useBrainstormStore.getState().messages).toHaveLength(0);
    });

    it("preserves other messages when updating one", () => {
      const message1: BrainstormMessage = {
        id: "msg-1",
        session_id: "session-1",
        sequence: 1,
        role: "user",
        content: "User message",
        parts: null,
        created_at: new Date().toISOString(),
      };
      const message2: BrainstormMessage = {
        id: "msg-2",
        session_id: "session-1",
        sequence: 2,
        role: "assistant",
        content: "Assistant message",
        parts: null,
        created_at: new Date().toISOString(),
        status: "streaming",
      };

      useBrainstormStore.getState().addMessage(message1);
      useBrainstormStore.getState().addMessage(message2);

      useBrainstormStore.getState().updateMessage("msg-2", (m) => ({
        ...m,
        content: "Updated assistant",
        status: undefined,
      }));

      const messages = useBrainstormStore.getState().messages;
      expect(messages).toHaveLength(2);
      expect(messages[0]!.content).toBe("User message");
      expect(messages[1]!.content).toBe("Updated assistant");
      expect(messages[1]!.status).toBeUndefined();
    });
  });

  describe("artifact management", () => {
    const makeArtifact = (
      id: string,
      overrides?: Partial<BrainstormArtifact>,
    ): BrainstormArtifact => ({
      id,
      session_id: "s1",
      type: "spec",
      path: `/specs/${id}.md`,
      title: `Artifact ${id}`,
      created_at: "2026-01-18T00:00:00Z",
      ...overrides,
    });

    it("adds an artifact", () => {
      useBrainstormStore.getState().addArtifact(makeArtifact("a1"));

      expect(useBrainstormStore.getState().artifacts).toHaveLength(1);
      expect(useBrainstormStore.getState().artifacts[0]!.id).toBe("a1");
    });

    it("deduplicates artifacts by id", () => {
      const artifact = makeArtifact("a1");

      useBrainstormStore.getState().addArtifact(artifact);
      useBrainstormStore.getState().addArtifact(artifact);

      expect(useBrainstormStore.getState().artifacts).toHaveLength(1);
    });

    it("deduplicates artifacts with null title", () => {
      const artifact = makeArtifact("a1", { title: null });

      useBrainstormStore.getState().addArtifact(artifact);
      useBrainstormStore.getState().addArtifact(artifact);

      expect(useBrainstormStore.getState().artifacts).toHaveLength(1);
      expect(useBrainstormStore.getState().artifacts[0]!.title).toBeNull();
    });

    it("allows distinct artifacts", () => {
      useBrainstormStore.getState().addArtifact(makeArtifact("a1"));
      useBrainstormStore.getState().addArtifact(makeArtifact("a2"));

      expect(useBrainstormStore.getState().artifacts).toHaveLength(2);
    });
  });

  describe("handleWebSocketDisconnect", () => {
    it("marks streaming message as error and resets streaming state", () => {
      const message: BrainstormMessage = {
        id: "m1",
        session_id: "s1",
        sequence: 1,
        role: "assistant",
        content: "Partial response",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
        status: "streaming",
      };
      useBrainstormStore.getState().addMessage(message);
      useBrainstormStore.getState().setStreaming(true, "m1");

      useBrainstormStore.getState().handleWebSocketDisconnect();

      const state = useBrainstormStore.getState();
      expect(state.messages[0]!.status).toBe("error");
      expect(state.messages[0]!.errorMessage).toBe(
        "Connection lost. Please retry."
      );
      expect(state.isStreaming).toBe(false);
      expect(state.streamingMessageId).toBeNull();
    });

    it("does nothing when streamingMessageId is null", () => {
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

      useBrainstormStore.getState().handleWebSocketDisconnect();

      const state = useBrainstormStore.getState();
      expect(state.messages).toHaveLength(1);
      expect(state.messages[0]!.status).toBeUndefined();
      expect(state.isStreaming).toBe(false);
      expect(state.streamingMessageId).toBeNull();
    });

    it("only affects the streaming message, not other messages", () => {
      const userMsg: BrainstormMessage = {
        id: "m1",
        session_id: "s1",
        sequence: 1,
        role: "user",
        content: "Hello",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
      };
      const streamingMsg: BrainstormMessage = {
        id: "m2",
        session_id: "s1",
        sequence: 2,
        role: "assistant",
        content: "Partial",
        parts: null,
        created_at: "2026-01-18T00:00:01Z",
        status: "streaming",
      };
      const completedMsg: BrainstormMessage = {
        id: "m3",
        session_id: "s1",
        sequence: 3,
        role: "assistant",
        content: "Done earlier",
        parts: null,
        created_at: "2026-01-18T00:00:02Z",
      };
      useBrainstormStore.getState().addMessage(userMsg);
      useBrainstormStore.getState().addMessage(streamingMsg);
      useBrainstormStore.getState().addMessage(completedMsg);
      useBrainstormStore.getState().setStreaming(true, "m2");

      useBrainstormStore.getState().handleWebSocketDisconnect();

      const messages = useBrainstormStore.getState().messages;
      expect(messages).toHaveLength(3);
      // User message unchanged
      expect(messages[0]!.content).toBe("Hello");
      expect(messages[0]!.status).toBeUndefined();
      // Streaming message got error
      expect(messages[1]!.status).toBe("error");
      expect(messages[1]!.errorMessage).toBe("Connection lost. Please retry.");
      // Completed message unchanged
      expect(messages[2]!.content).toBe("Done earlier");
      expect(messages[2]!.status).toBeUndefined();
    });
  });

  describe("stale streaming cleanup", () => {
    it("clears streaming status from all messages", () => {
      useBrainstormStore.getState().addMessage({
        id: "m1",
        session_id: "s1",
        sequence: 1,
        role: "assistant",
        content: "Old response",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
        status: "streaming",
      });
      useBrainstormStore.getState().addMessage({
        id: "m2",
        session_id: "s1",
        sequence: 2,
        role: "user",
        content: "Next question",
        parts: null,
        created_at: "2026-01-18T00:00:01Z",
      });

      useBrainstormStore.getState().clearStaleStreaming();

      const messages = useBrainstormStore.getState().messages;
      expect(messages[0]!.status).toBeUndefined();
      expect(messages[1]!.status).toBeUndefined();
    });

    it("does not affect error status", () => {
      useBrainstormStore.getState().addMessage({
        id: "m1",
        session_id: "s1",
        sequence: 1,
        role: "assistant",
        content: "",
        parts: null,
        created_at: "2026-01-18T00:00:00Z",
        status: "error",
        errorMessage: "Something broke",
      });

      useBrainstormStore.getState().clearStaleStreaming();

      expect(useBrainstormStore.getState().messages[0]!.status).toBe("error");
    });
  });
});
