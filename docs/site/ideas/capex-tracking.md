# Capitalization Tracking Design

> **Created by:** hey-amelia bot with Claude Opus 4.5

## Overview

A system that attributes engineering work to capitalizable initiatives for financial reporting. Integrates with Amelia's existing tracker abstraction to map PRs and issues to initiatives (JIRA Epics or GitHub Projects).

### Goals

1. **Real-time attribution** — When Amelia orchestrates work, automatically capture initiative context and log hours/artifacts
2. **Retrospective analysis** — On-demand CLI scan that processes historical PRs/issues and attributes them to initiatives
3. **Auditable reports** — Finance-ready output with full traceability from hours to source artifacts

### Non-Goals

- Dollar calculations (finance applies their own labor rates)
- Document ingestion (initiatives come from tracker, not Google Docs/Notion)
- Background scheduling (on-demand only)
- Fuzzy/semantic matching (hierarchical mapping only)

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Initiative source | JIRA Epics / GitHub Projects | Tracker-native, follows existing discipline per CONTRIBUTING.md |
| Mapping strategy | Hierarchical only | Issue's parent epic/project = initiative. Enforces good hygiene. |
| Hours estimation | Workflow execution sum, PR lifecycle fallback | Measures actual work time, not idle time; PR fallback for manual/historical work |
| Workflow persistence | SQLite table | Required for accurate hours and full audit trail |
| Failed workflow credit | 50% of elapsed time | Work was done even if not completed; configurable |
| Engineer weighting | Flat rate | Finance applies their own blended rates; reduces config overhead |
| Output formats | CLI + JSON/CSV, dashboard later | CLI for automation, dashboard for exploration |
| Retrospective trigger | On-demand CLI | Avoids background job complexity |
| Audit trail | Full reasoning per attribution | SOX compliance requires traceability |

---

## Data Model

### Initiative

A capitalizable unit of work from the tracker.

```python
class Initiative(BaseModel):
    """Capitalizable work unit from tracker."""
    id: str                          # JIRA Epic key or GitHub Project ID
    name: str                        # Epic/Project name
    tracker: Literal["jira", "github"]
    capitalizable: bool              # From epic/project field or label
    start_date: date | None          # Optional time bounds
    end_date: date | None
```

### WorkflowExecution

A record of a single `amelia start` run. Primary source for hours estimation.

```python
class WorkflowExecution(BaseModel):
    """Record of a single Amelia workflow run."""
    id: str                              # UUID
    issue_id: str                        # Issue being worked on
    initiative_id: str | None            # Resolved at workflow start
    started_at: datetime
    completed_at: datetime | None
    status: Literal["running", "completed", "failed", "cancelled"]
    pr_number: int | None                # If PR was created/updated
    agents_invoked: list[str]            # ["architect", "developer", "reviewer"]

    @property
    def duration_hours(self) -> float:
        """Actual elapsed time in hours."""
        if not self.completed_at:
            return 0.0
        delta = self.completed_at - self.started_at
        return delta.total_seconds() / 3600
```

### Attribution

A mapping from artifact to initiative with audit trail.

```python
class Attribution(BaseModel):
    """Maps an artifact to an initiative with reasoning."""
    artifact_type: Literal["pull_request", "issue", "commit"]
    artifact_id: str                 # PR number, issue key, commit SHA
    artifact_url: str                # Link for auditors
    initiative_id: str               # Parent epic/project
    engineers: list[str]             # GitHub usernames involved
    hours: float                     # Estimated hours
    hours_source: Literal["workflow", "pr_lifecycle", "manual"]  # How hours were calculated
    workflow_ids: list[str]          # References to WorkflowExecution records
    method: Literal["realtime", "retrospective"]
    reasoning: list[str]             # Audit trail entries
    created_at: datetime
```

### CapexReport

Aggregated output for a time period.

```python
class CapexReport(BaseModel):
    """Aggregated capitalization report."""
    period_start: date
    period_end: date
    initiatives: list[InitiativeSummary]
    unattributed: list[Attribution]  # Orphan artifacts for review
    total_hours: float
    capitalizable_hours: float
    generated_at: datetime
```

### Persistence

SQLite tables matching these models, same database as dashboard:
- `initiatives` — cached initiative metadata from tracker
- `workflow_executions` — every `amelia start` run with timestamps
- `attributions` — PR/issue to initiative mappings with hours

---

## Architecture

### Module Structure

```
amelia/
├── agents/           # Existing: Architect, Developer, Reviewer
├── trackers/         # Existing: JIRA, GitHub issue fetching
├── capex/            # NEW
│   ├── __init__.py
│   ├── models.py     # Initiative, Attribution, CapexReport, WorkflowExecution
│   ├── tracker.py    # InitiativeTracker protocol + implementations
│   ├── estimator.py  # Workflow-based hours estimation with PR fallback
│   ├── attributor.py # Core attribution logic
│   ├── reporter.py   # Report generation (JSON, CSV)
│   └── store.py      # SQLite persistence for all capex models
├── core/
│   └── orchestrator.py  # Modified: persist WorkflowExecution records
└── main.py              # New CLI commands
```

