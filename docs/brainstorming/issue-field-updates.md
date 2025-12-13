# GitHub Issue Project Field Updates

This document contains proposed updates for open issues missing project fields in the Amelia Roadmap.

## Project Field Options

| Field | Available Values |
|-------|------------------|
| Status | Exploring, Planned, In Progress, Done |
| Area | Core, Agents, Dashboard, CLI, Server |
| Size | small, medium, large, xl |
| Target Release | v1.0.0, v2.0.0, v3.0.0 |

## Issues Requiring Updates

### Priority 1: Missing Area + Size + Target Release

| Issue # | Title | Current Status | Labels | Recommended Area | Recommended Size | Recommended Release | Rationale |
|---------|-------|----------------|--------|------------------|------------------|---------------------|-----------|
| #85 | Context Compiler | In Progress | area:core, area:agents | Core | large | v1.0.0 | Active work, foundational feature for agent context management |
| #84 | Queue workflows without immediate execution | Exploring | area:core, area:cli, area:server | Server | medium | v2.0.0 | Server-side queue management, not critical for v1 |
| #83 | Activity log messages duplicated (bug) | Planned | area:agents, area:dashboard, area:server | Server | small | v1.0.0 | Bug fix, should ship before v1 release |
| #82 | Streaming output not appearing (bug) | Planned | area:agents, area:dashboard, area:server | Server | small | v1.0.0 | Bug fix, should ship before v1 release |
| #80 | Feedback Evaluator agent | Exploring | area:core, area:agents | Agents | large | v2.0.0 | New agent component, can wait for v2 |
| #30 | Dashboard Project Setup | Exploring | area:dashboard | Dashboard | medium | v1.0.0 | If dashboard is needed for v1, otherwise v2 |
| #9 | Handle clarification requests from Claude | Exploring | area:core | Core | medium | v2.0.0 | Nice-to-have UX improvement |
| #8 | Reviewer agent benchmark framework | Exploring | area:agents | Agents | large | v2.0.0 | Quality tooling, not blocking v1 |

### Priority 2: Missing Target Release Only

| Issue # | Title | Status | Area | Size | Recommended Release | Rationale |
|---------|-------|--------|------|------|---------------------|-----------|
| #73 | Task execution metrics | Planned | Dashboard | large | v1.0.0 | Wire up existing backend to dashboard |
| #72 | Phase 16 - 12-Factor Loop | Exploring | Core | xl | v3.0.0 | Architectural refinements, long-term |
| #71 | Phase 15 - Cloud Deployment | Exploring | Server | xl | v3.0.0 | Cloud infrastructure, advanced feature |
| #70 | Phase 14 - Capitalization Tracking | Exploring | Server | medium | v3.0.0 | Enterprise feature |
| #69 | Phase 13 - Knowledge Library | Exploring | Dashboard | xl | v3.0.0 | Advanced co-learning system |
| #68 | Phase 7 - Quality Gates | Exploring | Agents | large | v2.0.0 | Verification before review |
| #67 | Phase 12 - Debate Mode | Exploring | Agents | large | v3.0.0 | Multi-agent deliberation |
| #66 | Phase 6 - PR Lifecycle | Planned | CLI | medium | v2.0.0 | Eliminate GitHub web for review |
| #65 | Phase 11 - Spec Builder | Exploring | Dashboard | xl | v3.0.0 | NotebookLM-style feature |
| #64 | Phase 5 - Tracker Sync | Exploring | CLI | medium | v2.0.0 | Bidirectional sync |
| #63 | Phase 10 - Continuous Improvement | Exploring | Core | large | v3.0.0 | Quality flywheel |
| #62 | Phase 4 - Verification Framework | Planned | Core | large | v1.0.0 | Agents verify before done - foundational |
| #61 | Phase 9 - Chat Integration | Planned | Server | large | v2.0.0 | Mobile/async management |
| #60 | Phase 3 - Session Continuity | Planned | Core | large | v1.0.0 | Structured handoff - foundational |
| #59 | Phase 8 - Parallel Execution | Planned | Core | xl | v2.0.0 | Throughput multiplier |
| #43 | Extract mock fixtures | Planned | Core | small | v1.0.0 | Tech debt cleanup |
| #33 | Remove start-local | Planned | CLI | small | v1.0.0 | Tech debt cleanup |
| #7 | CLI integration tests | Planned | CLI | small | v1.0.0 | Test coverage |

## Release Planning Summary

### v1.0.0 (Foundational)
- Bug fixes: #82, #83
- Active work: #85
- Foundational phases: #60 (Session Continuity), #62 (Verification Framework)
- Dashboard wiring: #73, #30
- Tech debt: #7, #33, #43

### v2.0.0 (Enhanced Workflows)
- Phases 5-8: #59, #64, #66, #68
- New components: #8, #9, #80
- Server features: #61, #84

### v3.0.0 (Advanced Features)
- Phases 9-16: #63, #65, #67, #69, #70, #71, #72

---

## Agent Prompt

Use this prompt to step through updates:

```
Step through the GitHub issues in /Users/ka/github/amelia-feature/docs/brainstorming/issue-field-updates.md one by one.

For each issue that needs updates:
1. Show the issue number, title, and current field values
2. Show the recommended values from the document with the rationale
3. Ask the user to confirm, modify, or skip
4. If confirmed, update the project fields using gh CLI
5. Move to the next issue

Project field IDs for gh project item-edit:
- Project ID: PVT_kwHOAQONZs4BKCbl
- Area field: PVTSSF_lAHOAQONZs4BKCblzg6BhvA
  - Core: d70c692a
  - Agents: e572a38f
  - Dashboard: dff436c0
  - CLI: 4220fcc2
  - Server: d0fc31de
- Size field: PVTSSF_lAHOAQONZs4BKCblzg6BiEg
  - small: 1fe785fd
  - medium: 16d41963
  - large: 31e2a5d9
  - xl: 72b099bf
- Target Release field: PVTSSF_lAHOAQONZs4BKCblzg6Bhis
  - v1.0.0: 119ce3da
  - v2.0.0: 813e7362
  - v3.0.0: 045b7fd0

To get the project item ID for an issue:
gh project item-list 2 --owner anderskev --limit 100 --format json | jq -r '.items[] | select(.content.number == ISSUE_NUM) | .id'

To update a field:
gh project item-edit --project-id PVT_kwHOAQONZs4BKCbl --id ITEM_ID --field-id FIELD_ID --single-select-option-id OPTION_ID

Start with Priority 1 issues (missing all fields), then Priority 2 (missing target release only).
```
