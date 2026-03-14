---
phase: 8
slug: polling-service
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (auto mode) |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 0 | POLL-01..05 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py -x` | No -- Wave 0 | pending |
| 08-01-02 | 01 | 1 | POLL-03 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_start_stop_lifecycle -x` | W0 | pending |
| 08-01-03 | 01 | 1 | POLL-01 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_polls_enabled_profiles -x` | W0 | pending |
| 08-01-04 | 01 | 1 | POLL-01 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_skips_disabled_profiles -x` | W0 | pending |
| 08-01-05 | 01 | 1 | POLL-01 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_skips_prs_no_comments -x` | W0 | pending |
| 08-01-06 | 01 | 1 | POLL-02 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_per_profile_interval -x` | W0 | pending |
| 08-01-07 | 01 | 1 | POLL-04 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_exception_resilience -x` | W0 | pending |
| 08-01-08 | 01 | 1 | POLL-05 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_rate_limit_backoff -x` | W0 | pending |
| 08-01-09 | 01 | 1 | POLL-05 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_rate_limit_event -x` | W0 | pending |
| 08-02-01 | 02 | 2 | POLL-03 | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_start_stop_lifecycle -x` | W0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/server/lifecycle/test_pr_poller.py` -- stubs for POLL-01 through POLL-05
- [ ] Mock fixtures for `ProfileRepository`, `SettingsRepository`, `PRAutoFixOrchestrator`, and `gh` subprocess calls

*Existing infrastructure covers framework needs -- pytest + pytest-asyncio already installed and configured.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Rate limit 10% threshold tuning | POLL-05 | Requires real GitHub API rate limit state | Monitor logs during real polling; adjust threshold if premature/late backoff observed |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
