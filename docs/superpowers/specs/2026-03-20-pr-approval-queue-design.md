# PR Auto-Fix Approval Queue

Design spec for a confirmation gate that lets users review and approve PR fix cycles before execution.

## Problem

The PR auto-fix system is fully autonomous — the poller discovers labeled PRs, detects unresolved comments, and fires fix cycles without human input. Users see results after the fact (metrics, workflow detail, comment resolution status) but have no point where they can review what's about to happen and say "go" or "not yet."

## Solution

A confirmation layer between PR discovery and fix execution. When the poller detects unresolved comments, instead of dispatching a fix cycle immediately, it routes through a confirmation gate based on the profile's oversight mode. A new dedicated Approvals page in the dashboard surfaces the queue.

## Architecture

```
                                ┌─────────────┐
GitHub PR ──> Poller ──> Gate ──┤  autonomous  ├──> Execute immediately
                           │    └─────────────┘
                           │    ┌─────────────┐
                           ├────┤  supervised  ├──> Queue + auto-approve after timeout
                           │    └─────────────┘
                           │    ┌─────────────┐
                           └────┤   manual     ├──> Queue + block until human approves
                                └─────────────┘
```

### Oversight Modes (per-profile)

| Mode | Behavior | Use case |
|------|----------|----------|
| `autonomous` | Current behavior. No confirmation. | Personal repos, trusted reviewers |
| `supervised` | Queues for approval. Auto-approves after configurable timeout. | Team repos where you want visibility but don't want to block |
| `manual` | Queues for approval. Blocks indefinitely. | Production repos, compliance-sensitive |

## Backend

### PendingApproval Model

```python
class PendingApproval(BaseModel):
    id: UUID
    profile_id: str
    repo: str
    pr_number: int
    pr_title: str
    head_branch: str
    author: str
    oversight_mode: Literal["manual", "supervised"]
    timeout_seconds: int | None          # supervised only
    created_at: datetime
    expires_at: datetime | None          # supervised only
    status: Literal["pending", "approved", "dismissed"]
    comments: list[ClassifiedComment]    # pre-classified at queue time
    excluded_comment_ids: list[int]      # user toggled off
```

```python
class ClassifiedComment(BaseModel):
    comment_id: int
    body: str
    author: str
    path: str | None
    line: int | None
    category: CommentCategory            # reuses existing enum: bug, security, style, suggestion, question, praise
    confidence: float
    actionable: bool                     # question/praise are always non-actionable
    included: bool                       # default: actionable (so question/praise default to excluded)
    html_url: str
```

Note: Reuses the existing `CommentCategory` enum from `amelia/agents/schemas/classifier.py` (bug, security, style, suggestion, question, praise). Non-actionable categories (question, praise) default to `included=False` and appear in the EXCLUDED section. Security comments are always actionable.

### ConfirmationService

```python
class ConfirmationService:
    def __init__(self, orchestrator, event_bus, classify_fn):
        self._pending: dict[tuple[str, str, int], PendingApproval] = {}  # (profile_id, repo, pr_number)
        self._timers: dict[UUID, asyncio.TimerHandle] = {}
        self._dismiss_deadlines: dict[UUID, float] = {}  # monotonic deadline for undo window
        self._orchestrator = orchestrator
        self._event_bus = event_bus
        self._classify_fn = classify_fn  # reuses pipeline's classify node

    async def submit(profile, pr, comments):
        # autonomous -> orchestrator.trigger_fix_cycle() immediately
        # manual/supervised -> spawn background task to classify, then create PendingApproval
        #   frontend sees a "classifying..." state until classification completes
        # supervised -> schedule auto-approve timer via asyncio.call_later

    async def approve(approval_id, excluded_comment_ids):
        # update status -> approved
        # cancel auto-approve timer if any
        # trigger_fix_cycle() with filtered comments (excluding excluded_comment_ids)
        # emit PR_FIX_APPROVED event

    async def dismiss(approval_id):
        # update status -> dismissed
        # cancel auto-approve timer
        # record dismiss deadline: monotonic() + 10.0 in _dismiss_deadlines
        # do NOT remove from _pending yet (undo needs it)
        # emit PR_FIX_DISMISSED event
        # schedule cleanup task at 10s to remove from _pending and update poller

    async def undismiss(approval_id):
        # check _dismiss_deadlines[approval_id] > monotonic(), else raise 404
        # update status -> pending
        # cancel cleanup task
        # restart auto-approve timer if supervised

    async def list_pending() -> list[PendingApproval]: ...

    async def auto_approve(approval_id):
        # called by timer, same as approve() with no exclusions
        # sets approved_by="auto_timeout" in the PR_FIX_APPROVED event payload

    def notify_dismissed_comments(self, poller, profile_name, pr_number, comment_ids):
        # called by cleanup task after undo window expires
        # injects comment_ids into poller._processed_comments so they won't be re-queued
```

