# Phase 9: Events & Dashboard - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

PR auto-fix lifecycle events and dashboard UI integration. Users can see PR auto-fix activity in real-time through the dashboard with clear status for each comment and workflow, and configure fix aggressiveness per profile. No metrics tracking or benchmarking (Phase 10).

</domain>

<decisions>
## Implementation Decisions

### PR workflow distinction
- Type badge next to existing StatusBadge — a small "PR Fix" chip shown alongside status. Implementation and review workflows also get type badges for consistency.
- Tab bar at the top of the workflow list: All | Implementation | Review | PR Fix. Tabs filter the list by pipeline_type.
- PR auto-fix workflows show "PR #45 • 3 comments" metadata below the title (PR number + comment count).
- PR title fetched from GitHub and stored in workflow metadata — display the actual PR title, not just the number.
- WorkflowSummary needs pipeline_type exposed to the frontend to enable badge and tab filtering.

### Comment detail view
- Collapsible comment list section in the workflow detail page. Each comment is a row with status icon (fixed/failed/skipped), file path:line, and comment snippet.
- Expandable rows show: full comment body, file:line reference, reviewer author name, and status reason (e.g., "Skipped: below aggressiveness threshold"). No diff hunk.
- Summary bar above the comment list: "2 fixed • 1 failed • 1 skipped" — quick overview.
- External link icon on each comment row linking to the GitHub comment in a new tab.

### Aggressiveness config UI
- PR Auto-Fix section added to the existing profile edit modal (SettingsProfilesPage).
- Toggle switch (shadcn/ui Switch) at the top of the section: Off = pr_autofix is null (disabled). On = reveals aggressiveness and poll_label fields.
- Aggressiveness presented as a shadcn/ui Select dropdown with four levels: Critical, Standard, Thorough, Exemplary. Each option shows a brief description.
- Two config fields exposed in v1 UI: aggressiveness (Select) and poll_label (text input). Other PRAutoFixConfig fields (poll_interval, max_iterations, etc.) are advanced — configured via YAML only.

### Lifecycle events
- New event types to add: pr_comments_detected, pr_auto_fix_started, pr_auto_fix_completed, pr_comments_resolved, pr_poll_error
- Only pr_auto_fix_started and pr_auto_fix_completed show in the workflow detail activity log. Detection and resolution are internal (server logs only).
- Existing orchestration events (PR_FIX_QUEUED, PR_FIX_DIVERGED, PR_FIX_COOLDOWN_STARTED, PR_FIX_COOLDOWN_RESET, PR_FIX_RETRIES_EXHAUSTED) DO show in the workflow detail activity log — gives users visibility into delays/retries.
- pr_poll_error triggers a toast notification in the dashboard so users notice immediately when polling breaks.
- pr_poll_rate_limited does NOT trigger a toast — it's expected behavior. Activity log / server logs only.

### Component approach
- Use shadcn/ui and existing ai-elements components exclusively — no custom components. Build everything from existing primitives (Badge, Select, Switch, Collapsible, Tabs, etc.).

### Claude's Discretion
- Exact shadcn/ui component choices for the comment list (Collapsible vs Accordion vs custom Card layout)
- How to surface the GitHub external link (icon placement, tooltip)
- Tab bar implementation (shadcn/ui Tabs vs custom)
- Activity log event formatting for PR-specific events
- How pipeline_type flows from backend state to WorkflowSummary API response
- Toast notification implementation details (duration, styling, deduplication)

</decisions>

<specifics>
## Specific Ideas

- Type badge approach similar to how StatusBadge works — a compact chip/variant alongside status, not replacing it
- Comment list follows the pattern of existing activity log sections in WorkflowDetailPage — a dedicated section with its own header
- Profile edit modal already exists in SettingsProfilesPage — the PR Auto-Fix section is an addition to that form, not a new modal
- Tab filtering on workflow list is a new UI pattern for this dashboard — no existing tabs on WorkflowsPage yet

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `StatusBadge` (`dashboard/src/components/StatusBadge.tsx`): Pattern for type badge — uses cva variants, can be extended or a new TypeBadge created alongside it
- `WorkflowsPage` (`dashboard/src/pages/WorkflowsPage.tsx`): Workflow list — needs tab bar addition and type badge
- `WorkflowDetailPage` (`dashboard/src/pages/WorkflowDetailPage.tsx`): Detail view — needs comment section
- `SettingsProfilesPage` (`dashboard/src/pages/SettingsProfilesPage.tsx`): Profile management — needs PR Auto-Fix section in edit modal
- `useWebSocket` (`dashboard/src/hooks/useWebSocket.ts`): WebSocket event streaming — already handles real-time events
- `workflowStore` (`dashboard/src/store/workflowStore.ts`): Zustand store with event batching — needs PR-specific event handling
- `Toast` (`dashboard/src/components/Toast.tsx`): Existing toast component for error notifications
- `EventType` enum (`amelia/server/models/events.py`): Already has PR orchestration events, needs lifecycle events added
- shadcn/ui primitives in `dashboard/src/components/ui/`: Badge, Select, Switch, Collapsible, Tabs, etc.

### Established Patterns
- Zustand stores for frontend state management
- WebSocket event streaming via useWebSocket hook
- React Router v7 data loaders for page data
- shadcn/ui + Tailwind CSS for all UI components
- EventBus broadcasts WorkflowEvent to WebSocket clients
- WorkflowSummary/WorkflowDetail types define API response shape

### Integration Points
- `EventType` enum: Add 5 new lifecycle event types
- `WorkflowSummary` (backend + frontend): Expose pipeline_type field
- `WorkflowsPage`: Add tab bar and type badge to workflow list items
- `WorkflowDetailPage`: Add collapsible comment section for PR Fix workflows
- `SettingsProfilesPage`: Add PR Auto-Fix section to profile edit modal
- `amelia/server/routes/github.py`: May need endpoint for comment resolution data
- Event bus emission points: Pipeline nodes need to emit new lifecycle events

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-events-dashboard*
*Context gathered: 2026-03-14*
