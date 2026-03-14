# Phase 10: Metrics & Benchmarking - Research

**Researched:** 2026-03-14
**Domain:** Metrics persistence, aggregation APIs, dashboard visualization (recharts)
**Confidence:** HIGH

## Summary

Phase 10 adds metrics collection, persistence, and visualization for the PR auto-fix pipeline. The domain is well-bounded: two new database tables (pipeline run metrics and classification audit log), two new API endpoints, and a new "Analytics" page that reuses the established CostsPage patterns (date presets, recharts charts, DataTable).

The primary technical risk is low -- all patterns already exist in the codebase. The metrics collection hooks into the orchestrator's `_execute_pipeline` method (timing), the classifier service (classification decisions), and the pipeline state (group results). The dashboard side follows the CostsPage template almost exactly: loader fetches data, recharts renders charts, DataTable renders tabular audit log.

**Primary recommendation:** Follow the CostsPage/usage.py pattern exactly -- new Pydantic response models, new repository methods with `date_trunc` aggregation, new route file, new dashboard page with Tabs component switching between Costs and PR Fix Metrics.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- End-to-end latency only (comment detection to fix pushed) -- no per-node breakdown
- Classification decisions stored in DB: comment_id, comment_text snippet, category, confidence, actionable, aggressiveness_level
- METR-04 (fix acceptance tracking / re-opened threads) deferred to v2 -- success/fail/skip per comment is enough signal for v1
- Full per-run counters: comments_processed, fixes_applied, commits_pushed, threads_resolved, duration_seconds, aggressiveness_level
- Prompt hash tracked with each metric record -- enables before/after comparison when iterating on classification prompt
- Rename CostsPage to "Analytics" -- add PR Fix Metrics as a second tab alongside Costs
- Line chart for latency trends over time + stacked bar chart for success/fail/skip breakdown by aggressiveness level
- Uses recharts (already used by CostsPage)
- Reuse CostsPage date preset system (7d/30d/90d/custom) for consistent UX across both tabs
- Filter by profile (multi-repo support)
- Filter/breakdown by aggressiveness level (core signal for tuning)
- No per-PR drill-down or CSV export in v1
- Single aggregate endpoint: `GET /api/github/pr-autofix/metrics?start=&end=&profile=&aggressiveness=`
- Returns summary stats + daily-bucketed time series in one response
- Separate endpoint for classification audit: `GET /api/github/pr-autofix/classifications?start=&end=&limit=`
- Pre-bucketed by day: [{date, total_runs, fixed, failed, skipped, avg_latency_s}]

### Claude's Discretion
- Classification audit log UI component choice (explore shadcn/ui DataTable, Collapsible, etc.)
- Exact Pydantic response model structure for metrics and classifications endpoints
- Database table/migration design for metrics and classification records
- Chart color scheme and exact layout within the Analytics tab
- Whether to extract shared date preset logic from CostsPage into a reusable hook

