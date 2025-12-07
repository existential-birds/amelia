# **Capitalization Tracking & Engineering Attribution — Technical Specification for LLM Coding Agents**

*Version 1.0 — For internal use by the Amelia Orchestration Platform*

---

## **1. Overview**

This document provides all domain knowledge and implementation requirements needed for an LLM coding agent to design and implement a **capitalization and engineering effort attribution system** within an agentic software engineering orchestration platform.

This system:

* Ingests **executive initiative documents**
* Canonicalizes and normalizes **product/engineering initiatives**
* Maps initiatives to **JIRA epics, issues, and tickets**
* Maps initiatives to **GitHub pull requests, commits, and branches**
* Estimates **engineering hours per initiative**
* Tracks **financially capitalizable vs non-capitalizable work**
* Produces **auditable reports** for finance and executives
* Collects **impact metrics** that link engineering work to business outcomes

The final deliverable of this architecture is a set of **Python services, agents, or LangGraph nodes** that collaborate to produce reliable, explainable cost attribution.

---

# **2. Background — What Capitalization Means**

Most tech companies categorize engineering work as either:

### **OPEX (Operational Expense)**

* Bug fixes
* Maintenance
* Support work
* Minor enhancements

### **CAPEX (Capitalized Engineering Work)**

* New feature development
* Platform rewrites
* Long-term infrastructure assets
* R&D leading to durable product value

Finance teams define which initiatives qualify for capitalizability. Engineering operations and the Chief of Staff bridge:

> “Which product initiatives were approved?”
> vs
> “What engineering work actually happened?”

This bridge requires intelligent mapping, estimation, and documentation.

---

# **3. High-Level Workflow**

The capitalization workflow consists of 6 major steps:

```
Executive Initiative Docs
        ↓
 Initiative Extraction & Normalization
        ↓
 Mapping to JIRA Epics / Issues
        ↓
 Mapping to GitHub PRs / Commits
        ↓
 Engineering Hour Estimation & Attribution
        ↓
 Capitalization Reports + Audit Trails
```

Each step can be performed or assisted by an AI agent.

---

# **4. Input Sources**

Your system must integrate with the following external systems:

### **4.1 Executive Documents**

Formats may include:

* Google Docs
* Notion pages
* PDFs / memos
* Confluence strategy docs
* Email summaries

These documents define:

* Initiative names
* Business justification / context
* Time periods
* Responsible teams
* Whether initiative is CAPEX-eligible

### **4.2 JIRA**

Required endpoints:

**Epics**

* Epic name
* Description
* Status
* Issue links
* Labels
* Custom fields (e.g., initiative tags)

**Issues**

* Type (feature/bug/task)
* Assignee
* Created / resolved dates
* Story points (if used)
* Time tracking fields (if any)
* Change logs
* Linked PRs (via integrations)

### **4.3 GitHub**

Required endpoints:

**Pull Requests**

* Title, description
* Author, reviewers
* Open/close/merge timestamps
* Linked issues
* Labels
* Changed files
* Commit metadata

**Commits**

* Author
* Timestamp
* Message
* Lines added/deleted

---

# **5. Core Concepts**

The system must operate on the following domain abstractions:

---

## **5.1 Initiative Object**

Represents capitalizable units of work approved by executives.

```json
{
  "initiative_id": "INIT-001",
  "name": "New Onboarding Experience",
  "description": "Replace login & onboarding flow to reduce friction",
  "business_unit": "Growth",
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "capitalizable": true,
  "canonical_tags": ["onboarding", "growth", "product-led"]
}
```

---

## **5.2 Engineering Work Artifacts**

The system must represent JIRA and GitHub objects uniformly.

```json
{
  "artifact_id": "ENG-ARTIFACT-983",
  "type": "jira_epic | jira_issue | github_pr | commit",
  "linked_initiatives": [],
  "title": "Implement OAuth provider support",
  "description": "Part of onboarding rewrite initiative",
  "engineers": ["alice", "bob"],
  "start_time": "2025-01-10",
  "end_time": "2025-01-14",
  "effort_hours_estimated": null,
  "confidence": 0.0
}
```

---

## **5.3 Mapping Relationships**

Mappings may be:

* Direct (explicit tags, links)
* Heuristic (semantic similarity)
* Confirmed (human validated)

```json
{
  "initiative_id": "INIT-001",
  "artifact_id": "PR-1293",
  "score": 0.82,
  "method": "semantic_match + related_epic",
  "status": "auto_mapped"
}
```

---

# **6. AI Agent Responsibilities**

Your agentic system should include (at minimum) the following subsystems:

---

## **6.1 Initiative Extraction Agent**

Tasks:

* Extract initiative names and descriptions from documents
* Normalize naming conventions
* Create canonical initiative objects
* Tag using embeddings-based topic classification

---

## **6.2 JIRA Mapping Agent**

Tasks:

* Search JIRA epics and issues
* Score matches using semantic similarity
* Infer relationships via issue links and shared parents
* Identify ambiguous mappings needing human review

---

## **6.3 GitHub Mapping Agent**

Tasks:

* Analyze PR titles, descriptions
* Use commit messages for semantic matching
* Look for ticket IDs in branch names
* Score PR relevance to initiatives

---

## **6.4 Engineering Hours Estimation Agent**

Tasks:

* Use PR open → merge lifecycle as a proxy
* Use issue lifecycles (status transitions)
* Apply heuristics (configurable):

  * 6 hours/day productive engineering time
  * 1 story point = N hours
* Detect multi-developer PRs
* Avoid overcounting by merging correlated artifacts

