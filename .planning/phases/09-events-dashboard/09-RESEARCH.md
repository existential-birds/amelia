# Phase 9: Events & Dashboard - Research

**Researched:** 2026-03-14
**Domain:** Real-time event broadcasting + React dashboard UI for PR auto-fix workflows
**Confidence:** HIGH

## Summary

Phase 9 connects the existing PR auto-fix backend to the dashboard UI. The backend infrastructure is mature: events are emitted via EventBus, WebSocket streaming works, Zustand stores batch events, and shadcn/ui components provide all needed primitives. The work is primarily about adding 5 new event types to the EventType enum, exposing `pipeline_type` (mapped from existing `workflow_type` DB column) in WorkflowSummary, and building 3 UI additions: tab-filtered workflow list with type badges, collapsible comment section in workflow detail, and PR Auto-Fix config section in the profile edit modal.

A critical architectural discovery: PR auto-fix workflows currently do NOT create entries in the `workflows` database table. The `PRAutoFixOrchestrator._execute_pipeline()` runs the LangGraph pipeline directly without going through the server-side `OrchestratorService` that manages DB persistence. This means PR auto-fix runs are invisible in the dashboard workflow list. Phase 9 must either: (a) create lightweight server-side workflow records for PR auto-fix runs, or (b) surface PR auto-fix activity via a separate mechanism. Option (a) is strongly recommended since the existing `WorkflowType` enum can be extended with a `PR_AUTO_FIX` value, leveraging the existing `workflow_type` column in the `workflows` DB table.

**Primary recommendation:** Extend `WorkflowType` with `PR_AUTO_FIX`, have the PR orchestrator create/update server workflow records, add `pipeline_type` to WorkflowSummary/WorkflowDetail, then build the three UI features using existing shadcn/ui components.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Type badge next to existing StatusBadge -- a small "PR Fix" chip shown alongside status. Implementation and review workflows also get type badges for consistency.
- Tab bar at the top of the workflow list: All | Implementation | Review | PR Fix. Tabs filter the list by pipeline_type.
- PR auto-fix workflows show "PR #45 . 3 comments" metadata below the title (PR number + comment count).
- PR title fetched from GitHub and stored in workflow metadata -- display the actual PR title, not just the number.
- WorkflowSummary needs pipeline_type exposed to the frontend to enable badge and tab filtering.
- Collapsible comment list section in the workflow detail page. Each comment is a row with status icon (fixed/failed/skipped), file path:line, and comment snippet.
- Expandable rows show: full comment body, file:line reference, reviewer author name, and status reason. No diff hunk.
- Summary bar above the comment list: "2 fixed . 1 failed . 1 skipped" -- quick overview.
- External link icon on each comment row linking to the GitHub comment in a new tab.
- PR Auto-Fix section added to the existing profile edit modal (SettingsProfilesPage).
- Toggle switch (shadcn/ui Switch) at the top of the section: Off = pr_autofix is null (disabled). On = reveals aggressiveness and poll_label fields.
- Aggressiveness presented as a shadcn/ui Select dropdown with four levels: Critical, Standard, Thorough, Exemplary. Each option shows a brief description.
- Two config fields exposed in v1 UI: aggressiveness (Select) and poll_label (text input). Other PRAutoFixConfig fields are advanced -- configured via YAML only.
- New event types to add: pr_comments_detected, pr_auto_fix_started, pr_auto_fix_completed, pr_comments_resolved, pr_poll_error
- Only pr_auto_fix_started and pr_auto_fix_completed show in the workflow detail activity log. Detection and resolution are internal (server logs only).
- Existing orchestration events (PR_FIX_QUEUED, PR_FIX_DIVERGED, PR_FIX_COOLDOWN_STARTED, PR_FIX_COOLDOWN_RESET, PR_FIX_RETRIES_EXHAUSTED) DO show in the workflow detail activity log.
- pr_poll_error triggers a toast notification in the dashboard so users notice immediately when polling breaks.
- pr_poll_rate_limited does NOT trigger a toast -- it's expected behavior. Activity log / server logs only.
- Use shadcn/ui and existing ai-elements components exclusively -- no custom components.