### Deferred Ideas (OUT OF SCOPE)
- METR-04: Fix acceptance tracking (re-opened threads) -- deferred to v2
- Per-PR drill-down in dashboard
- CSV export for PR fix metrics
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| METR-01 | Track time from comment detection to fix pushed (end-to-end latency) | Timing in orchestrator `_execute_pipeline`: capture `start_time = time.monotonic()` before pipeline, `duration = time.monotonic() - start_time` after. Store as `duration_seconds` float in `pr_autofix_runs` table. |
| METR-02 | Track fix success rate per aggressiveness level | Per-run record stores `aggressiveness_level`, `comments_processed`, `fixes_applied`, `fixes_failed`, `fixes_skipped`. Aggregate endpoint groups by aggressiveness for rate calculation. |
| METR-03 | Track classification accuracy -- log LLM classification decisions with comment text | New `pr_autofix_classifications` table stores per-classification row: comment_id, body snippet, category, confidence, actionable, aggressiveness, prompt_hash. Populated in `classify_node` or `classify_comments`. |
| METR-04 | Track fix acceptance rate (re-opened threads) | DEFERRED to v2 per user decision. No implementation needed. |
| METR-05 | Track per-pipeline-run metrics: comments processed, fixes applied, commits pushed, threads resolved | All available from pipeline final state: `len(comments)`, count of FIXED/FAILED/SKIPPED in `group_results`, `commit_sha is not None`, count of `resolved=True` in `resolution_results`. Store in `pr_autofix_runs` table. |
| METR-06 | Persist metrics to database for historical analysis and trend reporting | Two new tables via migration 009: `pr_autofix_runs` (per-run aggregate) and `pr_autofix_classifications` (per-classification audit). |
| METR-07 | Expose metrics via API endpoint `GET /api/github/pr-autofix/metrics` | New route in `amelia/server/routes/github.py` (or new file). Returns `PRAutoFixMetricsResponse` with summary + daily time series. Follows `get_usage` pattern. |
| METR-08 | Dashboard view showing fix success rates, latency trends, and per-aggressiveness-level breakdown | New `AnalyticsPage` replaces `CostsPage` with Tabs (Costs, PR Fix Metrics). Recharts line chart for latency, stacked bar for success/fail/skip by aggressiveness. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncpg | (existing) | PostgreSQL queries for metrics persistence and aggregation | Already used throughout; `date_trunc`, aggregate functions are battle-tested |
| Pydantic | (existing) | Response models for metrics API | Project convention -- all data structures are Pydantic models |
| FastAPI | (existing) | API endpoints for metrics and classifications | Project convention |
| recharts | (existing) | Charts for latency trends and success rate visualization | Already used by CostsPage; `BarChart`, `LineChart`, `AreaChart` all available |
| @tanstack/react-table | (existing) | DataTable for classification audit log | Already used by CostsPage for model breakdown table |
| shadcn/ui Tabs | (existing) | Tab navigation between Costs and PR Fix Metrics | Already in project (`tabs.tsx`), used in ProfileEditModal |
| hashlib (stdlib) | 3.12+ | SHA-256 hash of classification prompt for prompt_hash tracking | No external dependency needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| shadcn/ui Collapsible | (existing) | Expandable classification audit rows | For showing full comment text on click |
| shadcn/ui DataTable | (existing) | Classification audit log | Primary display component for audit data |
| time.monotonic | stdlib | End-to-end latency measurement | NTP-immune timing (project convention from Phase 8) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate migration file | JSONB column on workflows | Dedicated tables enable proper SQL aggregation; JSONB would require complex JSON path queries |
| New metrics route file | Add to existing github.py | github.py is already 400 lines; new file keeps concerns separated but either works |
| Extract date preset hook | Keep duplicated in each tab | Extraction adds a reusable hook but increases scope; duplication is acceptable for 2 tabs |

## Architecture Patterns

### Recommended Project Structure
```
amelia/server/
  database/
    migrations/
      009_add_pr_autofix_metrics.sql    # New tables
    metrics_repository.py               # New repository (or extend repository.py)
  models/
    metrics.py                          # New Pydantic response models
  routes/
    github.py                           # Add metrics endpoints (or new metrics.py)

amelia/pipelines/pr_auto_fix/
    orchestrator.py                     # Add timing + metrics persistence calls
    nodes.py                            # Add classification logging in classify_node

amelia/services/
    classifier.py                       # Add prompt_hash computation

dashboard/src/
  pages/
    AnalyticsPage.tsx                   # New page with Tabs (Costs + PR Fix Metrics)
  components/
    PRFixMetricsTab.tsx                 # PR Fix Metrics charts and summary
    ClassificationAuditLog.tsx          # Audit log DataTable
    LatencyTrendChart.tsx               # Line chart for latency over time
    SuccessBreakdownChart.tsx           # Stacked bar chart by aggressiveness
  loaders/
    analytics.ts                        # Loader for analytics page (costs + metrics)
  api/
    client.ts                           # Add getAutoFixMetrics, getClassifications
```