### Poller Integration

The poller's `_poll_profile()` method currently calls `self._orchestrator.trigger_fix_cycle()` directly (line ~209 of `pr_poller.py`). This changes to call `self._confirmation_service.submit()` instead. The `ConfirmationService` is injected into the poller at initialization (same pattern as the orchestrator injection).

The poller's `_processed_comments` tracking is unchanged for autonomous mode. For supervised/manual mode, comments are marked as processed when `submit()` is called (same as today — they entered the system). On dismiss after the undo window, `notify_dismissed_comments()` ensures they stay in `_processed_comments` so the poller doesn't re-queue them. Only genuinely new comments (new GitHub comment IDs) trigger a new PendingApproval.

### Storage

In-memory `dict` keyed by `(repo, pr_number)`. Pending approvals are ephemeral — server restart loses them, next poll cycle recreates them. On recreation after restart, supervised timers compute remaining time from `expires_at - now` rather than restarting from zero.

### API Endpoints

```
GET    /api/approvals              -> list pending approvals
POST   /api/approvals/:id/approve  -> approve with optional excluded_comment_ids
POST   /api/approvals/:id/dismiss  -> dismiss (starts undo window)
POST   /api/approvals/:id/undo     -> undo dismiss (within 10s window)
```

Request/response bodies:

```python
class ApproveRequest(BaseModel):
    excluded_comment_ids: list[int] = Field(default_factory=list)

class ApprovalResponse(BaseModel):
    id: UUID
    status: str
    message: str

class ErrorResponse(BaseModel):
    detail: str    # e.g., "Already approved", "Undo window expired"
```

Error codes: 409 Conflict (double approve), 404 Not Found (expired undo or unknown ID), 422 Validation Error (all comments excluded).

### WebSocket Events

New `EventType` enum members (uppercase member name, lowercase string value per existing convention):

```
PR_FIX_AWAITING_APPROVAL = "pr_fix_awaiting_approval"
    -> payload: full PendingApproval serialized (or with status "classifying" if classification in progress)

PR_FIX_APPROVED = "pr_fix_approved"
    -> payload: {approval_id, pr_number, repo, approved_by: "user" | "auto_timeout"}

PR_FIX_DISMISSED = "pr_fix_dismissed"
    -> payload: {approval_id, pr_number, repo}

PR_FIX_AUTO_APPROVE_TICK = "pr_fix_auto_approve_tick"
    -> payload: {approval_id, pr_number, repo, remaining_seconds: int}
    -> sent every 60s as a sync correction; the frontend runs a local countdown
       seeded from expires_at, using ticks only to correct drift
    -> note: for short timeouts (e.g., 1-2 minutes), few or no ticks will fire
       before auto-approval; this is acceptable since the local countdown is authoritative
```

## Frontend

### Navigation

New sidebar nav item "Approvals" under WORKFLOWS group, between "Active Jobs" and "Past Runs." `ShieldCheck` icon with live badge count from Zustand store updated via WebSocket.

Hidden when count is 0 and no profiles use manual/supervised mode. The profiles API already returns `pr_autofix` config per profile — once the new `oversight_mode` field is added (see Configuration section), the frontend checks if any profile has it set to `manual` or `supervised` to determine nav visibility. `MobileCommandBar` gets notification dot when count > 0.

### Route

`/approvals` — lazy-loaded `ApprovalsPage` with loader fetching pending approvals.

### Component Mapping

| UI Element | Component | Source |
|---|---|---|
| Approval card list | `Queue` / `QueueSection` / `QueueList` | ai-elements |
| Individual PR card | `QueueItem` + `QueueItemContent` + `QueueItemIndicator` | ai-elements |
| Approve / Dismiss buttons | `QueueItemActions` / `QueueItemAction` | ai-elements |
| Comment classification rows | `Tool` + `ToolHeader` + `ToolContent` | ai-elements |
| Classification detail | `ToolInput` / `ToolOutput` | ai-elements |
| Low-confidence confirmation | `Confirmation` / `ConfirmationActions` | ai-elements |
| Page title + count | `PageHeader` | existing dashboard |
| Mode filter tabs | `Tabs` / `TabsList` / `TabsTrigger` | shadcn/ui |
| Profile filter | `Select` | shadcn/ui |
| Per-comment toggle | `Checkbox` | shadcn/ui |
| Confidence / category labels | `Badge` | shadcn/ui |
| Card expand/collapse | `Collapsible` | shadcn/ui |
| Dismiss undo | Sonner `toast` with action | existing dashboard |
| Empty state | `Empty` / `EmptyHeader` / `EmptyTitle` | existing dashboard |

