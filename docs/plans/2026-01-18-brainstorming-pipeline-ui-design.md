# Brainstorming Pipeline UI Design

**Goal:** Build a chat-based UI for the Spec Builder where users collaborate with an AI agent to produce design documents, then hand off to the implementation pipeline.

**Tech Stack:** React, TypeScript, ai-elements (Vercel), shadcn/ui, Zustand, existing WebSocket infrastructure.

**Aesthetic:** Consistent with dashboard (dark forest green, gold accents, existing component patterns).

---

## Overview

The Spec Builder is a multi-session chat workspace. Users switch between brainstorming sessions via a collapsible drawer. The conversation displays messages with collapsed reasoning blocks. When the agent writes a design document, an artifact card appears inline with a handoff option.

```
┌──────────────────────────────────────────────────────────────────┐
│  [≡] Spec Builder                              [+ New Session]   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│                        Conversation                              │
│                        (scrollable)                              │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ What would you like to design?                    [Send]   │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| User journey | Multi-session workspace | Users switch between brainstorms frequently |
| Session list | Collapsible drawer (left) | Maximizes chat space, easy access when needed |
| Reasoning display | Collapsed by default | Keeps conversation scannable, details on demand |
| Tool calls | Hidden in chat | Available in Logs view; reduces noise |
| New session | First message creates session | No extra clicks, immediate start |
| Handoff trigger | Inline artifact card | Appears naturally in conversation flow |
| Keyboard shortcut | None for v1 | Avoids conflicts with main sidebar |

---

## Page Layout

### Header

```
┌──────────────────────────────────────────────────────────────────┐
│  [≡] Spec Builder                              [+ New Session]   │
└──────────────────────────────────────────────────────────────────┘
```

- Hamburger menu opens session drawer
- "+ New Session" creates session, clears view, focuses input
- Uses existing `PageHeader` pattern

### Empty State

When no active session, show `ConversationEmptyState`:

```
                          💡

                Start a brainstorming session

       Type a message below to begin exploring
       ideas and producing design documents.
```

- Input is always enabled
- Sending first message creates session automatically
- Session topic inferred from first message

---

## Session Drawer

Slides from left edge using shadcn `Sheet`.

```
┌─────────────────────────┐
│  SESSIONS          [×]  │
├─────────────────────────┤
│                         │
│  ACTIVE                 │
│  ┌───────────────────┐  │
│  │ ● Caching design ⋮│  │  ← Selected (highlighted), overflow menu
│  │   2 min ago       │  │
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ ○ API refactor   ⋮│  │
│  │   1 hour ago      │  │
│  └───────────────────┘  │
│                         │
│  COMPLETED              │
│  ┌───────────────────┐  │
│  │ ✓ Auth system    ⋮│  │
│  │   Yesterday       │  │
│  └───────────────────┘  │
│                         │
│  ─────────────────────  │
│  [+ New Session]        │
└─────────────────────────┘
```

**Behavior:**
- Opens via hamburger menu
- Clicking a session loads it and closes drawer
- Sessions grouped: Active, Ready for Handoff, Completed, Failed
- Each item shows: status indicator, topic (or "Untitled"), relative time
- Overflow menu (⋮) on each item reveals delete option (keyboard accessible)

**Components:**
- shadcn `Sheet`, `SheetContent`, `SheetHeader`
- shadcn `DropdownMenu` for overflow menu (Delete action)
- Status indicators use `--status-*` CSS variables

---

## Conversation Area

Uses ai-elements components with existing theme.

```
┌────────────────────────────────────────────────────────────────┐
│ Design a caching layer for the API                          You│  ← User message
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ 🧠 Thinking...                                              ▼  │  ← Reasoning (collapsed)
└────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────┐
│ I'll help you design a caching layer. First, let me           │
│ understand your requirements.                                  │
│                                                                │  ← Assistant message
│ **What's the primary use case?**                              │
│                                                                │
│ 1. Reduce database load                                       │
│ 2. Speed up expensive computations                            │
│ 3. Session/auth token caching                                 │
└────────────────────────────────────────────────────────────────┘
```

**Message styling:**
- User messages: `bg-secondary`, right-aligned via `ml-auto`
- Assistant messages: Left-aligned, full width, markdown via `MessageResponse`
- Reasoning: Collapsed by default, brain icon, expands on click

**Behavior:**
- Auto-scrolls to bottom on new messages
- Scroll button appears when user scrolls up

**Components (ai-elements):**
- `Conversation`, `ConversationContent`, `ConversationScrollButton`
- `Message`, `MessageContent`, `MessageResponse`
- `Reasoning`, `ReasoningTrigger`, `ReasoningContent`

---

## Input Area

Fixed at bottom, always visible.

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│ Type your message...                                           │  ← Auto-expanding
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                        [Send]  │  ← Footer
└────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Textarea auto-expands up to ~6 lines
- Enter submits, Shift+Enter for newline
- Submit button: arrow (ready), spinner (streaming), square (stop)
- Focus ring uses `--ring` (gold)

**Components (ai-elements):**
- `PromptInput`, `PromptInputTextarea`, `PromptInputFooter`, `PromptInputSubmit`

**Note:** No file attachments for v1.

---

## Artifact Card & Handoff

When the agent writes a design document, an artifact card appears inline.

```
┌────────────────────────────────────────────────────────────────┐
│  ✓  Design document created                                    │
│                                                                │
│  📄 docs/plans/2026-01-18-caching-design.md                   │
│                                                                │
│  [View Document]           [Hand off to Implementation →]     │
└────────────────────────────────────────────────────────────────┘
```

**Styling:**
- shadcn `Card` with `border-l-4 border-l-status-completed`
- Success icon, file path in monospace
- Two buttons: secondary (View), primary (Hand off)

### Handoff Dialog

```
┌─────────────────────────────────────────────┐
│  Hand off to Implementation                 │
├─────────────────────────────────────────────┤
│                                             │
│  This will create a new implementation      │
│  workflow from your design document.        │
│                                             │
│  Issue title (optional)                     │
│  ┌───────────────────────────────────────┐  │
│  │ Implement caching layer               │  │
│  └───────────────────────────────────────┘  │
│                                             │
│           [Cancel]  [Create Workflow →]    │
└─────────────────────────────────────────────┘
```

**Components:**
- shadcn `AlertDialog`, `Input`, `Button`

---

## State Management

Zustand store matching existing dashboard patterns.

```typescript
interface BrainstormState {
  // Session management
  sessions: BrainstormingSession[]
  activeSessionId: string | null

