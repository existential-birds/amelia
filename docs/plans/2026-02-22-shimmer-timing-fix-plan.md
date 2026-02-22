# Shimmer Timing Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the spec builder's thinking shimmer so it appears immediately when the user sends a message, and only on the latest assistant message.

**Architecture:** Add optimistic assistant placeholder before the HTTP call using a temp ID. Add two store actions (`replaceMessageId`, `clearStaleStreaming`) to support the pattern. Wire up `handleWebSocketDisconnect` on close.

**Tech Stack:** TypeScript, Zustand, React, Vitest

---

### Task 1: Add `replaceMessageId` store action

**Files:**
- Modify: `dashboard/src/store/brainstormStore.ts`
- Test: `dashboard/src/store/__tests__/brainstormStore.test.ts`

**Step 1: Write the failing test**

Add to the "message management" describe block in `brainstormStore.test.ts`:

```typescript
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
```

**Step 2: Run test to verify it fails**

Run: `pnpm --filter dashboard test:run -- --reporter=verbose dashboard/src/store/__tests__/brainstormStore.test.ts`
Expected: FAIL — `replaceMessageId` is not a function

**Step 3: Write the implementation**

In `brainstormStore.ts`, add to the `BrainstormState` interface:

```typescript
replaceMessageId: (oldId: string, newId: string) => void;
```

Add to the store implementation:

```typescript
replaceMessageId: (oldId, newId) =>
  set((state) => ({
    messages: state.messages.map((m) =>
      m.id === oldId ? { ...m, id: newId } : m
    ),
    streamingMessageId:
      state.streamingMessageId === oldId ? newId : state.streamingMessageId,
  })),
```

**Step 4: Run test to verify it passes**

Run: `pnpm --filter dashboard test:run -- --reporter=verbose dashboard/src/store/__tests__/brainstormStore.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/store/brainstormStore.ts dashboard/src/store/__tests__/brainstormStore.test.ts
git commit -m "feat(store): add replaceMessageId action for optimistic placeholders"
```

---

### Task 2: Add `clearStaleStreaming` store action

**Files:**
- Modify: `dashboard/src/store/brainstormStore.ts`
- Test: `dashboard/src/store/__tests__/brainstormStore.test.ts`

**Step 1: Write the failing test**

Add to a new "stale streaming cleanup" describe block:

```typescript
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
```

**Step 2: Run test to verify it fails**

Run: `pnpm --filter dashboard test:run -- --reporter=verbose dashboard/src/store/__tests__/brainstormStore.test.ts`
Expected: FAIL — `clearStaleStreaming` is not a function

**Step 3: Write the implementation**

In `brainstormStore.ts`, add to the `BrainstormState` interface:

```typescript
clearStaleStreaming: () => void;
```

Add to the store implementation:

```typescript
clearStaleStreaming: () =>
  set((state) => ({
    messages: state.messages.map((m) =>
      m.status === "streaming" ? { ...m, status: undefined } : m
    ),
  })),
```

**Step 4: Run test to verify it passes**

Run: `pnpm --filter dashboard test:run -- --reporter=verbose dashboard/src/store/__tests__/brainstormStore.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/store/brainstormStore.ts dashboard/src/store/__tests__/brainstormStore.test.ts
git commit -m "feat(store): add clearStaleStreaming action"
```

---

### Task 3: Move assistant placeholder before HTTP call in `createSession`

**Files:**
- Modify: `dashboard/src/hooks/useBrainstormSession.ts`

**Step 1: Update the `createSession` callback**

Replace the try block (lines 76-98) with:

```typescript
// Add optimistic assistant placeholder BEFORE HTTP call
const tempAssistantId = nanoid();
try {
  clearStaleStreaming();
  const assistantMessage = {
    id: tempAssistantId,
    session_id: session.id,
    sequence: 2,
    role: "assistant" as const,
    content: "",
    parts: null,
    created_at: new Date().toISOString(),
    status: "streaming" as const,
  };
  addMessage(assistantMessage);
  setStreaming(true, tempAssistantId);

  const response = await brainstormApi.sendMessage(session.id, firstMessage);
  replaceMessageId(tempAssistantId, response.message_id);
  setStreaming(true, response.message_id);
} catch (error) {
  // Rollback optimistic messages
  removeMessage(tempAssistantId);
  removeMessage(userMessage.id);
  setStreaming(false, null);
  throw error;
}
```

