# Capitalization Tracking Design

> **Created by:** hey-amelia bot with Claude Opus 4.5
> **Updated by:** technical finance systems architect (R&D capitalization; Series B–D scale)
> **Scope note:** This document describes a **deterministic**, **on-demand**, **SQLite-backed** system to support capitalization reporting and audit trails. It is not accounting or legal advice; accounting conclusions remain the responsibility of management and their advisors.

## Overview

A system that attributes engineering work to **capitalizable initiatives** for financial reporting. Integrates with Amelia’s existing tracker abstraction to map PRs and issues to initiatives (JIRA Epics or GitHub Projects).

### Goals

1. **Real-time attribution** — When Amelia orchestrates work, automatically capture initiative context and log hours/artifacts
2. **Retrospective analysis** — On-demand CLI scan that processes historical PRs/issues and attributes them to initiatives
3. **Auditable reports** — Finance-ready output with full traceability from hours to source artifacts, plus integrity controls suitable for ICFR/SOX readiness

### Non-Goals

* Dollar calculations (finance applies their own labor rates)
* Document ingestion (initiatives come from tracker, not Google Docs/Notion)
* Background scheduling (on-demand only)
* Fuzzy/semantic matching (hierarchical mapping only)
* LLM-driven attribution (deterministic mapping only)

---

## Design Decisions

| Decision               | Choice                                         | Rationale                                                                                                                                                                                                                           |
| ---------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Initiative source      | JIRA Epics / GitHub Projects                   | Tracker-native, follows existing discipline per CONTRIBUTING.md                                                                                                                                                                     |
| Mapping strategy       | Hierarchical only                              | Issue’s parent epic/project = initiative. Enforces good hygiene.                                                                                                                                                                    |
| Hours estimation       | Workflow execution sum, PR lifecycle fallback  | Measures actual work time, not idle time; PR fallback for manual/historical work                                                                                                                                                    |
| Workflow persistence   | SQLite table                                   | Required for accurate hours and full audit trail                                                                                                                                                                                    |
| Failed workflow credit | 50% of elapsed time                            | Work was done even if not completed; configurable                                                                                                                                                                                   |
| Engineer weighting     | Flat rate                                      | Finance applies their own blended rates; reduces config overhead                                                                                                                                                                    |
| Output formats         | CLI + JSON/CSV, dashboard later                | CLI for automation, dashboard for exploration                                                                                                                                                                                       |
| Retrospective trigger  | On-demand CLI                                  | Avoids background job complexity                                                                                                                                                                                                    |
| Audit trail            | Append-only evidence + deterministic reasoning | ICFR/SOX auditability requires traceability and evidence integrity (Source: [https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201](https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201)) |

---

## Capitalization Policy Mapping

This section describes how the system **maps** engineering activity into finance-friendly classifications aligned to US GAAP (ASC 350-40) and IFRS (IAS 38). It does **not** determine accounting treatment on its own.

### Reference frameworks (for mapping only)