  // Current conversation
  messages: Message[]
  artifacts: Artifact[]

  // UI state
  isStreaming: boolean
  drawerOpen: boolean

  // Actions
  createSession: (firstMessage: string) => Promise<void>
  loadSession: (sessionId: string) => Promise<void>
  sendMessage: (content: string) => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>

  // WebSocket event handlers
  handleBrainstormEvent: (event: WorkflowEvent) => void
}
```

### Data Flow

```
User types message
       ↓
sendMessage(content)
       ↓
POST /api/brainstorm/sessions/{id}/message
       ↓
Backend streams via WebSocket (/ws/events)
       ↓
Store receives events → updates messages array
       ↓
React re-renders conversation
```

### WebSocket Integration

- Reuses existing `/ws/events` connection
- Subscribes to `workflow_id=session_id`
- Event types: `brainstorm_text`, `brainstorm_reasoning`, `brainstorm_tool_call`, `brainstorm_tool_result`, `brainstorm_message_complete`, `brainstorm_artifact_created`

---

## API Client

```typescript
// api/brainstorm.ts

createSession(profileId: string, topic?: string): Promise<BrainstormingSession>
// POST /api/brainstorm/sessions

getSession(id: string): Promise<SessionWithHistory>
// GET /api/brainstorm/sessions/{id}

listSessions(filters?: { profileId?: string; status?: string }): Promise<BrainstormingSession[]>
// GET /api/brainstorm/sessions

sendMessage(sessionId: string, content: string): Promise<{ message_id: string }>
// POST /api/brainstorm/sessions/{id}/message

deleteSession(id: string): Promise<void>
// DELETE /api/brainstorm/sessions/{id}

handoff(sessionId: string, artifactPath: string, issue?: { title: string }): Promise<{ workflow_id: string }>
// POST /api/brainstorm/sessions/{id}/handoff
```

---

## File Structure

```
dashboard/src/
├── pages/
│   └── SpecBuilderPage.tsx              # Main page component
│
├── components/
│   └── brainstorm/
│       ├── SessionDrawer.tsx            # Sheet with session list
│       ├── SessionList.tsx              # List of sessions
│       ├── SessionListItem.tsx          # Individual session row
│       ├── ArtifactCard.tsx             # Inline artifact display
│       └── HandoffDialog.tsx            # Handoff confirmation
│
├── hooks/
│   └── useBrainstormSession.ts          # Session loading, message sending
│
├── store/
│   └── brainstormStore.ts               # Zustand store
│
└── api/
    └── brainstorm.ts                    # API client functions
```

---

## Component Mapping

| Component | Source | Notes |
|-----------|--------|-------|
| Chat container | ai-elements `Conversation`, `ConversationContent` | |
| Empty state | ai-elements `ConversationEmptyState` | Custom icon/text |
| Messages | ai-elements `Message`, `MessageContent`, `MessageResponse` | |
| Reasoning | ai-elements `Reasoning`, `ReasoningTrigger`, `ReasoningContent` | Collapsed default |
| Scroll button | ai-elements `ConversationScrollButton` | |
| Input | ai-elements `PromptInput`, `PromptInputTextarea`, `PromptInputFooter`, `PromptInputSubmit` | |
| Session drawer | shadcn `Sheet`, `SheetContent`, `SheetHeader` | |
| Artifact card | shadcn `Card`, `CardHeader`, `CardContent`, `Button` | |
| Handoff dialog | shadcn `AlertDialog`, `Input`, `Button` | |
| Page header | Custom | Reuses `PageHeader` pattern |

---

## Related Documents

- [Brainstorming Pipeline Design](./2026-01-18-brainstorming-pipeline-design.md) - Backend architecture
- [Brainstorming Pipeline Implementation](./2026-01-18-brainstorming-pipeline-implementation.md) - Backend implementation plan
- [ai-elements Documentation](https://ai-elements.dev) - Component library