### Page Layout

```
+------------------------------------------------------------+
| Approvals                                    3 pending      |
+------------------------------------------------------------+
| [All profiles v]    [All] [Manual] [Supervised]            |
+------------------------------------------------------------+
|                                                             |
| +- 2 new PRs awaiting approval - [Show] -----------------+ |
| +-----(staged insertion banner, only when items visible)--+ |
|                                                             |
| <Queue>                                                     |
|   <QueueItem>                                               |
|     <QueueItemIndicator status="pending" />                 |
|     <QueueItemContent>                                      |
|       PR #142: Fix auth middleware            repo/backend  |
|       standard - 3 comments - @reviewer                     |
|       Auto-approves in 12:34                                |
|                                                             |
|       INCLUDED                                              |
|       <Tool state="output-available">                       |
|         [x] <Badge>Bug</Badge> null pointer   auth.py:42   |
|         [x] <Badge>Style</Badge> naming     middleware:18   |
|       </Tool>                                               |
|                                                             |
|       EXCLUDED                                              |
|       <Tool state="output-denied">                          |
|         [ ] <Badge variant="outline">Suggestion</Badge>     |
|             perf optimization               auth.py:87      |
|       </Tool>                                               |
|                                                             |
|       <QueueItemActions>                                    |
|         [Dismiss]  [Approve 2 comments]                     |
|       </QueueItemActions>                                   |
|     </QueueItemContent>                                     |
|   </QueueItem>                                              |
|                                                             |
|   <QueueItem> (collapsed)                                   |
|     PR #139: Update docs    repo/docs   thorough - 1 cmt > |
|   </QueueItem>                                              |
| </Queue>                                                    |
+------------------------------------------------------------+
```

### Card States

| State | Appearance |
|---|---|
| Collapsed | Single row: PR title, repo, mode, comment count, chevron |
| Expanded | Classifications with toggles, grouped included/excluded, action buttons |
| Approving | Loading state, then card animates out |

First card auto-expands. Others collapsed by default.

### Interactions

- **Toggle comment**: Checkbox flips `Tool` state between `output-available` and `output-denied`. Approve button count updates. All excluded = Approve disabled with tooltip "Include at least one comment."
- **Approve**: POST `/api/approvals/:id/approve` with `excluded_comment_ids`. Card animates out. Badge decrements.
- **Dismiss**: POST `/api/approvals/:id/dismiss`. Card animates out. Sonner toast: "PR #142 dismissed - [Undo]". Undo calls `/api/approvals/:id/undo`, re-inserts card.
- **New PRs (staged)**: `pr_fix_awaiting_approval` WebSocket events held in a staging buffer whenever the queue is non-empty (i.e., the page is showing at least one card). Banner: "N new PRs awaiting approval - [Show]". Clicking [Show] flushes the buffer and inserts all staged items at the top. When transitioning from empty to non-empty (queue was at zero), items insert live with no banner.
- **Auto-approve timeout**: Countdown text "Auto-approves in MM:SS". When timer fires, card disappears with toast: "PR #142 auto-approved (timeout)."

### New Components

1. `PRApprovalCard.tsx` — Composes `QueueItem` + `Tool` + `Checkbox` + `Badge`. Manages include/exclude toggle state locally before submit.
2. `NewApprovalsBar.tsx` — Staged insertion banner. Count + "Show" button.

### Empty State

```
+------------------------------------------------------------+
|                   [ ShieldCheck icon ]                      |
|             No PRs awaiting approval                        |
|                                                             |
|    PRs from profiles using manual or supervised             |
|    oversight will appear here for review.                   |
+------------------------------------------------------------+
```

### Mobile (< 768px)

Cards full-width stacked. `Tool` components collapsed by default (tap to expand). Profile filter becomes dropdown replacing tabs. `MobileCommandBar` notification dot.

## Configuration

### Profile Model Extension

New fields on `PRAutoFixConfig`:

```python
oversight_mode: Literal["autonomous", "supervised", "manual"] = "autonomous"
approval_timeout_seconds: int = 900  # 60-7200, supervised only
```