### Pattern 1: Metrics Collection in Orchestrator
**What:** Wrap pipeline execution with timing and extract counters from final state.
**When to use:** Every `_execute_pipeline` call.
**Example:**
```python
# In orchestrator._execute_pipeline
import time
import hashlib

start_time = time.monotonic()
# ... run pipeline ...
duration_seconds = time.monotonic() - start_time

# Extract counters from final_state dict
comments = final_state.get("comments", [])
group_results = final_state.get("group_results", [])
resolution_results = final_state.get("resolution_results", [])

fixed = sum(1 for r in group_results if _status(r) == "fixed")
failed = sum(1 for r in group_results if _status(r) == "failed")
skipped = len(comments) - fixed - failed
threads_resolved = sum(1 for r in resolution_results if _resolved(r))
commits_pushed = 1 if final_state.get("commit_sha") else 0

# Persist to pr_autofix_runs table
```

### Pattern 2: Classification Audit Logging
**What:** After LLM classification in `classify_comments`, persist each decision.
**When to use:** Every classification batch.
**Example:**
```python
# In classifier.py or classify_node
import hashlib

prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]

# After classification, for each result:
# Store: run_id, comment_id, body_snippet, category, confidence,
#        actionable, aggressiveness_level, prompt_hash, created_at
```

### Pattern 3: Daily Bucketed Aggregation (from existing usage.py)
**What:** PostgreSQL `date_trunc('day', ...)` for time series aggregation.
**When to use:** Metrics endpoint returning daily buckets.
**Example:**
```sql
SELECT
    date_trunc('day', created_at)::date as date,
    COUNT(*) as total_runs,
    SUM(fixes_applied) as fixed,
    SUM(fixes_failed) as failed,
    SUM(fixes_skipped) as skipped,
    AVG(duration_seconds) as avg_latency_s
FROM pr_autofix_runs
WHERE created_at::date >= $1 AND created_at::date <= $2
GROUP BY date_trunc('day', created_at)::date
ORDER BY date
```

### Pattern 4: Analytics Page with Tabs
**What:** Replace `/costs` route with `/analytics` using Tabs component.
**When to use:** Single page, two tabs.
**Example:**
```tsx
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

export default function AnalyticsPage() {
  return (
    <Tabs defaultValue="costs">
      <TabsList>
        <TabsTrigger value="costs">Costs</TabsTrigger>
        <TabsTrigger value="pr-fix">PR Fix Metrics</TabsTrigger>
      </TabsList>
      <TabsContent value="costs">
        {/* Existing CostsPage content */}
      </TabsContent>
      <TabsContent value="pr-fix">
        <PRFixMetricsTab />
      </TabsContent>
    </Tabs>
  );
}
```

### Anti-Patterns to Avoid
- **Storing metrics in JSONB on workflows table:** Makes SQL aggregation painful. Use proper relational tables.
- **Computing metrics on-the-fly from workflow_log events:** Slow, fragile. Persist pre-computed counters at pipeline completion time.
- **Separate API calls per chart:** Single endpoint returning summary + time series (matches CostsPage pattern) is more efficient.
- **Measuring latency with `datetime.now(UTC)`:** Use `time.monotonic()` for NTP-immune duration measurement (project convention from Phase 8).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Date range presets | Custom date parsing logic | Copy CostsPage PRESETS pattern + usage.py PRESETS dict | Already proven, consistent UX |
| Time series charts | Custom SVG/Canvas charts | recharts `LineChart`, `BarChart` with `ChartContainer` | Already integrated, shadcn/ui chart wrapper handles theming |
| Data tables | Custom table markup | `DataTable` + `DataTableColumnHeader` components | Already in project with sorting, consistent with CostsPage |
| Prompt hashing | Custom hash function | `hashlib.sha256(prompt.encode()).hexdigest()[:16]` | stdlib, deterministic, 16-char truncation is enough for comparison |
| Parameterized SQL | String formatting | asyncpg `$1, $2` placeholders | Already the project pattern, prevents SQL injection |