### Claude's Discretion
- Exact shadcn/ui component choices for the comment list (Collapsible vs Accordion vs custom Card layout)
- How to surface the GitHub external link (icon placement, tooltip)
- Tab bar implementation (shadcn/ui Tabs vs custom)
- Activity log event formatting for PR-specific events
- How pipeline_type flows from backend state to WorkflowSummary API response
- Toast notification implementation details (duration, styling, deduplication)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DASH-01 | New event types: pr_comments_detected, pr_auto_fix_started, pr_auto_fix_completed, pr_comments_resolved, pr_poll_error | EventType enum pattern documented; PERSISTED_TYPES set needs updates; level classification needed |
| DASH-02 | PR auto-fix workflows appear in dashboard workflow list with distinct badge/icon | WorkflowType enum extension + WorkflowSummary.pipeline_type field; TypeBadge component; Tab filtering |
| DASH-03 | Dashboard shows which PR comments triggered a workflow | Comment data stored in PRAutoFixState.comments; needs API endpoint to surface; collapsible comment section |
| DASH-04 | Dashboard shows resolution status per comment (fixed/failed/skipped) | GroupFixResult.comment_ids + status available in pipeline state; ResolutionResult tracks reply/resolve outcome |
| DASH-05 | Dashboard UI for viewing and configuring fix aggressiveness per profile | Backend ProfileResponse already includes pr_autofix; frontend Profile type needs pr_autofix field; edit modal needs section |
</phase_requirements>

## Architecture Patterns

### Backend Changes

#### 1. WorkflowType Extension
The `workflows` DB table already has a `workflow_type TEXT` column (defaults to 'full'). `WorkflowType` enum at `amelia/server/models/state.py:27` currently has `FULL` and `REVIEW`. Add `PR_AUTO_FIX = "pr_auto_fix"`.

No DB migration needed -- the column is TEXT and accepts any string value.

#### 2. WorkflowSummary pipeline_type Field
Add `pipeline_type: str | None = None` to `WorkflowSummary` and `WorkflowDetailResponse` in `amelia/server/models/responses.py`. Populate from `ServerExecutionState.workflow_type` when building summaries in `amelia/server/routes/workflows.py` (lines 212 and 268).

Frontend `WorkflowSummary` and `WorkflowDetail` types in `dashboard/src/types/index.ts` need corresponding `pipeline_type` field.

#### 3. PR Auto-Fix Workflow Records
The `PRAutoFixOrchestrator` must create server-side workflow records so PR auto-fix runs appear in the dashboard. Two integration points:

- **Before pipeline execution** (`_execute_pipeline`): Create a `ServerExecutionState` with `workflow_type=WorkflowType.PR_AUTO_FIX` and persist via `WorkflowRepository.create()`. Store PR metadata (pr_number, pr_title, comment_count) in `issue_cache` JSONB.
- **After pipeline completion**: Update the workflow record status to completed/failed.

The orchestrator needs access to `WorkflowRepository` (inject via constructor or access from app state).

#### 4. Event Type Additions
Add to `EventType` enum in `amelia/server/models/events.py`:

```python
# PR Auto-Fix lifecycle
PR_COMMENTS_DETECTED = "pr_comments_detected"
PR_AUTO_FIX_STARTED = "pr_auto_fix_started"
PR_AUTO_FIX_COMPLETED = "pr_auto_fix_completed"
PR_COMMENTS_RESOLVED = "pr_comments_resolved"
PR_POLL_ERROR = "pr_poll_error"
```

Level classifications:
- `PR_COMMENTS_DETECTED`: INFO (internal, not persisted to workflow log)
- `PR_AUTO_FIX_STARTED`: INFO (persisted, shows in activity log)
- `PR_AUTO_FIX_COMPLETED`: INFO (persisted, shows in activity log)
- `PR_COMMENTS_RESOLVED`: INFO (internal, not persisted)
- `PR_POLL_ERROR`: ERROR (persisted)

Add to `PERSISTED_TYPES`: PR_AUTO_FIX_STARTED, PR_AUTO_FIX_COMPLETED, PR_POLL_ERROR.
Add to `_INFO_TYPES`: PR_COMMENTS_DETECTED, PR_AUTO_FIX_STARTED, PR_AUTO_FIX_COMPLETED, PR_COMMENTS_RESOLVED.
Add to `_ERROR_TYPES`: PR_POLL_ERROR.

Update frontend `EventType` union in `dashboard/src/types/index.ts`.

#### 5. Comment Data API
PR comment data and resolution results live in `PRAutoFixState` (the LangGraph pipeline state). To surface this in the dashboard, either:

(a) Store comment data + resolution results in the workflow's `issue_cache` JSONB after pipeline completion (simpler, no new endpoint).
(b) Create a new endpoint `GET /api/workflows/{id}/pr-comments` that reads from pipeline checkpoints.

Recommend (a): write comment/resolution data to `issue_cache` at pipeline completion. The frontend can read it from `WorkflowDetailResponse` by adding a `pr_comments` field or by reading from existing `issue_cache` data.

### Frontend Changes

#### 1. TypeBadge Component
Create alongside StatusBadge using the same `cva` pattern. Variants: `implementation` (default), `review`, `pr_fix`. Small chip with distinct colors for each type.

Recommendation: Use the existing shadcn/ui `Badge` component with variant styling rather than a fully custom component (aligns with "no custom components" constraint). Apply different `className` based on `pipeline_type`.

#### 2. Tab-Filtered Workflow List
Add shadcn/ui `Tabs` component to `WorkflowsPage.tsx` above the existing `JobQueue`. Tabs: All | Implementation | Review | PR Fix. Filter `workflows` array by `pipeline_type` before passing to `JobQueue`.

The shadcn/ui `Tabs` component exists at `dashboard/src/components/ui/tabs.tsx` and is already imported in `ProfileEditModal.tsx`. Pattern is established.

#### 3. PR Metadata in Job Queue Items
Extend `JobQueueItem` to show "PR #45 . 3 comments" metadata when `pipeline_type === 'pr_auto_fix'`. Add `pipeline_type` and optional `pr_metadata` to the props Pick type.

#### 4. Comment Section in Workflow Detail
Add a collapsible section below the goal card in `WorkflowDetailPage.tsx`. Use shadcn/ui `Collapsible` for the section and for individual expandable rows.

Structure:
```
REVIEW COMMENTS (section header)
[Summary bar: "2 fixed . 1 failed . 1 skipped"]
[Comment row: status icon | file.py:42 | "Consider using..." | external link]
  [Expanded: full body, author, status reason]
```

Icons: CheckCircle (fixed/green), XCircle (failed/red), MinusCircle (skipped/muted).

#### 5. PR Auto-Fix Section in Profile Edit Modal
`ProfileEditModal.tsx` already uses Switch, Select, Tabs, Collapsible, and Badge. Add a new section after the existing sandbox section. Structure:

```
PR AUTO-FIX (section header)
[Switch: Enable PR Auto-Fix]
  (when enabled:)
  [Select: Aggressiveness - Critical/Standard/Thorough/Exemplary]
  [Input: Poll Label]
```

The backend `ProfileResponse` already returns `pr_autofix`. Frontend `Profile` type in `api/settings.ts` needs `pr_autofix?: PRAutoFixConfig | null` added. `ProfileUpdate` needs `pr_autofix?: PRAutoFixConfig | null` for saving.

#### 6. Toast for pr_poll_error
The `useWebSocket` hook dispatches `workflow-event` CustomEvents. Add a listener that checks for `pr_poll_error` event type and calls `Toast.error()`. Use the existing `Toast` module from `dashboard/src/components/Toast.tsx`.

For deduplication: track last toast timestamp per event type, suppress if within 30 seconds. This prevents toast spam during sustained polling failures.

### Recommended Project Structure (new/modified files)

```
amelia/server/models/
  events.py               # Add 5 new EventType values + classifications
  responses.py            # Add pipeline_type to WorkflowSummary/WorkflowDetail
  state.py                # Add PR_AUTO_FIX to WorkflowType enum

amelia/pipelines/pr_auto_fix/
  orchestrator.py          # Create/update workflow DB records, emit new events

dashboard/src/types/
  index.ts                 # Add pipeline_type to WorkflowSummary/WorkflowDetail, new EventType values

dashboard/src/api/
  settings.ts              # Add pr_autofix to Profile/ProfileUpdate types

dashboard/src/components/
  TypeBadge.tsx            # New: pipeline type badge using Badge variant
  PRCommentSection.tsx     # New: collapsible comment list for PR Fix workflows

dashboard/src/pages/
  WorkflowsPage.tsx        # Add tab filtering, type badge
  WorkflowDetailPage.tsx   # Add PR comment section (conditional)

dashboard/src/components/settings/
  ProfileEditModal.tsx     # Add PR Auto-Fix section (Switch + Select + Input)

dashboard/src/hooks/
  useWebSocket.ts          # Add pr_poll_error toast notification
```