### Tracker Extension

Add `InitiativeTracker` protocol to existing tracker abstraction:

```python
class InitiativeTracker(Protocol):
    """Fetches initiatives from tracker."""
    async def list_initiatives(self, capitalizable_only: bool = False) -> list[Initiative]: ...
    async def get_initiative_for_issue(self, issue_id: str) -> Initiative | None: ...
```

- `JiraTracker` implements via Epic parent lookup
- `GitHubTracker` implements via Project membership lookup

### Orchestrator Integration

When `amelia start` runs, the orchestrator manages `WorkflowExecution` lifecycle:

1. **Workflow start:** Create `WorkflowExecution` record with `status="running"`
2. **Initiative resolution:** Look up parent epic/project, store `initiative_id` in execution record
3. **Agent tracking:** Append to `agents_invoked` as each agent runs
4. **Workflow completion:** Update record with `completed_at`, final `status`, `pr_number`

The workflow state already tracks issue context — extend it to include initiative and persist execution timestamps.

**No new agents.** Attribution is deterministic (hierarchy lookup + workflow timestamps), not LLM-driven.

---

## CLI Commands

New command group: `amelia capex`

```bash
# List initiatives from tracker
amelia capex initiatives --tracker jira --capitalizable-only
amelia capex initiatives --tracker github

# Retrospective scan — attribute historical work
amelia capex scan --since 2025-01-01 --until 2025-03-31
amelia capex scan --quarter Q1-2025  # Convenience alias

# Generate report
amelia capex report --quarter Q1-2025 --format json > q1-capex.json
amelia capex report --quarter Q1-2025 --format csv > q1-capex.csv
amelia capex report --quarter Q1-2025 --format table  # Human-readable stdout

# Review unattributed artifacts (orphans without parent epic/project)
amelia capex unattributed --quarter Q1-2025

# Show attribution details for a specific artifact
amelia capex show PR-1293
amelia capex show PROJ-123  # Issue
```

**Real-time attribution:** No new command — happens automatically during `amelia start`.

**Configuration:** Uses existing `settings.amelia.yaml` profile for tracker credentials.

---

## Hours Estimation

### Estimation Hierarchy

Hours are calculated using a priority hierarchy:

1. **Primary: Workflow execution sum** — Actual `amelia start` run times
2. **Fallback: PR lifecycle** — Business hours between PR open and merge (for manual work or historical PRs)

### Workflow-Based Estimation

```python
def estimate_hours(
    pr: PullRequest,
    workflows: list[WorkflowExecution]
) -> tuple[float, Literal["workflow", "pr_lifecycle"], list[str]]:
    """Estimate engineering hours with source tracking.

    Returns (hours, source, reasoning) tuple for audit trail.
    """
    reasoning = []

    if workflows:
        completed = [w for w in workflows if w.status == "completed"]
        failed = [w for w in workflows if w.status == "failed"]

        hours = sum(w.duration_hours for w in completed)
        hours += sum(w.duration_hours * 0.5 for w in failed)  # Partial credit

        reasoning.append(f"Found {len(workflows)} workflow executions")
        for w in workflows:
            credit = w.duration_hours if w.status == "completed" else w.duration_hours * 0.5
            reasoning.append(f"  {w.id[:8]}: {w.status}, {credit:.2f}h")
        reasoning.append(f"Total workflow hours: {hours:.2f}")

        return hours, "workflow", reasoning
    else:
        # Fallback for manual work or historical PRs
        hours = business_hours_between(pr.created_at, pr.merged_at)
        reasoning.append("No workflow data found")
        reasoning.append(f"PR open: {pr.created_at.isoformat()}")
        reasoning.append(f"PR merged: {pr.merged_at.isoformat()}")
        reasoning.append(f"Business hours (fallback): {hours:.2f}")

        return hours, "pr_lifecycle", reasoning
```

### Workflow Hours Rules

- **Actual elapsed time** — No business hours filtering; measures real work duration
- **Completed workflows:** 100% of elapsed time
- **Failed workflows:** 50% of elapsed time (work was done, configurable)
- **Cancelled workflows:** 0% (user explicitly stopped)

### PR Lifecycle Fallback Rules

Used only when no workflow data exists (manual work or pre-capex PRs):

- Weekdays only (Mon-Fri)
- 8-hour workday (configurable)
- Excludes nights/weekends

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Multiple PRs from one workflow | Link workflow to all PRs it touched |
| One PR from multiple workflows | Sum all workflow times |
| Workflow with no PR | Still counts (planning work is capitalizable) |
| Unmerged PR with workflows | Use workflow hours, PR lifecycle ignored |

### Audit Trail Examples