## Common Pitfalls

### Pitfall 1: Race Condition Between Pipeline Completion and Metrics Write
**What goes wrong:** Pipeline completes but metrics write fails; user sees workflow but no metrics.
**Why it happens:** Metrics write is a separate DB call after pipeline.
**How to avoid:** Write metrics in the same `_execute_pipeline` method after updating workflow state, within the try block. If metrics write fails, log warning but don't fail the workflow.
**Warning signs:** Missing metrics for completed workflows.

### Pitfall 2: Prompt Hash Changes Breaking Comparison
**What goes wrong:** Hash changes when prompt has whitespace-only edits, breaking A/B comparison.
**Why it happens:** Hash includes all whitespace.
**How to avoid:** Normalize whitespace before hashing: `hashlib.sha256(prompt.strip().encode()).hexdigest()[:16]`.
**Warning signs:** Multiple prompt_hash values when user believes prompt hasn't changed.

### Pitfall 3: Counting Mismatches Between Comments and Group Results
**What goes wrong:** `fixes_applied + fixes_failed + fixes_skipped != comments_processed`.
**Why it happens:** Group results are per-file-group, not per-comment. One group can contain multiple comment_ids.
**How to avoid:** Count at the comment level by iterating `group_results[].comment_ids`, not at the group level.
**Warning signs:** Metrics showing more comments than exist in a run.

### Pitfall 4: CostsPage Route Change Breaking Bookmarks
**What goes wrong:** Users bookmarked `/costs` get 404 after rename.
**Why it happens:** Route changed to `/analytics`.
**How to avoid:** Add redirect from `/costs` to `/analytics` in router.tsx.
**Warning signs:** 404 errors in browser for old URL.

### Pitfall 5: Sidebar "Benchmarks" Placeholder Confusion
**What goes wrong:** Two similar links -- "Benchmarks" (coming soon) and new "Analytics".
**Why it happens:** Existing placeholder for benchmarks.
**How to avoid:** Remove or repurpose the "Benchmarks" link. Rename "Costs" to "Analytics" in sidebar.
**Warning signs:** Users confused by two similar navigation items.

### Pitfall 6: Empty State When No PR Auto-Fix Runs Exist
**What goes wrong:** Charts crash on empty data arrays.
**Why it happens:** No PR auto-fix workflows have been run yet.
**How to avoid:** Handle empty state in PR Fix Metrics tab (show Empty component like CostsPage does).
**Warning signs:** Chart rendering errors in console.

## Code Examples

### Database Migration (009_add_pr_autofix_metrics.sql)
```sql
-- Per-run aggregate metrics for PR auto-fix pipeline
CREATE TABLE IF NOT EXISTS pr_autofix_runs (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    profile_id TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    aggressiveness_level TEXT NOT NULL,
    comments_processed INTEGER NOT NULL DEFAULT 0,
    fixes_applied INTEGER NOT NULL DEFAULT 0,
    fixes_failed INTEGER NOT NULL DEFAULT 0,
    fixes_skipped INTEGER NOT NULL DEFAULT 0,
    commits_pushed INTEGER NOT NULL DEFAULT 0,
    threads_resolved INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    prompt_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_autofix_runs_created_at
    ON pr_autofix_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_pr_autofix_runs_profile
    ON pr_autofix_runs(profile_id);
CREATE INDEX IF NOT EXISTS idx_pr_autofix_runs_aggressiveness
    ON pr_autofix_runs(aggressiveness_level);

-- Per-classification audit log
CREATE TABLE IF NOT EXISTS pr_autofix_classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES pr_autofix_runs(id),
    comment_id BIGINT NOT NULL,
    body_snippet TEXT NOT NULL,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    actionable BOOLEAN NOT NULL,
    aggressiveness_level TEXT NOT NULL,
    prompt_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_autofix_classifications_run
    ON pr_autofix_classifications(run_id);
CREATE INDEX IF NOT EXISTS idx_pr_autofix_classifications_created_at
    ON pr_autofix_classifications(created_at);
```