Default `autonomous` preserves existing behavior. No migration needed — missing field deserializes as `autonomous`.

### Settings UI

`PRAutoFixSection.tsx` gains radio group for oversight mode. Timeout input visible only when "Supervised" selected. Validation: 1-120 minutes.

```
+--------------------------------------------+
| PR Auto-Fix                         [on]   |
+--------------------------------------------+
| Oversight Mode                             |
| (*) Autonomous -- fixes run immediately    |
| ( ) Supervised -- queued, auto-approves    |
|     after [15] minutes                     |
| ( ) Manual -- queued, waits for approval   |
+--------------------------------------------+
| Aggressiveness    [Standard v]             |
| Poll Label        [amelia        ]         |
+--------------------------------------------+
```

## Edge Cases

### Race Conditions

| Scenario | Behavior |
|---|---|
| Approve while poller detects new comments | Approval proceeds with its comments. New comments create a fresh PendingApproval after fix cycle completes. |
| Dismiss then new comments within undo window | Undo still works. New comments create separate approval after undo window expires. |
| Two tabs approve same PR | First wins. Second gets 409 Conflict, toast: "Already approved." |
| Server restarts with pending approvals | Lost (in-memory). Next poll cycle recreates. Supervised timers compute remaining time from `expires_at - now`. |
| Auto-approve fires during user review | Approval proceeds. Card disappears with toast: "PR #142 auto-approved (timeout)." User toggles lost. |

### Poller Integration

| Scenario | Behavior |
|---|---|
| Profile autonomous -> supervised | Next poll routes through confirmation service. In-flight cycles complete normally. |
| Profile manual -> autonomous | Pending approvals auto-approved immediately and cleared. |
| Profile deleted while PRs pending | Approvals discarded. Toast: "1 approval removed (profile deleted)." |
| Rate limit hit | Existing behavior. No new approvals until cleared. Banner on Approvals page. |

### UI Edge Cases

| Scenario | Behavior |
|---|---|
| All comments toggled off | Approve disabled. Tooltip: "Include at least one comment." |
| PR closed/merged while pending | Next poll detects, approval removed. Toast: "PR #142 closed externally." |
| 0 profiles use manual/supervised | Nav item hidden. `/approvals` shows empty state explaining how to enable. |
| 20+ pending approvals | ScrollArea. Filters essential for triage. |
| WebSocket disconnects | Loader data shown. Reconnection triggers revalidation. |

## Testing

### Backend Unit Tests

- `ConfirmationService`: submit routes per mode, approve/dismiss/undo state transitions, auto-approve timer, undo expiration, excluded comments forwarded to orchestrator
- `PendingApproval` model: serialization, defaults, status transitions
- API endpoints: correct responses, 409 double-approve, 404 expired undo

### Backend Integration Tests

- Poller -> ConfirmationService -> Orchestrator full flow per mode
- Supervised auto-approve end-to-end with real asyncio timers
- Profile mode switch mid-flight
- Comment deduplication through confirmation layer

### Frontend Component Tests

- `PRApprovalCard`: renders classifications, toggles update state, approve sends correct excluded IDs, dismiss triggers toast with undo
- `ApprovalsPage`: empty state, mode/profile filters, staged banner on WebSocket event, live insertion when empty
- `NewApprovalsBar`: count display, "Show" inserts items

### Frontend Integration Tests

- WebSocket event -> sidebar badge count update
- Approve -> card out -> count decrements
- Dismiss -> undo toast -> undo re-inserts card

## Dependencies

### ai-elements

The ai-elements component library (`/Users/ka/github/ai-elements`) is not currently a dependency of the dashboard. It must be added to `dashboard/package.json` before implementation. The library provides Queue, QueueItem, Tool, and Confirmation components used throughout the Approvals page. If adding the dependency is blocked, the same UI can be built with shadcn/ui Card + Collapsible + custom composition, but ai-elements is strongly preferred for consistency with the rest of the AI workflow UI.

## Future Considerations

These are explicitly out of scope for v1 but worth noting:

- **Batch operations**: "Approve All" / "Dismiss All (filtered)" for high-volume queues
- **Non-PR approval types**: The Approvals page and route can host other approval types (e.g., plan approvals for implementation workflows) without structural changes
- **Notification channels**: Slack/email notifications when a PR enters the approval queue (currently dashboard-only)
- **Approval history**: Persist approved/dismissed records for audit trail (currently ephemeral)
