---
phase: 7
slug: cli-api-triggers
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio (auto mode) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/unit/ -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 0 | TRIG-01 | unit | `uv run pytest tests/unit/test_fix_pr_command.py -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 0 | TRIG-02 | unit | `uv run pytest tests/unit/test_watch_pr_command.py -x` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 0 | TRIG-03 | unit | `uv run pytest tests/unit/server/routes/test_github_pr_routes.py::test_trigger_autofix -x` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 0 | TRIG-04 | unit | `uv run pytest tests/unit/server/routes/test_github_pr_routes.py::test_list_prs -x` | ❌ W0 | ⬜ pending |
| 07-01-05 | 01 | 0 | TRIG-05 | unit | `uv run pytest tests/unit/server/routes/test_github_pr_routes.py::test_get_pr_comments -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_fix_pr_command.py` — stubs for TRIG-01
- [ ] `tests/unit/test_watch_pr_command.py` — stubs for TRIG-02
- [ ] `tests/unit/server/routes/test_github_pr_routes.py` — stubs for TRIG-03, TRIG-04, TRIG-05
- [ ] `tests/unit/server/routes/__init__.py` — package init if missing

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Watch-PR polling loop | TRIG-02 | Long-running background loop hard to test deterministically | Start `amelia watch-pr 123 --interval 5`, verify it polls and exits on Ctrl+C |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
