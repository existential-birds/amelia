---
phase: 9
slug: events-dashboard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (Python), vitest (frontend) |
| **Config file** | `pyproject.toml` (Python), `dashboard/vitest.config.ts` (frontend) |
| **Quick run command** | `uv run pytest tests/unit/ -x && cd dashboard && pnpm test:run` |
| **Full suite command** | `uv run pytest && cd dashboard && pnpm test:run && pnpm build` |
| **Estimated runtime** | ~45 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x && cd dashboard && pnpm test:run`
- **After every plan wave:** Run `uv run pytest && cd dashboard && pnpm test:run && pnpm build`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | DASH-01 | unit | `uv run pytest tests/unit/server/ -k "event" -x` | Partial | ⬜ pending |
| 09-01-02 | 01 | 1 | DASH-01 | unit | `uv run pytest tests/unit/ -k "pr_auto_fix" -x` | ❌ W0 | ⬜ pending |
| 09-02-01 | 02 | 1 | DASH-02 | unit | `cd dashboard && pnpm test:run` | Partial | ⬜ pending |
| 09-02-02 | 02 | 1 | DASH-03 | unit | `cd dashboard && pnpm test:run` | ❌ W0 | ⬜ pending |
| 09-02-03 | 02 | 1 | DASH-04 | unit | `cd dashboard && pnpm test:run` | ❌ W0 | ⬜ pending |
| 09-03-01 | 03 | 2 | DASH-05 | unit | `cd dashboard && pnpm test:run` | Partial | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/pipelines/pr_auto_fix/test_workflow_records.py` — stubs for DASH-01 (workflow record creation, event broadcasting)
- [ ] `dashboard/src/components/__tests__/PRCommentSection.test.tsx` — stubs for DASH-03, DASH-04
- [ ] `dashboard/src/components/__tests__/TypeBadge.test.tsx` — stubs for DASH-02
- [ ] Extend `tests/unit/server/test_event_filtering.py` — new event type classifications for DASH-01
- [ ] Extend `dashboard/src/components/__tests__/WorkflowsPage.test.tsx` — tab filtering for DASH-02
- [ ] Extend `dashboard/src/components/__tests__/SettingsProfilesPage.test.tsx` — pr_autofix section for DASH-05

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-time WebSocket event rendering | DASH-01 | Requires live server + WebSocket connection | Start `uv run amelia dev`, trigger PR auto-fix, observe dashboard events tab |
| Dashboard workflow badge visual | DASH-02 | Visual correctness | Check badge renders with correct color/text in browser |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