Also add `clearStaleStreaming` and `replaceMessageId` to the destructured store actions at the top of the hook, and to the `useCallback` dependency array.

**Step 2: Run tests to verify nothing broke**

Run: `pnpm --filter dashboard test:run -- --reporter=verbose`
Expected: PASS

**Step 3: Commit**

```bash
git add dashboard/src/hooks/useBrainstormSession.ts
git commit -m "fix(brainstorm): show shimmer immediately in createSession"
```

---

### Task 4: Move assistant placeholder before HTTP call in `sendMessage`

**Files:**
- Modify: `dashboard/src/hooks/useBrainstormSession.ts`

**Step 1: Update the `sendMessage` callback**

Replace the try block (lines 122-147) with:

```typescript
const tempAssistantId = nanoid();
try {
  addMessage(userMessage);
  clearStaleStreaming();

  // Get updated count after user message was added
  const newLength = useBrainstormStore.getState().messages.length;
  const assistantMessage = {
    id: tempAssistantId,
    session_id: activeSessionId,
    sequence: newLength + 1,
    role: "assistant" as const,
    content: "",
    parts: null,
    created_at: new Date().toISOString(),
    status: "streaming" as const,
  };
  addMessage(assistantMessage);
  setStreaming(true, tempAssistantId);

  const response = await brainstormApi.sendMessage(activeSessionId, content);
  replaceMessageId(tempAssistantId, response.message_id);
  setStreaming(true, response.message_id);
} catch (error) {
  // Rollback optimistic messages
  removeMessage(tempAssistantId);
  removeMessage(optimisticId);
  setStreaming(false, null);
  throw error;
}
```

**Step 2: Run tests to verify nothing broke**

Run: `pnpm --filter dashboard test:run -- --reporter=verbose`
Expected: PASS

**Step 3: Commit**

```bash
git add dashboard/src/hooks/useBrainstormSession.ts
git commit -m "fix(brainstorm): show shimmer immediately in sendMessage"
```

---

### Task 5: Wire up `handleWebSocketDisconnect` on close

**Files:**
- Modify: `dashboard/src/hooks/useWebSocket.ts`

**Step 1: Add the disconnect call**

In the `ws.onclose` handler (around line 317-326), add `handleWebSocketDisconnect` before `scheduleReconnect`:

```typescript
ws.onclose = (event) => {
  console.log('WebSocket disconnected', event.code, event.reason);
  setConnected(false);
  wsRef.current = null;

  // Mark any streaming messages as errored
  useBrainstormStore.getState().handleWebSocketDisconnect();

  // Reconnect unless it was a normal closure
  if (event.code !== 1000) {
    scheduleReconnect();
  }
};
```

Make sure `useBrainstormStore` is imported at the top of the file (check if it already is — the `handleBrainstormMessage` function at line 47 already uses `useBrainstormStore.getState()`).

**Step 2: Run full test suite**

Run: `pnpm --filter dashboard test:run -- --reporter=verbose`
Expected: PASS

**Step 3: Commit**

```bash
git add dashboard/src/hooks/useWebSocket.ts
git commit -m "fix(websocket): mark streaming messages as errored on disconnect"
```

---

### Task 6: Manual verification

**Step 1: Start the dev server**

Run: `uv run amelia dev`

**Step 2: Verify shimmer appears immediately**

1. Open http://localhost:8421, navigate to spec builder
2. Select a profile and type a message
3. Verify the "Thinking..." shimmer appears immediately after pressing enter (before the HTTP response)
4. Verify the shimmer transitions to streaming content when text arrives

**Step 3: Verify stale shimmer is cleaned up**

1. Send a second message in the same session
2. Verify only the latest assistant message shows the shimmer
3. Previous assistant messages should have no shimmer

**Step 4: Run full dashboard test suite one final time**

Run: `pnpm --filter dashboard test:run -- --reporter=verbose`
Expected: ALL PASS