### Anti-Patterns to Avoid
- **Over-engineering the comment data flow:** Don't create a separate database table for PR comments. Store them in the workflow's `issue_cache` JSONB column -- they're ephemeral per-run data, not entities.
- **Re-fetching PR comments from GitHub:** The pipeline already has all comment data in state. Persist it at completion, don't re-fetch.
- **Custom component patterns:** Use shadcn/ui Badge with className variants instead of creating a new CVA-based TypeBadge from scratch.
- **Polling for comment updates:** Comment data is set once at pipeline completion. No real-time updates needed for the comment list.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tab filtering | Custom tab bar with CSS | shadcn/ui `Tabs` + `TabsList` + `TabsTrigger` | Already imported in ProfileEditModal, consistent with project |
| Toggle for on/off config | Custom checkbox logic | shadcn/ui `Switch` | Established pattern in project |
| Dropdown for aggressiveness | Custom dropdown | shadcn/ui `Select` | Used extensively in ProfileEditModal |
| Collapsible sections | Custom accordion | shadcn/ui `Collapsible` | Available in ui/ directory |
| Toast notifications | Custom notification system | `sonner` via existing Toast module | Already used throughout dashboard |
| Status icons | Custom SVG components | `lucide-react` icons (CheckCircle2, XCircle, MinusCircle) | Consistent with existing icon usage |

## Common Pitfalls

### Pitfall 1: Missing Workflow Records for PR Auto-Fix
**What goes wrong:** PR auto-fix workflows never appear in the dashboard because they bypass WorkflowRepository.
**Why it happens:** PRAutoFixOrchestrator runs pipelines directly without creating server-side state.
**How to avoid:** Must create ServerExecutionState records in WorkflowRepository before executing the pipeline.
**Warning signs:** Empty workflow list despite running PR auto-fix.

### Pitfall 2: Frontend Type Misalignment
**What goes wrong:** TypeScript types don't match backend response, causing runtime errors.
**Why it happens:** Backend ProfileResponse already has pr_autofix but frontend Profile type doesn't.
**How to avoid:** Update all three layers in lockstep: backend model, frontend type, frontend API client.
**Warning signs:** Build passes but runtime undefined errors on pr_autofix fields.

### Pitfall 3: Event Type String Mismatch
**What goes wrong:** Frontend doesn't recognize new event types from WebSocket.
**Why it happens:** Backend uses StrEnum values, frontend uses union of string literals. Must match exactly.
**How to avoid:** Add all 5 new event types to the frontend EventType union. Also add PR orchestration event types that are already in the backend but missing from the frontend type.
**Warning signs:** Console warnings about unknown event types.

### Pitfall 4: pipeline_type Null for Legacy Workflows
**What goes wrong:** Existing workflows have `workflow_type='full'` but frontend code assumes pipeline_type is always set.
**Why it happens:** Old workflows created before this phase won't have the new field.
**How to avoid:** Default `pipeline_type` to `'full'` (or map from workflow_type). Tab filtering "All" tab must handle null/undefined gracefully.
**Warning signs:** Legacy workflows disappear from the list or show no type badge.

### Pitfall 5: Toast Spam from Polling Errors
**What goes wrong:** Every poll error triggers a new toast, flooding the UI.
**Why it happens:** Poller retries frequently, each error emits an event.
**How to avoid:** Deduplicate toasts -- track last toast timestamp, suppress if within 30s. Only show for pr_poll_error, never for pr_poll_rate_limited.
**Warning signs:** Multiple identical error toasts stacking.

### Pitfall 6: ProfileEditModal Size Explosion
**What goes wrong:** The modal becomes unwieldy with the new PR Auto-Fix section.
**Why it happens:** ProfileEditModal.tsx is already 52KB+ with complex agent configuration.
**How to avoid:** Extract the PR Auto-Fix section into its own component (e.g., `PRAutoFixSection.tsx`). Keep the modal component focused on layout and orchestration.
**Warning signs:** Render performance degradation, hard to navigate the file.

## Code Examples

### Adding EventType Values (Python)
```python
# In amelia/server/models/events.py - add to EventType class

# PR Auto-Fix lifecycle
PR_COMMENTS_DETECTED = "pr_comments_detected"
PR_AUTO_FIX_STARTED = "pr_auto_fix_started"
PR_AUTO_FIX_COMPLETED = "pr_auto_fix_completed"
PR_COMMENTS_RESOLVED = "pr_comments_resolved"
PR_POLL_ERROR = "pr_poll_error"
```

