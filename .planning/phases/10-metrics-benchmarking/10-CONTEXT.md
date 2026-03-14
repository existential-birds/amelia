# Phase 10: Metrics & Benchmarking - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Track and expose PR auto-fix performance data — latency, success rates, classification audit logs — so users can evaluate fix quality and tune aggressiveness/prompts. No new fix capabilities or pipeline changes.

</domain>

<decisions>
## Implementation Decisions

### Data collection scope
- End-to-end latency only (comment detection to fix pushed) — no per-node breakdown
- Classification decisions stored in DB: comment_id, comment_text snippet, category, confidence, actionable, aggressiveness_level
- METR-04 (fix acceptance tracking / re-opened threads) deferred to v2 — success/fail/skip per comment is enough signal for v1
- Full per-run counters: comments_processed, fixes_applied, commits_pushed, threads_resolved, duration_seconds, aggressiveness_level
- Prompt hash tracked with each metric record — enables before/after comparison when iterating on classification prompt

### Dashboard visualization
- Rename CostsPage to "Analytics" — add PR Fix Metrics as a second tab alongside Costs
- Line chart for latency trends over time + stacked bar chart for success/fail/skip breakdown by aggressiveness level
- Uses recharts (already used by CostsPage)
- Classification audit log UI approach is Claude's Discretion — explore shadcn/ui and ai-elements components to pick best fit

### Time ranges & filtering
- Reuse CostsPage date preset system (7d/30d/90d/custom) for consistent UX across both tabs
- Filter by profile (multi-repo support)
- Filter/breakdown by aggressiveness level (core signal for tuning)
- No per-PR drill-down or CSV export in v1
- Primary iteration loop: change classification prompt → observe metrics → compare via prompt hash

### API shape
- Single aggregate endpoint: `GET /api/github/pr-autofix/metrics?start=&end=&profile=&aggressiveness=`
- Returns summary stats + daily-bucketed time series in one response (matches CostsPage usage pattern)
- Separate endpoint for classification audit: `GET /api/github/pr-autofix/classifications?start=&end=&limit=`
- Pre-bucketed by day: [{date, total_runs, fixed, failed, skipped, avg_latency_s}]

### Claude's Discretion
- Classification audit log UI component choice (explore shadcn/ui DataTable, ai-elements, Collapsible, etc.)
- Exact Pydantic response model structure for metrics and classifications endpoints
- Database table/migration design for metrics and classification records
- Chart color scheme and exact layout within the Analytics tab
- Whether to extract shared date preset logic from CostsPage into a reusable hook

</decisions>

<specifics>
## Specific Ideas

- "The primary way we will iterate on this is by changing the prompt" — metrics dashboard is fundamentally a prompt tuning feedback loop
- Prompt hash tracking enables A/B-style comparison without formal experiment infrastructure
- Analytics page consolidation: costs and PR fix metrics together signals a pattern for future metrics (agent performance, etc.)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CostsPage` (`dashboard/src/pages/CostsPage.tsx`): Date presets, recharts integration, CSV export pattern, layout structure — direct template for PR Fix Metrics tab
- `costs.ts` loader (`dashboard/src/loaders/costs.ts`): Data loader pattern for metrics
- `usage.py` route (`amelia/server/routes/usage.py`): `get_usage` endpoint with date range query — pattern for metrics endpoint
- `WorkflowRepository` (`amelia/server/database/repository.py`): Has success_rate calculation pattern, daily aggregation queries
- `UsageMetrics` / `ModelUsageMetrics` (`amelia/server/models/usage.py`): Pydantic response model pattern with success_rate field
- `DashboardSidebar` already has a "Benchmarks" link placeholder

### Established Patterns
- PostgreSQL date_trunc for daily bucketing (used in usage queries)
- Zustand stores for frontend state management
- React Router v7 data loaders for page data fetching
- shadcn/ui + Tailwind CSS for all UI components
- Pydantic response models in `amelia/server/models/`

### Integration Points
- `CostsPage`: Rename to Analytics, add tab navigation between Costs and PR Fix Metrics
- `DashboardSidebar`: Update nav link text from "Costs" to "Analytics"
- `amelia/server/routes/github.py`: Add metrics and classifications endpoints
- `amelia/server/database/`: New repository or extend existing for metrics queries
- `amelia/pipelines/pr_auto_fix/`: Emit metrics data at pipeline completion
- Classification service: Capture decisions with prompt hash at classification time

</code_context>

<deferred>
## Deferred Ideas

- METR-04: Fix acceptance tracking (re-opened threads) — deferred to v2, adds polling complexity for uncertain signal
- Per-PR drill-down in dashboard — future enhancement
- CSV export for PR fix metrics — future enhancement (CostsPage pattern available when needed)

</deferred>

---

*Phase: 10-metrics-benchmarking*
*Context gathered: 2026-03-14*