### Pydantic Response Models
```python
# amelia/server/models/metrics.py
from pydantic import BaseModel

class PRAutoFixMetricsSummary(BaseModel):
    total_runs: int
    total_comments_processed: int
    total_fixed: int
    total_failed: int
    total_skipped: int
    avg_latency_seconds: float
    fix_rate: float  # fixed / (fixed + failed + skipped)

class PRAutoFixDailyBucket(BaseModel):
    date: str  # YYYY-MM-DD
    total_runs: int
    fixed: int
    failed: int
    skipped: int
    avg_latency_s: float

class AggressivenessBreakdown(BaseModel):
    level: str
    runs: int
    fixed: int
    failed: int
    skipped: int
    fix_rate: float

class PRAutoFixMetricsResponse(BaseModel):
    summary: PRAutoFixMetricsSummary
    daily: list[PRAutoFixDailyBucket]
    by_aggressiveness: list[AggressivenessBreakdown]

class ClassificationRecord(BaseModel):
    comment_id: int
    body_snippet: str
    category: str
    confidence: float
    actionable: bool
    aggressiveness_level: str
    prompt_hash: str | None
    created_at: str

class ClassificationsResponse(BaseModel):
    classifications: list[ClassificationRecord]
    total: int
```

### Audit Log UI Component (Claude's Discretion Recommendation)
**Recommendation:** Use shadcn/ui `DataTable` with `Collapsible` rows for body text expansion.

```tsx
// ClassificationAuditLog.tsx
// DataTable columns: date, category, confidence, actionable, aggressiveness, prompt_hash
// Click row to expand and show full body_snippet via Collapsible
// Color-code category with existing Badge component pattern
// Pagination via limit param on API
```

This follows the project pattern (DataTable in CostsPage) while adding expandable rows for the comment body text, which can be long. The Collapsible component is already in the project.

### Date Preset Reuse (Claude's Discretion Recommendation)
**Recommendation:** Do NOT extract a shared hook. Duplicate the preset logic.

Rationale: Only 2 consumers (Costs tab and PR Fix Metrics tab). Extracting a hook adds complexity for marginal DRY benefit. When a third consumer appears, extract then. The preset logic is ~10 lines total.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No metrics at all | Dedicated metrics tables + API | Phase 10 (now) | Enables prompt tuning feedback loop |
| Metrics in workflow_log events | Pre-computed counters in metrics table | Design decision | Faster aggregation, simpler queries |

## Open Questions

1. **Metrics repository: new file or extend existing?**
   - What we know: `WorkflowRepository` is already 1000+ lines. New metrics queries are conceptually separate.
   - What's unclear: Whether a `MetricsRepository` class improves or fragments the codebase.
   - Recommendation: New `MetricsRepository` class in `repository.py` or separate `metrics_repository.py`. Lean toward separate file to match `profile_repository.py`, `settings_repository.py` pattern.

2. **Where to inject classification logging: classify_node vs classify_comments?**
   - What we know: `classify_comments` is the service function; `classify_node` is the pipeline node that calls it.
   - What's unclear: Should the service know about persistence, or should the node handle it?
   - Recommendation: Node level. `classify_node` already has access to config params (event bus, workflow ID, profile). Pass classifications + metadata to a metrics service function that handles persistence. Keeps `classify_comments` pure.

3. **Run ID generation: UUID in orchestrator vs auto-generated?**
   - What we know: `workflow_id` is created in `_execute_pipeline`. Metrics `run_id` could reuse it or be separate.
   - Recommendation: Use `workflow_id` as the FK to `workflows` table, generate a separate `id` for `pr_autofix_runs` to allow for retries (multiple runs per workflow).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (backend), vitest (frontend) |
