# Roadmap: PR Auto-Fix

## Milestones

- ✅ **v1.0 PR Auto-Fix** — Phases 1-14 (shipped 2026-03-22) → [archive](milestones/v1.0-ROADMAP.md)

### Phase 1: Review pipeline efficiency

**Goal:** Eliminate redundant diff fetching and unreliable structured output in the review pipeline — reduce reviewer token cost by ~50% and prevent evaluator crashes from schema validation failures
**Requirements**: See docs/specs/2025-03-29-review-pipeline-efficiency.md
**Depends on:** —
**Plans:** 1/3 plans executed

Plans:
- [x] 01-01-PLAN.md — Driver fix for custom tool names + diff pre-computation and reviewer prompt update
- [ ] 01-02-PLAN.md — Evaluator tool-based submission (submit_evaluation)
- [ ] 01-03-PLAN.md — Reviewer submit tool (submit_review)