* **US GAAP — ASC 350-40 (Internal-Use Software)**: Internal-use software development/implementation guidance; recent updates modernize operability in iterative methods and adjust capitalization thresholds (Source: [https://www.fasb.org/news-and-meetings/in-the-news/fasb-issues-standard-that-makes-targeted-improvements-to-internal-use-software-guidance-423046](https://www.fasb.org/news-and-meetings/in-the-news/fasb-issues-standard-that-makes-targeted-improvements-to-internal-use-software-guidance-423046)) (Source: [https://www.fasb.org/page/PageContent?pageId=%2Fprojects%2Frecently-completed-projects%2Faccounting-for-and-disclosure-of-software-costs.html](https://www.fasb.org/page/PageContent?pageId=%2Fprojects%2Frecently-completed-projects%2Faccounting-for-and-disclosure-of-software-costs.html))
* **ASU 2018-15 (Cloud computing implementation costs)**: Aligns treatment of certain cloud implementation costs with internal-use software guidance when the hosting arrangement is a service contract (Source: [https://storage.fasb.org/ASU%202018-15.pdf](https://storage.fasb.org/ASU%202018-15.pdf))
* **IFRS — IAS 38 (Intangible Assets)**: Research vs development distinction; development costs may be capitalized only when criteria are met (Source: [https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-38-intangible-assets.pdf](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-38-intangible-assets.pdf))

### System terms for “capitalizable vs non-capitalizable”

The system classifies at the **initiative** level, using tracker-native metadata. This preserves deterministic attribution and hierarchical-only mapping.

**Initiative classification fields (deterministic):**

* `initiative.capitalization_treatment`: `capitalizable` | `non_capitalizable` | `mixed` | `unknown`
* `initiative.capitalization_basis`: `ASC_350_40_internal_use` | `ASC_350_40_cloud_impl` | `IAS_38_development` | `IAS_38_research` | `other` | `unknown`
* `initiative.policy_version`: string (e.g., `2025Q4`)
* `initiative.policy_tags`: list[str] (controlled vocabulary; see “Policy configuration”)

**How capitalizable work is represented**

* Work is **eligible** only when the parent initiative’s `capitalization_treatment` is `capitalizable` (or `mixed`, with sub-initiative segmentation via tracker hierarchy if available).
* Non-capitalizable work remains attributable (for completeness) but is reported separately.

> Important: For ASC 350-40 operability in iterative development, the system must capture **evidence markers** for “authorization / commencement” and “ready for intended use” (or equivalent). Recent FASB updates emphasize operability for nonlinear development and require clear criteria for when capitalization begins (Source: [https://www.fasb.org/news-and-meetings/in-the-news/fasb-issues-standard-that-makes-targeted-improvements-to-internal-use-software-guidance-423046](https://www.fasb.org/news-and-meetings/in-the-news/fasb-issues-standard-that-makes-targeted-improvements-to-internal-use-software-guidance-423046)). IAS 38 requires development criteria (technical feasibility, intent, ability, etc.) to be met before capitalization (Source: [https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-38-intangible-assets.pdf](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-38-intangible-assets.pdf)).

### Evidence markers captured by the system

The system records evidence as **immutable events** tied to initiatives and periods, not as free-form narrative.

**Authorization / Commencement evidence (system-level representation)**

* `initiative.authorization_event_id`: FK to `capex_events.id`
* Evidence event types:

  * `INITIATIVE_AUTHORIZED` (management authorization and funding commitment)
  * `INITIATIVE_COMMENCED` (capitalization start trigger per policy mapping)
* Evidence payload requires:

  * `authorized_by` (user id)
  * `authorized_at` (timestamp)
  * `authorization_source_type`: `tracker_field` | `tracker_label` | `manual_attestation`
  * `authorization_source_ref`: URL or key (e.g., JIRA epic field change URL, GitHub project audit link, or internal ticket URL)
  * `policy_basis`: enum from `capitalization_basis`
  * `notes` (short; no accounting conclusions)

**Ready-for-intended-use evidence**

* `initiative.ready_for_use_event_id`: FK to `capex_events.id`
* Evidence event types:

  * `INITIATIVE_READY_FOR_USE`
  * `INITIATIVE_ABANDONED` (for impairment/abandonment flagging; reporting only)
* Evidence payload requires:

  * `declared_by` (user id)
  * `declared_at` (timestamp)
  * `evidence_refs`: list[URL] (release tag, deployment record, acceptance issue, etc.)
  * `scope_summary` (short)

---

## SOX / ICFR Audit Trail Completeness

### Control objectives (what we must prove)

These are phrased as ICFR-aligned objectives; auditors typically evaluate whether controls are designed and operating effectively to prevent/detect material misstatement (Source: [https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201](https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201)) and management must assess ICFR under SOX Section 404 (Source: [https://www.sec.gov/rules-regulations/2003/03/managements-report-internal-control-over-financial-reporting-certification-disclosure-exchange-act](https://www.sec.gov/rules-regulations/2003/03/managements-report-internal-control-over-financial-reporting-certification-disclosure-exchange-act)).

| Control Objective                              | Risk Addressed                                              | System Evidence Produced (SQLite + CLI)                                                   |
| ---------------------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| CO-1: Completeness of population               | Missing eligible engineering activity from capex population | Deterministic ingestion logs + exception list of unattributed artifacts                   |
| CO-2: Accuracy of attribution                  | Wrong initiative mapping                                    | Immutable reasoning chain from artifact → issue → parent initiative (hierarchical lookup) |
| CO-3: Authorization & capitalization start/end | Capitalizing before authorized / after ready-for-use        | Evidence events for authorization/commencement and ready-for-use                          |
| CO-4: Change control / audit trail             | Undocumented edits to initiatives or overrides              | Append-only mutation log with before/after hashes + approvals                             |
| CO-5: Evidence integrity                       | Tampering with records or exports                           | Hash-chained event log + signed export manifest + reproducible report inputs              |

### Append-only patterns in SQLite (no background jobs)

We introduce a capex-specific event ledger that complements Amelia’s existing server-side append-only event log pattern (events table) described in `overview.md` .

**New tables (in `amelia/capex/store.py` migrations)**

#### `capex_events` (append-only)

Captures all capex-relevant events, including evidence markers and override approvals.

Fields:

* `id` TEXT PRIMARY KEY (UUIDv7 preferred for monotonicity; otherwise UUID + created_at index)
* `created_at` TIMESTAMP NOT NULL
* `event_type` TEXT NOT NULL (enum)
* `actor_user_id` TEXT NOT NULL
* `actor_role` TEXT NOT NULL (`engineer` | `finance` | `admin`)
* `entity_type` TEXT NOT NULL (`initiative` | `workflow_execution` | `attribution` | `report_run` | `export_bundle`)
* `entity_id` TEXT NOT NULL
* `payload_json` TEXT NOT NULL (canonical JSON serialization)
* `prev_event_hash` TEXT NULL
* `event_hash` TEXT NOT NULL
* `correlation_id` TEXT NULL (ties to workflow_id/report_run_id)
* `source_ip` TEXT NULL (if available from server context)
* `source_client` TEXT NOT NULL (`cli` | `dashboard`)

Hashing:

* `event_hash = sha256(prev_event_hash || created_at || event_type || actor_user_id || entity_type || entity_id || payload_json)`
* Enforced by: store layer computes hash at insert time; DB enforces `NOT NULL` and indexed uniqueness on `(event_hash)`

#### `capex_mutations` (append-only change log for editable entities)

All “edits” are represented as new immutable mutation records.

Fields:

* `id` TEXT PRIMARY KEY
* `created_at` TIMESTAMP NOT NULL
* `actor_user_id` TEXT NOT NULL
* `actor_role` TEXT NOT NULL
* `entity_type` TEXT NOT NULL (`initiative` | `attribution`)
* `entity_id` TEXT NOT NULL
* `mutation_type` TEXT NOT NULL (`CREATE` | `UPDATE` | `VOID` | `RESTATE`)
* `before_json` TEXT NULL
* `after_json` TEXT NOT NULL
* `reason_code` TEXT NOT NULL (controlled vocabulary)
* `reason_text` TEXT NULL
* `approval_id` TEXT NULL (FK to `capex_approvals.id`)
* `prev_mutation_hash` TEXT NULL
* `mutation_hash` TEXT NOT NULL

#### `capex_approvals` (segregation of duties support)

Fields:

* `id` TEXT PRIMARY KEY
* `requested_at` TIMESTAMP NOT NULL
* `requested_by_user_id` TEXT NOT NULL
* `requested_by_role` TEXT NOT NULL
* `approval_status` TEXT NOT NULL (`pending` | `approved` | `rejected`)
* `decided_at` TIMESTAMP NULL
* `decided_by_user_id` TEXT NULL
* `decided_by_role` TEXT NULL
* `approval_scope` TEXT NOT NULL (`override_hours` | `override_initiative` | `policy_change` | `period_lock_breakglass`)
* `approval_reason_code` TEXT NOT NULL
* `approval_notes` TEXT NULL

#### `capex_period_locks` (prevents backdating changes)

Fields:

* `period_id` TEXT PRIMARY KEY (e.g., `2025Q1`)
* `period_start` DATE NOT NULL
* `period_end` DATE NOT NULL
* `locked_at` TIMESTAMP NOT NULL
* `locked_by_user_id` TEXT NOT NULL
* `locked_by_role` TEXT NOT NULL
* `lock_reason` TEXT NOT NULL
* `lock_hash` TEXT NOT NULL (hash of report inputs + export manifest hash)

Lock semantics:

* When locked, any mutation affecting attributions within the period requires `admin` breakglass approval.

---

## Access Control and Change Management

### Roles and permissions (minimal, finance-usable)

| Operation                                   |     Engineer |     Finance | Admin |
| ------------------------------------------- | -----------: | ----------: | ----: |
| Run scans/reports/exports                   |            ✅ |           ✅ |     ✅ |
| Mark initiative policy fields               |            ❌ |           ✅ |     ✅ |
| Record authorization/ready-for-use evidence | ❌ (optional) |           ✅ |     ✅ |
| Create manual overrides (draft)             |  ✅ (request) | ✅ (request) |     ✅ |
| Approve overrides (SoD)                     |            ❌ |           ✅ |     ✅ |
| Breakglass edit in locked period            |            ❌ |           ❌ |     ✅ |

Segregation of duties (SoD) principle: the same user should not both request and approve certain sensitive changes (commonly required under ICFR programs; the system enforces SoD at the workflow level for approvals). This aligns to risk-based ICFR expectations (Source: [https://www.sec.gov/rules-regulations/2003/03/managements-report-internal-control-over-financial-reporting-certification-disclosure-exchange-act](https://www.sec.gov/rules-regulations/2003/03/managements-report-internal-control-over-financial-reporting-certification-disclosure-exchange-act)) (Source: [https://kpmg.com/kpmg-us/content/dam/kpmg/frv/pdf/2023/handbook-internal-controls-over-financial-reporting.pdf](https://kpmg.com/kpmg-us/content/dam/kpmg/frv/pdf/2023/handbook-internal-controls-over-financial-reporting.pdf)).

### Write-once vs editable (and how edits are tracked)

**Write-once (immutable)**

* `workflow_executions` records (status transitions only; no overwriting—each status change also emits a `capex_events` entry)
* `capex_events`, `capex_mutations`, `capex_approvals` (append-only)

**Editable via mutation log (no in-place overwrite)**

* `initiatives` (cached tracker metadata + policy fields)
* `attributions` (only specific fields can be overridden; see below)

System rule: tables `initiatives` and `attributions` store the **current projection** (latest state), but every change must have a corresponding append-only `capex_mutations` record and a `capex_events` entry. Auditors trace from the current row back through the chain of mutations.

---

## Quarter-End Evidence Package Outputs (finance-facing)

Finance typically needs a reproducible, reviewable **package** for quarter close: roll-forward totals, drill-down detail, exception list, and evidence references, with integrity controls. (Based on common practice.)

### Evidence package: `amelia capex export --quarter Q1-2025`

Output: a folder (or zip) containing JSON/CSV plus a manifest.

**Bundle structure**

```
capex_export_Q1-2025/
  manifest.json
  summary_by_initiative.csv
  detail_attributions.csv
  workflow_executions.csv
  exceptions_unattributed.csv
  policy_snapshot.json
  evidence_events.json
  integrity/
    db_snapshot_info.json
    hashes.json
    signature.sig
```

**Manifest fields (`manifest.json`)**

* `bundle_id` (UUID)
* `generated_at`
* `generated_by_user_id`
* `period_id`, `period_start`, `period_end`
* `db_file_fingerprint` (sha256 of SQLite file bytes at export time)
* `included_files`: list of `{path, sha256, row_count}`
* `report_parameters`: JSON (tracker(s), filters, failed_credit_factor, business_hours_config, etc.)
* `lock_status`: `locked`|`unlocked` plus `period_lock_hash` if locked
* `software_version`: Amelia git SHA + semantic version
* `signature_public_key_id` (local key id)

**Roll-up totals (`summary_by_initiative.csv`)**
Exact columns:

* `period_id`
* `initiative_id`
* `initiative_name`
* `tracker`
* `capitalization_treatment`
* `capitalization_basis`
* `authorized_at` (from evidence event)
* `ready_for_use_at` (from evidence event, if present)
* `total_hours`
* `capitalizable_hours`
* `non_capitalizable_hours`
* `hours_source_workflow`
* `hours_source_pr_lifecycle`
* `hours_source_manual`
* `exception_count` (unattributed + overrides)

**Drill-down (`detail_attributions.csv`)**
Exact columns:

* `artifact_type`
* `artifact_id`
* `artifact_url`
* `issue_id`
* `initiative_id`
* `engineers`
* `hours`
* `hours_source`
* `workflow_ids`
* `pr_created_at`
* `pr_merged_at`
* `attribution_method` (`realtime`|`retrospective`)
* `created_at`
* `override_flag` (bool)
* `override_approval_id` (nullable)
* `reasoning_hash` (sha256 of reasoning array canonical JSON)

**Workflow evidence (`workflow_executions.csv`)**
Exact columns:

* `workflow_id`
* `issue_id`
* `initiative_id`
* `started_at`
* `completed_at`
* `status`
* `duration_hours`
* `failed_credit_applied` (bool)
* `agents_invoked`
* `pr_number`
* `worktree_path` (optional; may be sensitive—configurable)

**Exceptions (`exceptions_unattributed.csv`)**
Exact columns:

* `artifact_type`
* `artifact_id`
* `artifact_url`
* `issue_id`
* `detected_reason` (`no_parent_initiative` | `missing_issue_link` | `tracker_unreachable` | `other`)
* `detected_at`
* `suggested_action` (`fix_hierarchy_in_tracker` | `manual_override_request`)

### Auditor traceability (end-to-end)

An auditor should be able to sample from roll-up to raw evidence:

1. **Report line** (`summary_by_initiative.csv`) → pick initiative
2. **Drill down** (`detail_attributions.csv`) → pick a PR/issue
3. **Attribution record** (`attributions` table) → see deterministic mapping + reasoning + workflow ids
4. **Workflow evidence** (`workflow_executions.csv` + `workflow_executions` table) → see start/end/status; reconcile duration
5. **Evidence markers** (`evidence_events.json` + `capex_events`) → see authorization/ready-for-use attestations and references
6. **Integrity** (`manifest.json` + hashes/signature + hash-chained `capex_events`) → verify records were not altered post-export

---

## Time Tracking Pitfalls Mitigation (audit-risk reduction)

Time-based attribution commonly fails when engineering activity does not align cleanly to initiatives or when edge cases inflate/deflate hours. This section defines deterministic mitigations compatible with constraints. Some pitfalls are widely observed in agile capitalization programs (Source: [https://agilityhealthradar.com/wp-content/uploads/2017/05/The-top-10-pitfalls-of-agile-capitalization-Highlight.pdf](https://agilityhealthradar.com/wp-content/uploads/2017/05/The-top-10-pitfalls-of-agile-capitalization-Highlight.pdf)).

### Pitfall: Reopened PRs / iterative cycles

**Risk:** double-counting or counting stale time.

Mitigation rules:

* If a PR is reopened, PR lifecycle fallback must use **sum of active windows**, not a single open→merge span.
* Track PR state transitions deterministically:

  * Store `pr_timeline_json` (canonical list of `{state, at}` events) on the attribution when `hours_source="pr_lifecycle"`.

Fields to capture:

* In `Attribution`:

  * `pr_timeline_json: str | None`
  * `pr_active_hours: float | None`
* Produced by:

  * `amelia capex scan` when PR lifecycle fallback is used.

### Pitfall: Partial work / context switching

**Risk:** elapsed workflow time may include breaks; PR lifecycle may include idle.

Mitigation rules:

* Workflow-based hours remain **elapsed time** (no “activity detection” introduced; would add complexity and bias).
* Provide a **manual override request** mechanism with approvals and strict logging (see below).
* Require reason codes to prevent ad hoc edits.

### Pitfall: “Failed workflow credit” governance

The 50% credit policy is retained, but must be governed.

Why 50%:

* Captures real effort on runs that failed late, while avoiding full credit in ambiguous outcomes. (Based on common practice.)

Controls:

* Make the factor explicit in report parameters and exports.
* Allow override only via approval workflow.

Fields:

* In `WorkflowExecution`:

  * `failed_credit_factor_applied: float` (0.0, 0.5, or overridden)
* In `capex_events` payload for `WORKFLOW_FAILED_CREDIT_APPLIED`:

  * `workflow_id`, `base_duration_hours`, `factor`, `credited_hours`, `policy_version`

CLI:

* `amelia capex policy show` (shows current factor)
* `amelia capex override request --workflow <id> --failed-credit-factor 0.25 --reason-code <...>`
* `amelia capex override approve <approval_id>` (finance/admin only)

### Manual overrides workflow (allowed, controlled)

Overrides are permitted only for:

* `hours` adjustment when PR lifecycle is clearly overstated/understated
* initiative reassignment when tracker hierarchy was wrong at the time and later corrected

Override model:

* Add to `Attribution`:

  * `override_flag: bool`
  * `override_type: "hours" | "initiative" | None`
  * `override_approval_id: str | None`
  * `override_reason_code: str | None`
  * `override_notes: str | None`
  * `original_hours: float | None`
  * `original_initiative_id: str | None`

Storage:

* Current projection updates `attributions` row
* Every override creates:

  * `capex_approvals` record (pending → approved/rejected)
  * `capex_mutations` record with before/after JSON and hash chain
  * `capex_events` entries for request and decision

---

## Data Retention and Evidence Integrity

### Retention period recommendations

* **Minimum 7 years** for audit-relevant evidence is a common baseline in SOX contexts; auditors are required to retain certain audit records for seven years under SEC rules applicable to accountants (Source: [https://www.sec.gov/rules-regulations/2003/01/retention-records-relevant-audits-reviews](https://www.sec.gov/rules-regulations/2003/01/retention-records-relevant-audits-reviews)) (Source: [https://www.sec.gov/news/press/2003-11.htm](https://www.sec.gov/news/press/2003-11.htm)).
* For company operational systems, retention requirements vary by policy and legal counsel. **Recommendation: retain capex evidence packages and supporting event logs for 7 years**. (Based on common practice; align to your corporate retention policy.)

Implementation (no background jobs):

* Provide `amelia capex export` to produce immutable evidence packages suitable for archive storage.
* Provide `amelia capex verify-export <path>` to validate hashes/signatures offline.
* Optional `amelia capex purge --before <date>` remains **manual** and refuses to purge if any locked periods would be affected (admin only).

### Integrity measures feasible locally/offline

1. **Hash-chained append-only event log** (`capex_events`)

2. **Hash-chained mutation log** (`capex_mutations`)

3. **Signed exports**: manifest + all included file hashes are signed with a locally managed keypair:

   * `signature.sig = sign(private_key, sha256(manifest.json))`
   * Store public key id in manifest

4. **Reproducibility**:

   * Manifest includes report parameters and SQLite fingerprint so the same period can be regenerated and compared.

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

    # Deterministic policy metadata (finance-owned)
    capitalization_treatment: Literal["capitalizable", "non_capitalizable", "mixed", "unknown"]
    capitalization_basis: Literal[
        "ASC_350_40_internal_use",
        "ASC_350_40_cloud_impl",
        "IAS_38_development",
        "IAS_38_research",
        "other",
        "unknown",
    ]
    policy_version: str              # e.g., "2025Q4"
    policy_tags: list[str]           # controlled vocabulary (org-defined)

    # Evidence links (event IDs)
    authorization_event_id: str | None
    commencement_event_id: str | None
    ready_for_use_event_id: str | None

    start_date: date | None          # Optional time bounds (reporting convenience)
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

    # Governance fields
    failed_credit_factor_applied: float | None  # e.g., 0.5 if failed and credited

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
    issue_id: str | None             # Resolved issue (if applicable)

    initiative_id: str               # Parent epic/project
    engineers: list[str]             # GitHub usernames involved
    hours: float                     # Estimated hours

    hours_source: Literal["workflow", "pr_lifecycle", "manual"]  # How hours were calculated
    workflow_ids: list[str]          # References to WorkflowExecution records
    method: Literal["realtime", "retrospective"]

    reasoning: list[str]             # Deterministic audit trail entries
    reasoning_hash: str              # sha256(canonical_json(reasoning))

    # PR lifecycle evidence (only when hours_source == "pr_lifecycle")
    pr_timeline_json: str | None

    # Overrides (controlled)
    override_flag: bool = False
    override_type: Literal["hours", "initiative"] | None = None
    override_approval_id: str | None = None
    override_reason_code: str | None = None
    override_notes: str | None = None
    original_hours: float | None = None
    original_initiative_id: str | None = None

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

    # Reproducibility + integrity
    report_run_id: str               # UUID
    parameters_hash: str             # sha256(canonical_json(report_parameters))
```

### Persistence

SQLite tables matching these models, same database as dashboard:

* `initiatives` — cached initiative metadata from tracker + finance policy fields
* `workflow_executions` — every `amelia start` run with timestamps
* `attributions` — PR/issue/commit to initiative mappings with hours
* `capex_events` — append-only ledger for evidence and sensitive actions
* `capex_mutations` — append-only log of any edits to initiatives/attributions
* `capex_approvals` — approvals for overrides/policy changes
* `capex_period_locks` — prevents unapproved edits to closed periods

---

## Architecture

### Module Structure

```
amelia/
├── agents/           # Existing: Architect, Developer, Reviewer
├── trackers/         # Existing: JIRA, GitHub issue fetching
├── capex/            # NEW
│   ├── __init__.py
│   ├── models.py     # Initiative, Attribution, CapexReport, WorkflowExecution, Approval, Event, Mutation
│   ├── tracker.py    # InitiativeTracker protocol + implementations
│   ├── estimator.py  # Workflow-based hours estimation with PR fallback
│   ├── attributor.py # Core deterministic attribution logic
│   ├── reporter.py   # Report generation (JSON, CSV) + evidence bundle export
│   ├── policy.py     # Controlled vocab, policy snapshots, validation
│   └── store.py      # SQLite persistence + append-only logs + period locks
├── core/
│   └── orchestrator.py  # Modified: persist WorkflowExecution records + capex events
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

* `JiraTracker` implements via Epic parent lookup
* `GitHubTracker` implements via Project membership lookup

### Orchestrator Integration

When `amelia start` runs, the orchestrator manages `WorkflowExecution` lifecycle:

1. **Workflow start:** Create `WorkflowExecution` record with `status="running"`
2. **Initiative resolution:** Look up parent epic/project, store `initiative_id` in execution record
3. **Agent tracking:** Append to `agents_invoked` as each agent runs
4. **Workflow completion:** Update record with `completed_at`, final `status`, `pr_number`
5. **Capex event emission:** For each lifecycle transition, insert a `capex_events` record with a correlation id = workflow id

This aligns with Amelia’s existing event-driven observability and SQLite-backed event storage described in `overview.md` .

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
amelia capex scan --quarter Q1-2025

# Generate report (reproducible report_run_id + parameters_hash)
amelia capex report --quarter Q1-2025 --format json > q1-capex.json
amelia capex report --quarter Q1-2025 --format csv > q1-capex.csv
amelia capex report --quarter Q1-2025 --format table

# Evidence package export (finance-facing)
amelia capex export --quarter Q1-2025 --out ./capex_export_Q1-2025
amelia capex verify-export ./capex_export_Q1-2025

# Review unattributed artifacts (orphans without parent epic/project)
amelia capex unattributed --quarter Q1-2025

# Show attribution details for a specific artifact
amelia capex show PR-1293
amelia capex show PROJ-123

# Policy + evidence markers (finance/admin)
amelia capex policy show
amelia capex initiative set-policy INIT-001 --treatment capitalizable --basis ASC_350_40_internal_use --policy-version 2025Q4 --tag "feature_dev"
amelia capex initiative attest INIT-001 --event INITIATIVE_AUTHORIZED --source-ref "<url>" --notes "<short>"
amelia capex initiative attest INIT-001 --event INITIATIVE_READY_FOR_USE --evidence-ref "<url>"

# Overrides with approvals (request → approve)
amelia capex override request --artifact PR-1293 --hours 6.0 --reason-code PR_IDLE_TIME
amelia capex override approve <approval_id>
amelia capex override reject <approval_id>

# Period lock (end of close)
amelia capex period lock --quarter Q1-2025 --reason "Close completed"
```

**Real-time attribution:** No new command — happens automatically during `amelia start`.

**Configuration:** Uses existing `settings.amelia.yaml` profile for tracker credentials.

---

## Hours Estimation

### Estimation Hierarchy

Hours are calculated using a priority hierarchy:

1. **Primary: Workflow execution sum** — Actual `amelia start` run times
2. **Fallback: PR lifecycle** — Business hours between PR active windows (open/reopen) and merge (for manual work or historical PRs)

### Workflow-Based Estimation

```python
def estimate_hours(
    pr: PullRequest,
    workflows: list[WorkflowExecution],
    failed_credit_factor: float = 0.5,
) -> tuple[float, Literal["workflow", "pr_lifecycle"], list[str]]:
    """Estimate engineering hours with source tracking.

    Returns (hours, source, reasoning) tuple for audit trail.
    """
    reasoning = []

    if workflows:
        completed = [w for w in workflows if w.status == "completed"]
        failed = [w for w in workflows if w.status == "failed"]

        hours = sum(w.duration_hours for w in completed)
        hours += sum(w.duration_hours * failed_credit_factor for w in failed)

        reasoning.append(f"Found {len(workflows)} workflow executions")
        for w in workflows:
            if w.status == "completed":
                credit = w.duration_hours
            elif w.status == "failed":
                credit = w.duration_hours * failed_credit_factor
            else:
                credit = 0.0
            reasoning.append(f"  {w.id[:8]}: {w.status}, {credit:.2f}h")
        reasoning.append(f"Total workflow hours: {hours:.2f}")

        return hours, "workflow", reasoning
    else:
        hours, timeline = business_hours_from_pr_timeline(pr.timeline)
        reasoning.append("No workflow data found")
        reasoning.append(f"PR timeline windows: {len(timeline)}")
        reasoning.append(f"Business hours (fallback): {hours:.2f}")

        return hours, "pr_lifecycle", reasoning
```

### Workflow Hours Rules

* **Actual elapsed time** — No business hours filtering; measures real work duration
* **Completed workflows:** 100% of elapsed time
* **Failed workflows:** 50% of elapsed time (configurable; governed)
* **Cancelled workflows:** 0% (user explicitly stopped)

### PR Lifecycle Fallback Rules

Used only when no workflow data exists (manual work or pre-capex PRs):

* Weekdays only (Mon–Fri)
* 8-hour workday (configurable)
* Uses PR state transitions (open/reopen/close/merge) to avoid overstating reopened PR time

---

## Dashboard View (Later Phase)

Unchanged conceptually. (All new audit features are CLI/export first; dashboard can surface the same projections from SQLite.)

---

## Implementation Phases

Each sub-phase is a single `amelia start` workflow with focused scope and TDD approach.

**Critical path:** Workflow tracking (14b) is foundational — it must be implemented early because accurate hours estimation depends on workflow execution data.

### Phase 14a: Data Models & Persistence

* Extend `amelia/capex/models.py` with:

  * policy fields on `Initiative`
  * integrity fields on `Attribution` (`reasoning_hash`, overrides)
  * new models: `CapexEvent`, `CapexMutation`, `CapexApproval`, `CapexPeriodLock`
* Extend `amelia/capex/store.py` with:

  * append-only inserts for `capex_events`, `capex_mutations`, `capex_approvals`
  * lock checks for `capex_period_locks`
* Add migration for new tables
* **Acceptance:** unit tests validate hash chaining + immutability constraints

### Phase 14b: Workflow Tracking (Critical Path)

* Modify `orchestrator.py` to:

  * create `WorkflowExecution` record at workflow start
  * emit `capex_events` for lifecycle transitions
  * update record with `completed_at`, `status`, `pr_number`
* **Acceptance:** integration tests confirm workflow execution and event rows are created consistently

### Phase 14c: Initiative Tracker Protocol

* Implement `InitiativeTracker` protocol
* Wire initiative resolution into orchestrator
* **Acceptance:** deterministic parent mapping tests

### Phase 14d: Hours Estimation

* Update estimator to compute PR fallback from PR timeline windows
* Persist `pr_timeline_json` when fallback is used
* **Acceptance:** tests cover reopened PR scenarios

### Phase 14e: Attribution Engine

* Compute `reasoning_hash`
* Populate override fields (default false)
* **Acceptance:** snapshot tests for deterministic outputs

### Phase 14f: CLI Scan Command

* `scan` must create a `report_run_id` and `parameters_hash` for reproducibility
* **Acceptance:** E2E tests with fixtures

### Phase 14g: CLI Report + Export + Verify + Lock

* Add `export`, `verify-export`, `period lock`
* Add `policy show`, `initiative set-policy`, `initiative attest`
* Add `override request/approve/reject`
* **Acceptance:** evidence bundle contents match schema and hashes validate

### Phase 14h/14i: Dashboard API/UI

* Optional later; must only expose current projections + event/mutation history drill-down

---

## Change Log

* Added **Capitalization Policy Mapping** section to explicitly map system classifications to ASC 350-40 and IAS 38 concepts, including evidence markers for authorization/commencement and ready-for-use (Source: [https://www.fasb.org/news-and-meetings/in-the-news/fasb-issues-standard-that-makes-targeted-improvements-to-internal-use-software-guidance-423046](https://www.fasb.org/news-and-meetings/in-the-news/fasb-issues-standard-that-makes-targeted-improvements-to-internal-use-software-guidance-423046)) (Source: [https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-38-intangible-assets.pdf](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-38-intangible-assets.pdf)).
* Incorporated **ASU 2018-15** handling via `capitalization_basis=ASC_350_40_cloud_impl` for cloud implementation cost alignment (Source: [https://storage.fasb.org/ASU%202018-15.pdf](https://storage.fasb.org/ASU%202018-15.pdf)).
* Added explicit **ICFR/SOX-aligned control objectives** and evidence mapping to improve audit readiness (Source: [https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201](https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201)) (Source: [https://www.sec.gov/rules-regulations/2003/03/managements-report-internal-control-over-financial-reporting-certification-disclosure-exchange-act](https://www.sec.gov/rules-regulations/2003/03/managements-report-internal-control-over-financial-reporting-certification-disclosure-exchange-act)).
* Designed an **append-only capex event ledger** (`capex_events`) with hash chaining to support evidence integrity without background jobs; aligned with Amelia’s existing append-only event pattern in `overview.md` .
* Added **mutation logging** (`capex_mutations`) and **approval workflow** (`capex_approvals`) to support change management and segregation of duties (Source: [https://kpmg.com/kpmg-us/content/dam/kpmg/frv/pdf/2023/handbook-internal-controls-over-financial-reporting.pdf](https://kpmg.com/kpmg-us/content/dam/kpmg/frv/pdf/2023/handbook-internal-controls-over-financial-reporting.pdf)).
* Added **period locking** (`capex_period_locks`) to prevent unapproved changes after close; introduced `amelia capex period lock` and breakglass concept (Based on common practice).
* Defined a finance-facing **quarter-end evidence package export bundle** (CSV/JSON + manifest + signatures) with precise fields and auditor trace steps (Based on common practice).
* Strengthened **PR lifecycle fallback** to account for reopened PRs using timeline windows; added `pr_timeline_json` capture to reduce overstatement risk (Source: [https://agilityhealthradar.com/wp-content/uploads/2017/05/The-top-10-pitfalls-of-agile-capitalization-Highlight.pdf](https://agilityhealthradar.com/wp-content/uploads/2017/05/The-top-10-pitfalls-of-agile-capitalization-Highlight.pdf)).
* Formalized governance for **failed workflow credit (50%)** by making the factor explicit in report parameters and requiring approvals for overrides (Based on common practice).
* Added **retention and integrity** guidance and cited SEC’s seven-year accountant retention rule as an external anchor; recommended retaining capex evidence packages for 7 years (Source: [https://www.sec.gov/rules-regulations/2003/01/retention-records-relevant-audits-reviews](https://www.sec.gov/rules-regulations/2003/01/retention-records-relevant-audits-reviews)) (Source: [https://www.sec.gov/news/press/2003-11.htm](https://www.sec.gov/news/press/2003-11.htm)).
