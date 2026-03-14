---
phase: 6
slug: orchestration-safety
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (auto mode) |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/unit/pipelines/pr_auto_fix/ -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/pipelines/pr_auto_fix/ -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | ORCH-01 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_concurrent_triggers_same_pr -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | ORCH-01 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_concurrent_different_prs -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | ORCH-02 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_pending_flag_triggers_next_cycle -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | ORCH-02 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_cooldown_resets_on_new_comment -x` | ❌ W0 | ⬜ pending |
| 06-01-05 | 01 | 1 | ORCH-02 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_cooldown_max_cap -x` | ❌ W0 | ⬜ pending |
| 06-01-06 | 01 | 1 | ORCH-03 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_resets_to_remote_head -x` | ❌ W0 | ⬜ pending |
| 06-01-07 | 01 | 1 | ORCH-03 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_divergence_retry_and_exhaustion -x` | ❌ W0 | ⬜ pending |
| 06-01-08 | 01 | 1 | Config | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_cooldown_config_validation -x` | ❌ W0 | ⬜ pending |
| 06-01-09 | 01 | 1 | Events | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_event_types_exist -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` — stubs for ORCH-01, ORCH-02, ORCH-03, config validation, and event types
- [ ] No new framework install needed — pytest-asyncio already configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cooldown countdown visible in dashboard | ORCH-02 | Requires running dashboard UI | Start dev server, trigger fix cycle, verify cooldown event appears with countdown |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