### Extending WorkflowType
```python
# In amelia/server/models/state.py
class WorkflowType(StrEnum):
    FULL = "full"
    REVIEW = "review"
    PR_AUTO_FIX = "pr_auto_fix"
```

### Adding pipeline_type to WorkflowSummary
```python
# In amelia/server/models/responses.py - add to WorkflowSummary
pipeline_type: Annotated[
    str | None,
    Field(default=None, description="Pipeline type: full, review, or pr_auto_fix"),
] = None
```

### TypeBadge Using Existing Badge
```tsx
// Using shadcn/ui Badge with variant mapping
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const TYPE_STYLES = {
  full: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  review: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  pr_auto_fix: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
} as const;

const TYPE_LABELS = {
  full: 'Implementation',
  review: 'Review',
  pr_auto_fix: 'PR Fix',
} as const;

type PipelineType = keyof typeof TYPE_STYLES;

function TypeBadge({ type }: { type: string }) {
  const pipelineType = (type || 'full') as PipelineType;
  return (
    <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0', TYPE_STYLES[pipelineType])}>
      {TYPE_LABELS[pipelineType]}
    </Badge>
  );
}
```

### Tab Filtering Pattern
```tsx
// Using existing shadcn/ui Tabs in WorkflowsPage
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

const [activeTab, setActiveTab] = useState('all');

const filteredWorkflows = activeTab === 'all'
  ? workflows
  : workflows.filter(w => w.pipeline_type === activeTab);

<Tabs value={activeTab} onValueChange={setActiveTab}>
  <TabsList>
    <TabsTrigger value="all">All</TabsTrigger>
    <TabsTrigger value="full">Implementation</TabsTrigger>
    <TabsTrigger value="review">Review</TabsTrigger>
    <TabsTrigger value="pr_auto_fix">PR Fix</TabsTrigger>
  </TabsList>
</Tabs>
```

### PR Auto-Fix Toggle in Profile Edit
```tsx
// PR Auto-Fix section within ProfileEditModal
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const AGGRESSIVENESS_LEVELS = [
  { value: 'critical', label: 'Critical', description: 'Only fix clear bugs and errors' },
  { value: 'standard', label: 'Standard', description: 'Fix bugs plus style/convention issues' },
  { value: 'thorough', label: 'Thorough', description: 'Address most actionable feedback' },
  { value: 'exemplary', label: 'Exemplary', description: 'Fix everything including suggestions' },
];
```

### Toast Deduplication in useWebSocket
```tsx
// In useWebSocket.ts - handle pr_poll_error events
let lastPollErrorToastMs = 0;
const POLL_ERROR_TOAST_COOLDOWN_MS = 30_000;

// Inside handleEvent callback:
if (event.event_type === 'pr_poll_error') {
  const now = Date.now();
  if (now - lastPollErrorToastMs > POLL_ERROR_TOAST_COOLDOWN_MS) {
    Toast.error(event.message || 'PR polling error');
    lastPollErrorToastMs = now;
  }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PR auto-fix invisible in dashboard | PR auto-fix has workflow records + events | Phase 9 | Users see all workflow types |
| No pipeline_type on WorkflowSummary | pipeline_type field exposed | Phase 9 | Tab filtering + type badges |
| pr_autofix not in frontend Profile type | Frontend Profile includes pr_autofix | Phase 9 | Dashboard can configure auto-fix |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (Python), vitest (frontend) |
| Config file | `pyproject.toml` (Python), `dashboard/vitest.config.ts` (frontend) |
| Quick run command | `uv run pytest tests/unit/ -x` / `cd dashboard && pnpm test:run` |
| Full suite command | `uv run pytest && cd dashboard && pnpm test:run` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | 5 new event types classified correctly | unit | `uv run pytest tests/unit/server/ -k "event" -x` | Partial (test_event_filtering.py exists) |
| DASH-02 | WorkflowSummary has pipeline_type, TypeBadge renders | unit | `cd dashboard && pnpm test:run -- --reporter=verbose` | Partial (WorkflowsPage.test.tsx exists) |
| DASH-03 | Comment section renders with correct data | unit | `cd dashboard && pnpm test:run -- --reporter=verbose` | No (new component) |
| DASH-04 | Comment resolution status displays correctly | unit | `cd dashboard && pnpm test:run -- --reporter=verbose` | No (new component) |
| DASH-05 | PR Auto-Fix section in profile edit works | unit | `cd dashboard && pnpm test:run -- --reporter=verbose` | Partial (SettingsProfilesPage.test.tsx exists) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x && cd dashboard && pnpm test:run`
- **Per wave merge:** `uv run pytest && cd dashboard && pnpm test:run && pnpm build`
- **Phase gate:** Full suite + `uv run mypy amelia` + `uv run ruff check amelia` + `pnpm lint:fix`

