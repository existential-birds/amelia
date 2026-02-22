# Shimmer Timing Fix Design

**Date:** 2026-02-22
**Branch:** feat/codex-driver

## Problem

Three related bugs in the spec builder's thinking shimmer:

1. **No shimmer during HTTP wait** — The assistant placeholder message is added to the store *after* `await brainstormApi.sendMessage()` returns. During the HTTP round-trip, `isStreaming` is `true` but no assistant message exists, so the shimmer condition can't match. Users see nothing happening.

2. **Stale shimmer on old messages** — Previous assistant messages can retain `status: "streaming"` if `message_complete` was missed (e.g. disconnect). All such messages show the shimmer, not just the latest.

3. **WebSocket disconnect doesn't mark messages as errored** — `handleWebSocketDisconnect()` exists in the store but is never called from `useWebSocket.ts`.

## Approach: Optimistic Placeholder with Temp ID

Add the assistant placeholder to the store **before** the HTTP call using a temporary `nanoid()`. Replace the temp ID with the server's real `message_id` when the response arrives.

### Store Changes (`brainstormStore.ts`)

Add two new actions:

- `replaceMessageId(oldId, newId)` — Swap a message's ID (for replacing temp ID with server ID).
- `clearStaleStreaming()` — Set `status: undefined` on any messages that still have `status: "streaming"`. Called before adding a new streaming placeholder.

### Hook Changes (`useBrainstormSession.ts`)

Both `createSession` and `sendMessage` follow this sequence:

```
1. addMessage(userMessage)
2. clearStaleStreaming()
3. tempId = nanoid()
4. addMessage(assistantPlaceholder with tempId, status: "streaming")
5. setStreaming(true, tempId)
6. response = await brainstormApi.sendMessage(...)
7. replaceMessageId(tempId, response.message_id)
8. setStreaming(true, response.message_id)
```

On error: remove both the temp assistant message and optimistic user message, clear streaming.

### WebSocket Changes (`useWebSocket.ts`)

In the `onclose` handler, call `useBrainstormStore.getState().handleWebSocketDisconnect()` before scheduling reconnect.

### Rendering (no changes needed)

The existing shimmer condition in `SpecBuilderPage.tsx` already works correctly:

```tsx
const isStreamingEmpty =
  message.role === "assistant" &&
  message.status === "streaming" &&
  !message.content &&
  !message.reasoning;
```

With the placeholder added before the HTTP call, this condition is satisfied immediately.

## Files Changed

1. `dashboard/src/store/brainstormStore.ts` — Add `replaceMessageId`, `clearStaleStreaming`
2. `dashboard/src/hooks/useBrainstormSession.ts` — Reorder placeholder creation before HTTP call
3. `dashboard/src/hooks/useWebSocket.ts` — Call `handleWebSocketDisconnect` on close

## Edge Cases

- **WebSocket events arrive before HTTP response:** Unlikely since the backend returns 202 before spawning the background task. If it happened, `updateMessage` would be a no-op (no message with that ID yet). After `replaceMessageId`, subsequent events would match. First few tokens could be lost — acceptable given the extreme rarity.
- **HTTP call fails:** Rollback removes both optimistic messages and clears streaming. Clean state.
- **Rapid successive messages:** `clearStaleStreaming()` ensures only the latest placeholder shows the shimmer.
