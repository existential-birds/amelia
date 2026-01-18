# Plan Review: Brainstorming Pipeline UI Implementation

> **To apply fixes:** Open new session, run:
> `Read this file, then apply the suggested fixes to docs/plans/2026-01-18-brainstorming-pipeline-ui-implementation.md`

**Reviewed:** 2026-01-18
**Verdict:** With fixes (1-8)

---

## Plan Review: Spec Builder UI

**Plan:** `docs/plans/2026-01-18-brainstorming-pipeline-ui-implementation.md`
**Tech Stack:** React, TypeScript, Zustand, ai-elements, shadcn/ui, date-fns, react-router-dom, Vitest

### Summary Table

| Criterion | Status | Notes |
|-----------|--------|-------|
| Parallelization | ✅ GOOD | Clean dependency graph, 5-6 concurrent agents possible in Batch 2 |
| TDD Adherence | ⚠️ ISSUES | Task 11 violates TDD (tests after implementation), Task 10/13 weak |
| Type/API Match | ⚠️ ISSUES | ai-elements import path wrong, missing components, status CSS classes wrong |
| Library Practices | ⚠️ ISSUES | ai-elements API mismatches, AlertDialog pattern issue |
| Security/Edge Cases | ⚠️ ISSUES | Missing error handling, no optimistic rollback, race conditions |

### Issues Found

#### Critical (Must Fix Before Execution)

**1. [Task 10] ai-elements Import Path and Missing Components**

- **Issue:** Plan imports from `"ai-elements"` but ai-elements v1.6.3 is a CLI tool that installs components into `@/components/ai-elements/`. The referenced components (`Conversation`, `Message`, `PromptInput`, `Reasoning`, etc.) are NOT installed in the codebase.
- **Why:** Code will fail to compile. Import resolution will fail.
- **Fix:** Either install missing components via CLI or build custom components.
- **Suggested edit for Task 10 Step 3 (before implementation):**

Add a new Step 0 to Task 10:
```markdown
**Step 0: Install ai-elements components**

Run: `cd dashboard && pnpm dlx ai-elements add conversation message prompt-input reasoning`

Then update imports in SpecBuilderPage.tsx to:
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

---

**2. [Task 5] Status CSS Classes Don't Exist**

- **Issue:** Plan uses `bg-status-waiting` and `bg-status-error` but these don't exist in `globals.css`. Available: `status-running`, `status-completed`, `status-pending`, `status-blocked`, `status-failed`, `status-cancelled`.
- **Why:** Styles won't apply, status indicators will be invisible.
- **Fix:** Use existing status class names.
- **Suggested edit for Task 5 Step 3, lines 1222-1227:**

```typescript
const statusStyles: Record<SessionStatus, string> = {
  active: "bg-status-running",
  ready_for_handoff: "bg-status-pending",
  completed: "bg-status-completed",
  failed: "bg-status-failed",
};
```

---

**3. [Task 11] TDD Violation - Tests Written After Implementation**

- **Issue:** Task 11 implements WebSocket handling first (Step 2), then runs existing tests (Step 3), then adds new tests (Step 4). This violates TDD.
- **Why:** Without tests first, implementation may not match expected behavior.
- **Fix:** Restructure task to write tests first.
- **Suggested edit for Task 11:**

```markdown
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
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm test:run src/hooks/__tests__/useWebSocket.test.ts`
Expected: FAIL - event types not handled

**Step 3: Implement event handling**

[existing Step 2 content]

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run src/hooks/__tests__/useWebSocket.test.ts`
Expected: All tests pass
```

---

**4. [Task 4, 10] Missing Error Handling and Optimistic Rollback**

- **Issue:** Hook functions (`loadSessions`, `loadSession`, `sendMessage`, `createSession`) have no try/catch. Optimistic updates are not rolled back on failure. Page handlers (`handleSubmit`, `handleHandoffConfirm`) silently fail.
- **Why:** Users see messages that failed to send. No feedback on errors. Poor UX.
- **Fix:** Add error handling with rollback.
- **Suggested edit for Task 4 Step 3, sendMessage function (lines 978-1001):**

```typescript
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
    } catch (error) {
      // Rollback optimistic update
      removeMessage(optimisticId);
      setStreaming(false, null);
      throw error;
    }
  },
  [activeSessionId, messages.length, addMessage, removeMessage, setStreaming]
);
```

Add `removeMessage` action to store in Task 3.

---

#### Major (Should Fix)

**5. [Task 10] PromptInputSubmit Uses Wrong Props**

- **Issue:** Plan uses `isLoading` prop but ai-elements `PromptInputSubmit` uses `status?: ChatStatus` prop.
- **Why:** Component may not show loading state correctly.
- **Fix:** Use correct prop.
- **Suggested edit for Task 10 Step 3, lines 2322-2325:**

```typescript
<PromptInputSubmit
  onClick={handleSubmit}
  disabled={!inputValue.trim()}
  status={isStreaming ? "streaming" : "ready"}