### Wave 0 Gaps
- [ ] Frontend tests for PRCommentSection component
- [ ] Frontend tests for TypeBadge component
- [ ] Backend unit tests for new event type classifications (extend existing test_event_filtering.py)
- [ ] Frontend test updates for WorkflowsPage tab filtering
- [ ] Frontend test updates for ProfileEditModal pr_autofix section

## Open Questions

1. **How should PR auto-fix workflow records be created?**
   - What we know: PRAutoFixOrchestrator runs pipelines without WorkflowRepository. The workflows table has a workflow_type column.
   - What's unclear: Whether to inject WorkflowRepository into PRAutoFixOrchestrator or use a lighter-weight approach.
   - Recommendation: Inject WorkflowRepository via constructor. Create records in `_execute_pipeline()` before running, update on completion. Use `issue_cache` JSONB for PR metadata (pr_number, pr_title, comment_count, comments, resolution_results).

2. **Where to store comment resolution data for the frontend?**
   - What we know: GroupFixResult and ResolutionResult are in PRAutoFixState (LangGraph state). The workflow DB has issue_cache JSONB.
   - What's unclear: Best serialization format for the frontend.
   - Recommendation: After pipeline completion, serialize comment data + resolution results into `issue_cache`. Add a `pr_comments` field to WorkflowDetailResponse that reads from issue_cache.

3. **How to get PR title for display?**
   - What we know: PRSummary has title field. The poller and CLI triggers already have PR context.
   - What's unclear: Where in the flow to fetch and persist the title.
   - Recommendation: Fetch PR title when creating the workflow record (before pipeline execution). Store in issue_cache. The GitHub PR service already provides PRSummary with title.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `amelia/server/models/events.py` - EventType enum, PERSISTED_TYPES, level classification sets
- Codebase analysis: `amelia/server/models/responses.py` - WorkflowSummary, WorkflowDetailResponse structure
- Codebase analysis: `amelia/server/models/state.py` - WorkflowType enum, ServerExecutionState
- Codebase analysis: `amelia/pipelines/pr_auto_fix/orchestrator.py` - _emit_event pattern, _execute_pipeline flow
- Codebase analysis: `amelia/pipelines/pr_auto_fix/state.py` - PRAutoFixState, GroupFixResult, ResolutionResult
- Codebase analysis: `amelia/server/database/migrations/001_initial_schema.sql` - workflows table schema with workflow_type TEXT column
- Codebase analysis: `dashboard/src/types/index.ts` - WorkflowSummary, EventType, WorkflowEvent types
- Codebase analysis: `dashboard/src/components/StatusBadge.tsx` - CVA pattern for badges
- Codebase analysis: `dashboard/src/components/settings/ProfileEditModal.tsx` - Switch, Select, Tabs patterns
- Codebase analysis: `dashboard/src/store/workflowStore.ts` - Zustand event batching
- Codebase analysis: `dashboard/src/hooks/useWebSocket.ts` - WebSocket event handling, custom event dispatch
- Codebase analysis: `dashboard/src/components/Toast.tsx` - Sonner toast wrapper
- Codebase analysis: `dashboard/src/api/settings.ts` - Profile API (missing pr_autofix field)
- Codebase analysis: `amelia/server/routes/settings.py` - ProfileResponse already has pr_autofix

### Secondary (MEDIUM confidence)
- shadcn/ui components verified present: tabs.tsx, switch.tsx, select.tsx, collapsible.tsx, badge.tsx

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all components exist in the project, patterns established
- Architecture: HIGH - thorough codebase analysis reveals exact integration points
- Pitfalls: HIGH - identified through code analysis (missing DB records, type misalignment)

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable codebase, no external dependency changes)