---

## **6.5 Financial Attribution Agent**

Tasks:

* Multiply hours × fully-loaded labor rates
* Generate OPEX vs CAPEX breakdowns
* Provide per-initiative totals
* Export CSV/JSON/PDF summaries

---

## **6.6 Audit Log Agent**

Tasks:

* Record reasoning behind mappings
* Keep evidence references (text snippets, PR/issue IDs)
* Retain uncertainty flags
* Provide audit-ready narratives

Example:

```json
{
  "artifact": "PR-1293",
  "initiative": "INIT-001",
  "reasoning": [
    "PR title contains 'onboarding'",
    "Linked to Epic ENG-2041 which maps to INIT-001",
    "High semantic match score (0.87)"
  ],
  "confidence": 0.91
}
```

---

# **7. Engineering Hour Estimation Methodologies**

Your implementation must support **multiple estimation strategies**, fallbacks, and combined confidence scoring.

---

## **7.1 PR Lifecycle Heuristic**

```
hours = business_hours_between(pr_open_time, pr_merge_time) * engineer_weight
```

Engineer weights:

* junior = 0.8
* mid = 1.0
* senior = 1.2

---

## **7.2 JIRA Status-Lifecycle Heuristic**

```
active_time = (time_in_progress + time_in_review + time_in_qa)
estimated_hours = active_time / standard_working_hours_per_day
```

---

## **7.3 Story Points → Hours Mapping**

(If the company uses agile pointing)

Example:

* 1 SP ≈ 2–6 hours
* Use median or team-calibrated factor

---

## **7.4 Manual Overrides**

If EMs provide hours, those always take precedence.

---

# **8. Critical Metrics to Collect**

Your system must track **3 classes of metrics**:

---

## **8.1 Capitalization Metrics**

These are required for finance:

| Metric                                 | Description                            |
| -------------------------------------- | -------------------------------------- |
| Total engineering hours per initiative | Primary metric used for capitalization |
| Total cost per initiative              | Hours × labor rate                     |
| Capitalizable %                        | Portion of work eligible per GAAP      |
| OPEX vs CAPEX split                    | Required for financial reporting       |
| Hours by engineer seniority            | For cost weighting                     |
| Hours by team                          | For departmental budget allocation     |

---

## **8.2 Engineering Productivity Metrics**

Useful for business + engineering leadership:

| Metric                          | Purpose                              |
| ------------------------------- | ------------------------------------ |
| Cycle time                      | PR open → merge duration             |
| Time-in-status                  | JIRA time in progress/review/testing |
| PR review load                  | Helps detect bottlenecks             |
| PRs merged per initiative       | Initiative complexity                |
| Developer contribution patterns | Who is working on what               |

---

## **8.3 Initiative Impact Metrics**

Helps evaluate ROI of engineering time:

| Impact Metric                  | Example                              |
| ------------------------------ | ------------------------------------ |
| Feature adoption               | % of users using new onboarding      |
| Revenue influence              | Uplift tied to initiative execution  |
| Infra performance improvements | Latency reduction, reliability gains |
| Customer outcome metrics       | Support tickets, NPS scores          |
| Time saved                     | Internal productivity improvements   |

The system does **not** need to compute all metrics — but it must collect the raw workspace data such that metrics can be computed downstream.

---

# **9. Required Outputs**

Agents must be able to generate the following:

---

## **9.1 Initiative-Level Summary**

```json
{
  "initiative_id": "INIT-001",
  "total_hours": 431.5,
  "total_cost": 62283.50,
  "capitalizable_hours": 398.2,
  "non_capitalizable_hours": 33.3,
  "engineers_involved": ["alice", "bob", "carol"],
  "confidence": 0.88
}
```

---

## **9.2 Artifact-Level Mapping Report**

```json
[
  {
    "artifact": "PR-1293",
    "initiative": "INIT-001",
    "estimated_hours": 9.4,
    "confidence": 0.91
  }
]
```

---

## **9.3 Audit Narrative (Human-Readable)**

```
Initiative: New Onboarding Experience (INIT-001)

PR-1293 was mapped to this initiative because:
- The PR title references onboarding and user login
- It was linked to JIRA Epic ENG-2041, which is tied to this initiative
- Semantic similarity score: 0.87
Estimated effort: 9.4 engineering hours
Confidence: High (0.91)
```

---

# **10. Architecture Requirements**

Your system should support:

### ✔ Graph-based or workflow-based agent execution (LangGraph recommended)

### ✔ Configurable and tunable heuristics

### ✔ Human-in-the-loop approval workflow

### ✔ Full traceability & auditability

### ✔ Ability to re-run and update metrics each quarter

### ✔ JSON-based schemas for universal data exchange

---

# **11. Implementation Tasks (For the Coding Agent)**

The coding agent must be able to:

1. Design and generate initiative extraction parsers
2. Implement JIRA/GitHub integration modules
3. Implement semantic-matching workflows
4. Implement hours estimation algorithms
5. Generate initiative-level cost summaries
6. Build an audit trail subsystem
7. Support interactive UI (React) for validation
8. Design a persistence layer (Postgres preferred)
9. Create LangGraph agents & state machines
10. Ensure modularity for future extensibility

---

# **12. Example End-to-End Flow**

```
1. Load executive doc
2. Extract initiatives → initiative objects
3. Query JIRA + GitHub → fetch artifacts
4. For each initiative:
     a. Score and map related artifacts
     b. Estimate hours for each artifact
5. Aggregate totals
6. Generate finance-ready report
7. Produce audit logs
8. Store everything in the Amelia backend
```