| Config file | `pyproject.toml` (pytest), `dashboard/vitest.config.ts` (vitest) |
| Quick run command | `uv run pytest tests/unit/ -x` |
| Full suite command | `uv run pytest && cd dashboard && pnpm test:run` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| METR-01 | End-to-end latency tracked per run | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py -x -k latency` | No -- Wave 0 |
| METR-02 | Success rate per aggressiveness level | unit | `uv run pytest tests/unit/server/routes/test_metrics_routes.py -x -k aggressiveness` | No -- Wave 0 |
| METR-03 | Classification decisions logged with text | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x -k classification_audit` | No -- Wave 0 |
| METR-05 | Per-run counters extracted from state | unit | `uv run pytest tests/unit/server/test_metrics_extraction.py -x` | No -- Wave 0 |
| METR-06 | Metrics persisted to database | unit | `uv run pytest tests/unit/server/database/test_metrics_repository.py -x` | No -- Wave 0 |
| METR-07 | API endpoint returns metrics | unit | `uv run pytest tests/unit/server/routes/test_metrics_routes.py -x` | No -- Wave 0 |
| METR-08 | Dashboard renders charts and tables | unit | `cd dashboard && pnpm test:run -- --testPathPattern=PRFixMetrics` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x`
- **Per wave merge:** `uv run pytest && cd dashboard && pnpm test:run`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/server/database/test_metrics_repository.py` -- covers METR-06
- [ ] `tests/unit/server/routes/test_metrics_routes.py` -- covers METR-02, METR-07
- [ ] `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` -- extend existing with METR-01 latency tests
- [ ] `tests/unit/pipelines/pr_auto_fix/test_nodes.py` -- extend existing with METR-03 classification audit tests
- [ ] `dashboard/src/pages/__tests__/AnalyticsPage.test.tsx` -- covers METR-08

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `amelia/server/routes/usage.py` -- date range pattern, aggregation query pattern
- Codebase inspection: `amelia/server/models/usage.py` -- Pydantic response model pattern
- Codebase inspection: `amelia/server/database/repository.py` -- `get_usage_summary`, `get_usage_trend`, `date_trunc` aggregation
- Codebase inspection: `dashboard/src/pages/CostsPage.tsx` -- date presets, recharts integration, DataTable, empty state
- Codebase inspection: `dashboard/src/components/CostsTrendChart.tsx` -- recharts chart patterns (AreaChart, LineChart, ChartContainer)
- Codebase inspection: `amelia/pipelines/pr_auto_fix/orchestrator.py` -- `_execute_pipeline` method (integration point for timing)
- Codebase inspection: `amelia/pipelines/pr_auto_fix/nodes.py` -- `classify_node` (integration point for audit logging)
- Codebase inspection: `amelia/pipelines/pr_auto_fix/state.py` -- `GroupFixResult`, `GroupFixStatus`, `ResolutionResult` (source of counters)
- Codebase inspection: `amelia/agents/schemas/classifier.py` -- `CommentClassification` fields (what to log)
- Codebase inspection: `amelia/services/classifier.py` -- `classify_comments` (prompt construction for hashing)
- Codebase inspection: `dashboard/src/components/ui/tabs.tsx` -- Tabs component available
- Codebase inspection: `dashboard/src/components/ui/collapsible.tsx` -- Collapsible component available
- Codebase inspection: `dashboard/src/components/ui/data-table.tsx` -- DataTable component available

### Secondary (MEDIUM confidence)
- None needed -- all patterns are established in the existing codebase

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in project, no new dependencies
- Architecture: HIGH - direct extension of proven CostsPage/usage.py patterns
- Pitfalls: HIGH - identified from concrete code analysis of orchestrator, classifier, and dashboard
- Database design: HIGH - follows existing migration and table patterns

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable -- internal codebase patterns)