/>
```

---

**6. [Task 8] AlertDialog onOpenChange Fires on Confirm Too**

- **Issue:** `onOpenChange={(isOpen) => !isOpen && onCancel()}` will call `onCancel()` when dialog closes for ANY reason, including after confirm.
- **Why:** Could trigger unintended cancel behavior after successful confirmation.
- **Fix:** Remove onOpenChange or handle explicitly.
- **Suggested edit for Task 8 Step 3, line 1907:**

```typescript
<AlertDialog open={open}>
```

Remove `onOpenChange` entirely. Dialog closes via explicit `onCancel()` and `handleConfirm()` calls.

---

**7. [Task 12/13] Route Path Mismatch with Existing Sidebar**

- **Issue:** Plan adds route at `/spec-builder` but existing `DashboardSidebar.tsx` already has a link to `/specs` for "Spec Builder".
- **Why:** Navigation won't work - clicking sidebar link goes to `/specs` but page is at `/spec-builder`.
- **Fix:** Use consistent path.
- **Suggested edit for Task 12 Step 1:**

```typescript
{
  path: 'specs',  // Match existing sidebar link
  lazy: async () => {
    const { default: Component } = await import('@/pages/SpecBuilderPage');
    return { Component };
  },
},
```

And update Task 13 to remove `comingSoon` prop from existing link instead of adding new link.

---

**8. [Task 11] WebSocket Events Not Session-Scoped**

- **Issue:** WebSocket event handlers update store without checking if event is for the active session.
- **Why:** Events from old sessions could update the wrong conversation.
- **Fix:** Add session ID validation.
- **Suggested edit for Task 11 Step 3:**

```typescript
case 'brainstorm_text': {
  const { message_id, text, session_id } = event.data ?? {};
  const state = useBrainstormStore.getState();
  if (session_id === state.activeSessionId && message_id && typeof text === 'string') {
    state.appendMessageContent(message_id, text);
  }
  break;
}
```

---

#### Minor (Nice to Have)

**9. [Task 5] Test File Path Typo**

- **Issue:** Step 2 says `.test.ts` but file is `.test.tsx`.
- **Fix:** Change line 1196 from `SessionListItem.test.ts` to `SessionListItem.test.tsx`.

---

**10. [Task 2] Timeout Signal Memory Leak**

- **Issue:** `createTimeoutSignal` uses `setTimeout` that's never cleared if request completes first.
- **Fix:** Use `AbortSignal.timeout()` like existing client.ts.
- **Suggested edit for Task 2 Step 3, lines 267-270:**

```typescript
function createTimeoutSignal(timeoutMs: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}
```

---

**11. [Task 10] Missing isSubmitting State**

- **Issue:** No debounce or duplicate prevention when rapidly pressing Enter.
- **Fix:** Add `isSubmitting` state and check.
- **Suggested edit for Task 10 Step 3, add state and update handleSubmit:**

```typescript
const [isSubmitting, setIsSubmitting] = useState(false);

const handleSubmit = useCallback(async () => {
  const content = inputValue.trim();
  if (!content || isSubmitting) return;

  setIsSubmitting(true);
  setInputValue("");
  try {
    if (activeSessionId) {
      await sendMessage(content);
    } else {
      await createSession("default", content);
    }
  } catch (error) {
    setInputValue(content); // Restore on error
    // TODO: Show error toast
  } finally {
    setIsSubmitting(false);
  }
}, [inputValue, isSubmitting, activeSessionId, sendMessage, createSession]);
```

---

**12. [Task 3] Store Missing removeMessage Action**

- **Issue:** Needed for optimistic rollback but not defined.
- **Fix:** Add to store.
- **Suggested edit for Task 3 Step 3, add to interface and implementation:**

```typescript
// In interface
removeMessage: (messageId: string) => void;

// In implementation
removeMessage: (messageId: string) =>
  set((state) => ({
    messages: state.messages.filter((m) => m.id !== messageId),
  })),
```

---

### Parallelization Analysis

The plan is well-structured for parallel execution:

| Batch | Tasks | Max Concurrent |
|-------|-------|----------------|
| 1 | Task 1 (Types) | 1 |
| 2 | Tasks 2, 3, 5, 7, 8, 14 | 5-6 |
| 3 | Tasks 4, 6 | 2 |
| 4 | Task 9 (Barrel) | 1 |
| 5 | Task 10 (Page) | 1 |
| 6 | Tasks 11, 12, 13 | 3 |
| 7 | Task 15 (Verify) | 1 |
| 8 | Task 16 (Manual) | 1 |

Critical path is ~8 sequential steps with good parallelization in Batches 2 and 6.

---

### Verdict

**Ready to execute?** With fixes (1-8)

**Reasoning:** The plan has solid TDD structure for most tasks and clean parallelization. However, the ai-elements import issue (Critical #1) will cause immediate compilation failure. The missing error handling (Critical #4) will result in poor UX. These 8 issues should be addressed before execution. Minor issues (9-12) can be fixed during implementation.

---

## Next Steps

**Review saved to:** `docs/plans/2026-01-18-brainstorming-pipeline-ui-implementation-review.md`

**Options:**

1. **Apply fixes now** - Edit the plan file to address issues
2. **Save & fix later** - Open new session to apply fixes
3. **Proceed anyway** - Execute plan despite issues (not recommended for Critical)

Which option?