**Workflow-based (preferred):**
```json
{
  "artifact_id": "PR-1293",
  "initiative_id": "INIT-001",
  "hours": 4.2,
  "hours_source": "workflow",
  "workflow_ids": ["exec-001", "exec-002", "exec-003"],
  "reasoning": [
    "Issue PROJ-456 parent epic: INIT-001",
    "Found 3 workflow executions",
    "  exec-001: completed, 1.50h",
    "  exec-002: failed, 0.40h (0.8h × 0.5)",
    "  exec-003: completed, 2.30h",
    "Total workflow hours: 4.20"
  ]
}
```

**PR lifecycle fallback (manual/historical work):**
```json
{
  "artifact_id": "PR-1294",
  "initiative_id": "INIT-001",
  "hours": 12.5,
  "hours_source": "pr_lifecycle",
  "workflow_ids": [],
  "reasoning": [
    "Issue PROJ-457 parent epic: INIT-001",
    "No workflow data found",
    "PR open: 2025-01-10T09:00:00Z",
    "PR merged: 2025-01-11T14:30:00Z",
    "Business hours (fallback): 12.50"
  ]
}
```

---

## Dashboard View (Later Phase)

### New Tab: "Capitalization"

**Initiative List View:**
- Table: Name, Type (CAPEX/OPEX), Hours, Artifacts, Status
- Filters: quarter, capitalizable only, tracker
- Click row to drill down

**Initiative Detail View:**
- Summary card: total hours, engineer count, date range
- Artifact table: all attributed PRs/issues with individual hours
- Audit panel: click any artifact to see full reasoning
- Export buttons: JSON, CSV

**Unattributed View:**
- Orphan artifacts without parent epic/project
- Helps identify work needing manual categorization

**Report Generation:**
- Date range picker
- Preview before export
- Download JSON/CSV

---

## Implementation Phases

Each sub-phase is a single `amelia start` workflow with focused scope and TDD approach.

**Critical path:** Workflow tracking (14b) is foundational — it must be implemented early because accurate hours estimation depends on workflow execution data.

### Phase 14a: Data Models & Persistence
- Add `amelia/capex/models.py` with `Initiative`, `Attribution`, `CapexReport`, `WorkflowExecution`
- Add `amelia/capex/store.py` with SQLite CRUD operations for all models
- Add Alembic migration for `initiatives`, `attributions`, and `workflow_executions` tables
- **Acceptance:** `uv run pytest tests/unit/capex/test_models.py` passes

### Phase 14b: Workflow Tracking (Critical Path)
- Modify `orchestrator.py` to create `WorkflowExecution` record at workflow start
- Update record with `completed_at`, `status`, `pr_number` on completion/failure
- Track `agents_invoked` as each agent runs
- **Acceptance:** `amelia start` creates/updates workflow_execution record; verify with `uv run pytest tests/integration/capex/test_workflow_tracking.py`

### Phase 14c: Initiative Tracker Protocol
- Add `InitiativeTracker` protocol to `amelia/core/types.py`
- Implement `JiraInitiativeTracker` — fetch epics, resolve parent for issue
- Implement `GitHubInitiativeTracker` — fetch projects, resolve membership
- Wire initiative resolution into orchestrator (store `initiative_id` in workflow execution)
- **Acceptance:** Integration tests against mock tracker data pass

### Phase 14d: Hours Estimation
- Add `amelia/capex/estimator.py` with workflow-first `estimate_hours()` function
- Add `business_hours_between()` for PR lifecycle fallback
- Handle edge cases: failed workflows (50% credit), cancelled (0%), no workflow data (fallback)
- **Acceptance:** Unit tests cover workflow sum, partial credit, and PR lifecycle fallback scenarios

### Phase 14e: Attribution Engine
- Add `amelia/capex/attributor.py` — resolve PR → issue → initiative chain
- Link attributions to `workflow_ids` for full traceability
- Track `hours_source` ("workflow" vs "pr_lifecycle") in attribution
- Generate audit trail reasoning for each attribution
- **Acceptance:** Given mock PR/workflow data, attributions match expected output with correct hours_source

### Phase 14f: CLI Scan Command
- Add `amelia capex scan --since --until` command
- Fetch PRs from GitHub, look up associated workflow executions, resolve attributions
- Historical PRs without workflow data use PR lifecycle fallback
- **Acceptance:** E2E test with mock GitHub API returns expected attributions

### Phase 14g: CLI Report Commands
- Add `amelia capex initiatives`, `report`, `show`, `unattributed`
- JSON/CSV/table output formatters
- Show `hours_source` breakdown in reports (workflow vs fallback)
- **Acceptance:** CLI outputs match snapshot fixtures

### Phase 14h: Dashboard API
- Add `amelia/server/routers/capex.py` with REST endpoints
- Include workflow execution detail in attribution responses
- **Acceptance:** OpenAPI spec matches, integration tests pass

### Phase 14i: Dashboard UI
- Add React pages: initiative list, detail, unattributed, report
- Show workflow execution timeline in attribution detail view
- **Acceptance:** Manual test plan verifies UI flows

---

## References

- Capitalization Tracking Spec — Original domain knowledge document
- CONTRIBUTING.md — GitHub organization patterns (Projects, Epics)
