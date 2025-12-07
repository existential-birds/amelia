# Capitalization Tracking Design

*Brainstorming session: 2025-12-07*

---

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
| Hours estimation | PR lifecycle (open → merge) | Only reliable signal available; no JIRA time tracking or story points |
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
    hours: float                     # Business hours (PR open→merge)
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

SQLite tables matching these models, same database as dashboard.

---

## Architecture

### Module Structure

```
amelia/
├── agents/           # Existing: Architect, Developer, Reviewer
├── trackers/         # Existing: JIRA, GitHub issue fetching
├── capex/            # NEW
│   ├── __init__.py
│   ├── models.py     # Initiative, Attribution, CapexReport
│   ├── tracker.py    # InitiativeTracker protocol + implementations
│   ├── estimator.py  # Hours estimation from PR lifecycle
│   ├── attributor.py # Core attribution logic
│   ├── reporter.py   # Report generation (JSON, CSV)
│   └── store.py      # SQLite persistence
├── core/
│   └── orchestrator.py  # Modified: emit attributions during workflow
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

When `amelia start` runs, the orchestrator emits `Attribution` records as PRs are created/merged. The workflow state already tracks issue context — extend it to include initiative.

**No new agents.** Attribution is deterministic (hierarchy lookup + PR timestamps), not LLM-driven.

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

### PR Lifecycle Calculation

```python
def estimate_hours(pr: PullRequest) -> tuple[float, list[str]]:
    """Estimate engineering hours from PR lifecycle.

    Returns (hours, reasoning) tuple for audit trail.
    """
    reasoning = []

    opened = pr.created_at
    merged = pr.merged_at

    if not merged:
        reasoning.append(f"PR not merged, using current time")
        merged = datetime.now(UTC)

    hours = business_hours_between(opened, merged)
    reasoning.append(f"PR open: {opened.isoformat()}")
    reasoning.append(f"PR merged: {merged.isoformat()}")
    reasoning.append(f"Business hours: {hours:.1f}")

    return hours, reasoning
```

### Business Hours Rules

- Weekdays only (Mon-Fri)
- 8-hour workday (configurable)
- Excludes nights (e.g., PR opened Friday 5pm, merged Monday 9am = 0 hours over weekend)

### Audit Trail Example

```json
{
  "artifact_id": "PR-1293",
  "initiative_id": "INIT-001",
  "hours": 12.5,
  "reasoning": [
    "Issue PROJ-456 parent epic: INIT-001",
    "PR linked to issue: PROJ-456",
    "PR open: 2025-01-10T09:00:00Z",
    "PR merged: 2025-01-11T14:30:00Z",
    "Business hours: 12.5"
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

### Phase 14a: Data Models & Persistence
- Add `amelia/capex/models.py` with `Initiative`, `Attribution`, `CapexReport`
- Add `amelia/capex/store.py` with SQLite CRUD operations
- Add Alembic migration for `initiatives` and `attributions` tables
- **Acceptance:** `uv run pytest tests/unit/capex/test_models.py` passes

### Phase 14b: Initiative Tracker Protocol
- Add `InitiativeTracker` protocol to `amelia/core/types.py`
- Implement `JiraInitiativeTracker` — fetch epics, resolve parent for issue
- Implement `GitHubInitiativeTracker` — fetch projects, resolve membership
- **Acceptance:** Integration tests against mock tracker data pass

### Phase 14c: Hours Estimation
- Add `amelia/capex/estimator.py` with `business_hours_between()` and `estimate_hours()`
- Handle edge cases: unmerged PRs, weekend spans, holidays (configurable)
- **Acceptance:** Unit tests cover weekday/weekend/overnight scenarios

### Phase 14d: Attribution Engine
- Add `amelia/capex/attributor.py` — resolve PR → issue → initiative chain
- Generate audit trail reasoning for each attribution
- Persist attributions via store
- **Acceptance:** Given mock PR/issue data, attributions match expected output

### Phase 14e: CLI Scan Command
- Add `amelia capex scan --since --until` command
- Fetch PRs from GitHub, resolve attributions, persist
- **Acceptance:** E2E test with mock GitHub API returns expected attributions

### Phase 14f: CLI Report Commands
- Add `amelia capex initiatives`, `report`, `show`, `unattributed`
- JSON/CSV/table output formatters
- **Acceptance:** CLI outputs match snapshot fixtures

### Phase 14g: Real-time Orchestrator Hook
- Modify `orchestrator.py` to capture initiative context at workflow start
- Emit attribution when PR merges
- **Acceptance:** `amelia start` on test issue creates attribution record

### Phase 14h: Dashboard API
- Add `amelia/server/routers/capex.py` with REST endpoints
- **Acceptance:** OpenAPI spec matches, integration tests pass

### Phase 14i: Dashboard UI
- Add React pages: initiative list, detail, unattributed, report
- **Acceptance:** Manual test plan verifies UI flows

---

## References

- [Capitalization Tracking Spec](capex_tracking.md) — Original domain knowledge document
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — GitHub organization patterns (Projects, Epics)
