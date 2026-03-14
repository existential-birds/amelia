---
phase: 10
slug: metrics-benchmarking
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (backend), vitest (frontend) |
| **Config file** | `pyproject.toml` (pytest), `dashboard/vitest.config.ts` (vitest) |
| **Quick run command** | `uv run pytest tests/unit/ -x` |
| **Full suite command** | `uv run pytest && cd dashboard && pnpm test:run` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x`
- **After every plan wave:** Run `uv run pytest && cd dashboard && pnpm test:run`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | METR-01 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py -x -k latency` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 1 | METR-05 | unit | `uv run pytest tests/unit/server/test_metrics_extraction.py -x` | ❌ W0 | ⬜ pending |
| 10-01-03 | 01 | 1 | METR-03 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x -k classification_audit` | ❌ W0 | ⬜ pending |
| 10-01-04 | 01 | 1 | METR-06 | unit | `uv run pytest tests/unit/server/database/test_metrics_repository.py -x` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 2 | METR-02 | unit | `uv run pytest tests/unit/server/routes/test_metrics_routes.py -x -k aggressiveness` | ❌ W0 | ⬜ pending |
| 10-02-02 | 02 | 2 | METR-07 | unit | `uv run pytest tests/unit/server/routes/test_metrics_routes.py -x` | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 2 | METR-08 | unit | `cd dashboard && pnpm test:run -- --testPathPattern=PRFixMetrics` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/server/database/test_metrics_repository.py` — stubs for METR-06
- [ ] `tests/unit/server/routes/test_metrics_routes.py` — stubs for METR-02, METR-07
- [ ] `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` — extend existing with METR-01 latency tests
- [ ] `tests/unit/pipelines/pr_auto_fix/test_nodes.py` — extend existing with METR-03 classification audit tests
- [ ] `tests/unit/server/test_metrics_extraction.py` — stubs for METR-05
- [ ] `dashboard/src/pages/__tests__/AnalyticsPage.test.tsx` — stubs for METR-08

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dashboard chart visual rendering | METR-08 | Chart appearance needs visual check | Load Analytics page, verify charts render with sample data |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
