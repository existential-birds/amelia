---
phase: 2
slug: github-api-layer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (auto mode) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
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
| 02-01-01 | 01 | 0 | GHAPI-01 | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_fetch_review_comments -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 0 | GHAPI-02 | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_list_open_prs -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 0 | GHAPI-03 | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_resolve_thread -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 0 | GHAPI-04 | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_reply_to_comment -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 0 | GHAPI-05 | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_skip_self_comments -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 0 | GIT-01 | unit | `uv run pytest tests/unit/tools/test_git_operations.py::test_stage_and_commit -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 0 | GIT-02 | unit | `uv run pytest tests/unit/tools/test_git_operations.py::test_push -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 0 | GIT-03 | unit | `uv run pytest tests/unit/tools/test_git_operations.py::test_divergence_abort -x` | ❌ W0 | ⬜ pending |
| 02-02-04 | 02 | 0 | GIT-04 | unit | `uv run pytest tests/unit/tools/test_git_operations.py::test_sha_verification -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/services/__init__.py` — new package
- [ ] `tests/unit/services/test_github_pr.py` — stubs for GHAPI-01 through GHAPI-05
- [ ] `tests/unit/tools/test_git_operations.py` — stubs for GIT-01 through GIT-04
- [ ] `amelia/services/__init__.py` — new package

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
